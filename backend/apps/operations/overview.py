"""One read-only snapshot of an organization's background work, for owners and admins."""

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from apps.organizations.models import Organization

from . import heartbeat

WINDOW_DAYS = 7
RECENT_FAILURES = 10


def _counts(qs: Any, field: str = "status") -> dict[str, int]:
    return {row[field]: row["n"] for row in qs.values(field).annotate(n=Count("id")).order_by()}


def build(org: Organization) -> dict[str, Any]:
    from apps.ai.models import AIWorkflowRun
    from apps.automation.models import AutomationAction
    from apps.automation.policy import get_policy
    from apps.publishing.models import PublishedPost, PublishingJob
    from apps.social.models import SocialAccount

    now = timezone.now()
    since = now - timedelta(days=WINDOW_DAYS)

    jobs = PublishingJob.objects.filter(organization=org)
    live = _counts(
        jobs.filter(status__in=["scheduled", "queued", "publishing", "needs_reconciliation"])
    )
    recent = _counts(jobs.filter(updated_at__gte=since, status__in=["published", "failed"]))
    job_failures = (
        jobs.filter(status="failed", updated_at__gte=since)
        .select_related("content_item", "social_account")
        .order_by("-updated_at")[:RECENT_FAILURES]
    )

    runs = AIWorkflowRun.objects.filter(organization=org)
    run_live = _counts(runs.filter(status__in=["queued", "running"]))
    run_recent = _counts(runs.filter(created_at__gte=since, status__in=["succeeded", "failed"]))
    run_failures = runs.filter(status="failed", created_at__gte=since).order_by("-created_at")[
        :RECENT_FAILURES
    ]

    actions = AutomationAction.objects.filter(organization=org)
    action_open = _counts(actions.filter(status__in=["awaiting_approval", "deferred"]))
    policy = get_policy(org)

    metrics = _counts(
        PublishedPost.objects.filter(organization=org, published_at__gte=now - timedelta(days=90)),
        "metrics_status",
    )

    return {
        "generated_at": now,
        "window_days": WINDOW_DAYS,
        "background": heartbeat.status(),
        "publishing": {
            "scheduled": live.get("scheduled", 0),
            "queued": live.get("queued", 0),
            "publishing": live.get("publishing", 0),
            "needs_reconciliation": live.get("needs_reconciliation", 0),
            "published_recent": recent.get("published", 0),
            "failed_recent": recent.get("failed", 0),
            "recent_failures": [
                {
                    "id": j.pk,
                    "content_item": j.content_item_id,
                    "content_title": j.content_item.title,
                    "account_name": j.social_account.name,
                    "platform": j.social_account.platform,
                    "is_mock": j.social_account.is_mock,
                    "error_code": j.error_code,
                    "error_message": j.error_message,
                    "at": j.updated_at,
                }
                for j in job_failures
            ],
        },
        "ai": {
            "queued": run_live.get("queued", 0),
            "running": run_live.get("running", 0),
            "succeeded_recent": run_recent.get("succeeded", 0),
            "failed_recent": run_recent.get("failed", 0),
            "recent_failures": [
                {
                    "id": r.pk,
                    "workflow": r.workflow,
                    "error_code": r.error_code,
                    "error_message": r.error_message,
                    "is_mock": r.is_mock,
                    "at": r.finished_at or r.created_at,
                }
                for r in run_failures
            ],
        },
        "automation": {
            "mode": policy.mode,
            "paused": policy.paused,
            "awaiting_approval": action_open.get("awaiting_approval", 0),
            "deferred": action_open.get("deferred", 0),
            "failed_recent": actions.filter(status="failed", updated_at__gte=since).count(),
        },
        "social_accounts_needing_attention": [
            {"id": a.pk, "name": a.name, "platform": a.platform, "status": a.status}
            for a in SocialAccount.objects.filter(
                organization=org, status__in=["needs_reauth", "disconnected"]
            ).order_by("name")
        ],
        # Posts from the last 90 days by metrics collection outcome ("" = not collected yet).
        "metrics_collection": metrics,
    }
