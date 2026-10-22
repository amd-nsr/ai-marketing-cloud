"""Evidence-based recommendations from deterministic, explainable rules.

Each rule states what was observed (with numbers and sample sizes), why acting may
help, and what remains uncertain. Rules never claim causality and stay silent when
there isn't enough data.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.content.models import Approval
from apps.marketing.models import MarketingPlan
from apps.organizations.models import Organization
from apps.publishing.models import PublishedPost, PublishingJob
from apps.social.models import SocialAccount

from .definitions import PRIMARY_ENGAGEMENT, definition
from .models import MarketingRecommendation, RecommendationEvidence
from .services import posts_with_metrics

K = MarketingRecommendation.Kind
MIN_POSTS_PER_GROUP = 3
MIN_POSTS_TOTAL = 6
MIN_POSTS_TOP = 5
RECOMMENDATION_WINDOW_DAYS = 60
DISMISSED_QUIET_DAYS = 30
FORMAT_LABEL = {
    "post": "single-image posts",
    "carousel": "carousels",
    "reel": "reels",
    "story": "stories",
    "short_video": "short videos",
}


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass
class Evidence:
    description: str
    platform: str = ""
    metric_key: str = ""
    value: float | None = None
    baseline: float | None = None
    sample_size: int | None = None
    published_post_id: Any = None


@dataclass
class Draft:
    kind: str
    fingerprint: str
    title: str
    observation: str
    rationale: str
    suggested_action: str
    uncertainty: str = ""
    priority: int = 2
    link: str = ""
    uses_simulated_data: bool = False
    evidence: list[Evidence] = field(default_factory=list)


def _engagement_metric(platform: str, rows: list[dict[str, Any]]) -> str | None:
    for key in PRIMARY_ENGAGEMENT.get(platform, ()):
        if sum(1 for r in rows if r["metrics"].get(key) is not None) >= MIN_POSTS_TOTAL:
            return key
    return None


def _format_rules(org: Organization, rows: list[dict[str, Any]], base: str) -> list[Draft]:
    drafts = []
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_platform.setdefault(r["platform"], []).append(r)
    for platform, prows in by_platform.items():
        metric = _engagement_metric(platform, prows)
        if metric is None:
            continue
        label = definition(metric).label.lower()
        valued = [r for r in prows if r["metrics"].get(metric) is not None]
        simulated = any(r["is_mock"] for r in valued)
        baseline = median(r["metrics"][metric] for r in valued)
        if baseline <= 0:
            continue
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in valued:
            groups.setdefault(r["format"], []).append(r)
        for fmt, grows in groups.items():
            if len(grows) < MIN_POSTS_PER_GROUP or len(grows) == len(valued):
                continue
            group_median = median(r["metrics"][metric] for r in grows)
            ratio = group_median / baseline
            if 0.5 < ratio < 1.5:
                continue
            better = ratio >= 1.5
            name = FORMAT_LABEL.get(fmt, fmt)
            drafts.append(
                Draft(
                    kind=K.FORMAT_PERFORMANCE,
                    fingerprint=f"format:{platform}:{fmt}:{'up' if better else 'down'}",
                    title=f"{name.capitalize()} {'are outperforming' if better else 'are underperforming'} on {platform.title()}",
                    observation=(
                        f"Across your last {len(valued)} {platform.title()} posts, {name} had a median of "
                        f"{group_median:,.0f} {label} versus {baseline:,.0f} for all posts "
                        f"({ratio:.1f}x the typical post, {len(grows)} {name})."
                    ),
                    rationale=(
                        f"Doing more of what your audience already responds to is a low-risk way to improve {label}."
                        if better
                        else f"{name.capitalize()} are getting noticeably fewer {label} than your other posts."
                    ),
                    suggested_action=(
                        f"Plan a few more {name} in the next two weeks and compare results."
                        if better
                        else f"Review recent {name}: try a stronger hook or a different theme before making more."
                    ),
                    uncertainty=(
                        f"Based on {len(grows)} {name}; topic, timing and boosting can explain differences. "
                        "This shows correlation, not cause."
                    ),
                    priority=2,
                    link=f"{base}/analytics",
                    uses_simulated_data=simulated,
                    evidence=[
                        Evidence(
                            f"Median {label} for {name}",
                            platform,
                            metric,
                            group_median,
                            baseline,
                            len(grows),
                        ),
                        Evidence(
                            f"Median {label} for all posts",
                            platform,
                            metric,
                            baseline,
                            None,
                            len(valued),
                        ),
                    ],
                )
            )
    return drafts


def _top_post_rule(rows: list[dict[str, Any]], base: str) -> list[Draft]:
    drafts = []
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_platform.setdefault(r["platform"], []).append(r)
    for platform, prows in by_platform.items():
        metric = None
        for key in PRIMARY_ENGAGEMENT.get(platform, ()):
            if sum(1 for r in prows if r["metrics"].get(key) is not None) >= MIN_POSTS_TOP:
                metric = key
                break
        if metric is None:
            continue
        valued = [r for r in prows if r["metrics"].get(metric) is not None]
        baseline = median(r["metrics"][metric] for r in valued)
        top = max(valued, key=lambda r: r["metrics"][metric])
        value = top["metrics"][metric]
        if baseline <= 0 or value < 2 * baseline:
            continue
        label = definition(metric).label.lower()
        drafts.append(
            Draft(
                kind=K.TOP_POST,
                fingerprint=f"top:{top['id']}",
                title=f"“{_short(top['title'])}” stood out on {platform.title()}",
                observation=(
                    f"It received {value:,.0f} {label}, {value / baseline:.1f}x your median of "
                    f"{baseline:,.0f} across {len(valued)} {platform.title()} posts."
                ),
                rationale="Posts that clearly outperform are a good template for future content.",
                suggested_action="Create a follow-up or variation on the same theme, and reuse its hook or format.",
                uncertainty="A single post can do well for reasons outside your control (timing, shares by others).",
                priority=3,
                link=f"{base}/content/{top['content_item']}",
                uses_simulated_data=top["is_mock"],
                evidence=[
                    Evidence(
                        f"{definition(metric).label} on this post",
                        platform,
                        metric,
                        value,
                        baseline,
                        len(valued),
                        top["id"],
                    )
                ],
            )
        )
    return drafts


def _posting_gap_rule(org: Organization, base: str) -> list[Draft]:
    if not MarketingPlan.objects.filter(
        organization=org, status=MarketingPlan.Status.ACTIVE
    ).exists():
        return []
    last = PublishedPost.objects.filter(organization=org).order_by("-published_at").first()
    upcoming = PublishingJob.objects.filter(
        organization=org, status__in=["scheduled", "queued"]
    ).exists()
    if upcoming:
        return []
    days = (timezone.now() - last.published_at).days if last else None
    if days is not None and days < 14:
        return []
    observation = (
        f"Nothing has been published for {days} days and nothing is scheduled."
        if days is not None
        else "You have an active marketing plan but nothing has been published or scheduled yet."
    )
    return [
        Draft(
            kind=K.POSTING_GAP,
            fingerprint="posting_gap",
            title="Your publishing has paused",
            observation=observation,
            rationale="Your active plan assumes regular posting; long gaps make results hard to build or measure.",
            suggested_action="Schedule the next items from your plan's content calendar.",
            uncertainty="A pause may be intentional (holidays, seasonality).",
            priority=1,
            link=f"{base}/calendar",
        )
    ]


def _operational_rules(org: Organization, base: str) -> list[Draft]:
    drafts = []
    for account in SocialAccount.objects.filter(
        organization=org, status=SocialAccount.Status.NEEDS_REAUTH
    ):
        drafts.append(
            Draft(
                kind=K.ACCOUNT_REAUTH,
                fingerprint=f"reauth:{account.pk}",
                title=f"Reconnect {account.name}",
                observation=f"{account.get_platform_display()} rejected our stored access for {account.name}.",
                rationale="Scheduled posts and metrics for this account will fail until it's reconnected.",
                suggested_action="Open Social accounts and connect it again.",
                priority=1,
                link=f"{base}/accounts",
                uses_simulated_data=account.is_mock,
            )
        )
    stale = Approval.objects.filter(
        organization=org,
        status=Approval.Status.PENDING,
        created_at__lt=timezone.now() - timedelta(days=3),
    ).count()
    if stale:
        drafts.append(
            Draft(
                kind=K.STALE_APPROVALS,
                fingerprint="stale_approvals",
                title=f"{stale} item{'s' if stale > 1 else ''} waiting for approval for over 3 days",
                observation=f"{stale} approval request{'s have' if stale > 1 else ' has'} been pending for more than 3 days.",
                rationale="Content waiting for review can't be scheduled, which leaves gaps in your calendar.",
                suggested_action="Review the approval queue.",
                priority=1,
                link=f"{base}/approvals",
            )
        )
    failed = PublishingJob.objects.filter(
        organization=org,
        status=PublishingJob.Status.FAILED,
        updated_at__gte=timezone.now() - timedelta(days=7),
    ).count()
    if failed:
        drafts.append(
            Draft(
                kind=K.PUBLISHING_FAILURES,
                fingerprint="publishing_failures",
                title=f"{failed} post{'s' if failed > 1 else ''} failed to publish this week",
                observation=f"{failed} publishing job{'s' if failed > 1 else ''} ended in failure in the last 7 days.",
                rationale="Failed posts never reached your audience.",
                suggested_action="Check the reasons in Publishing and retry or fix them.",
                priority=1,
                link=f"{base}/publishing",
            )
        )
    return drafts


def build_drafts(org: Organization) -> list[Draft]:
    base = f"/o/{org.pk}"
    rows = posts_with_metrics(org, days=RECOMMENDATION_WINDOW_DAYS)
    return [
        *_operational_rules(org, base),
        *_posting_gap_rule(org, base),
        *_format_rules(org, rows, base),
        *_top_post_rule(rows, base),
    ]


@transaction.atomic
def generate(org: Organization) -> dict[str, int]:
    """Create/refresh recommendations. Dismissed ones stay quiet for 30 days; ones whose
    condition no longer holds are removed if never acted on."""
    now = timezone.now()
    drafts = build_drafts(org)
    seen = set()
    created = updated = 0
    for d in drafts:
        seen.add(d.fingerprint)
        rec = MarketingRecommendation.objects.filter(
            organization=org, fingerprint=d.fingerprint
        ).first()
        if (
            rec
            and rec.status == MarketingRecommendation.Status.DISMISSED
            and rec.decided_at
            and rec.decided_at > now - timedelta(days=DISMISSED_QUIET_DAYS)
        ):
            continue
        fields = {
            "kind": d.kind,
            "priority": d.priority,
            "title": d.title[:200],
            "observation": d.observation,
            "rationale": d.rationale,
            "suggested_action": d.suggested_action,
            "uncertainty": d.uncertainty,
            "link": d.link,
            "uses_simulated_data": d.uses_simulated_data,
            "generated_at": now,
        }
        if rec is None:
            rec = MarketingRecommendation.objects.create(
                organization=org, fingerprint=d.fingerprint, **fields
            )
            created += 1
        else:
            for k, v in fields.items():
                setattr(rec, k, v)
            if rec.status == MarketingRecommendation.Status.DISMISSED:
                rec.status = MarketingRecommendation.Status.NEW
            rec.save()
            rec.evidence.all().delete()
            updated += 1
        RecommendationEvidence.objects.bulk_create(
            [
                RecommendationEvidence(
                    organization=org,
                    recommendation=rec,
                    description=e.description,
                    platform=e.platform,
                    metric_key=e.metric_key,
                    value=e.value,
                    baseline=e.baseline,
                    sample_size=e.sample_size,
                    published_post_id=e.published_post_id,
                )
                for e in d.evidence
            ]
        )
    removed, _ = (
        MarketingRecommendation.objects.filter(
            organization=org, status=MarketingRecommendation.Status.NEW
        )
        .exclude(fingerprint__in=seen)
        .delete()
    )
    return {"created": created, "updated": updated, "resolved": removed}
