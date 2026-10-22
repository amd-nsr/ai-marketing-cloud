"""Publishing engine: durable jobs, explicit transitions, safe retries, reconciliation.

Invariants:
- Only approved content is published, and only the exact version that was approved.
- A job is sent at most once per attempt; attempts are recorded before the network call.
- After an uncertain outcome (timeout after sending) a job is never resubmitted
  automatically: the platform is checked for the post first (reconciliation).
- Idempotency keys make duplicate API requests return the original job.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.content.models import ContentItem
from apps.content.services import set_status as set_content_status
from apps.core.errors import Conflict, QuotaExceeded
from apps.core.state_machine import assert_transition
from apps.organizations.models import Organization
from apps.social.adapters.base import (
    MediaFile,
    PublishRequest,
    PublishResult,
    SocialError,
)
from apps.social.adapters.registry import adapter_for
from apps.social.models import SocialAccount
from apps.social.services import account_ref, mark_needs_reauth
from apps.usage.limits import get_limits

from .models import PublishedPost, PublishingAttempt, PublishingJob

logger = logging.getLogger(__name__)
J = PublishingJob.Status

TRANSITIONS: dict[str, frozenset[str]] = {
    J.SCHEDULED: frozenset({J.QUEUED, J.CANCELLED}),
    J.QUEUED: frozenset({J.PUBLISHING, J.CANCELLED}),
    J.PUBLISHING: frozenset({J.PUBLISHED, J.QUEUED, J.FAILED, J.NEEDS_RECONCILIATION}),
    J.NEEDS_RECONCILIATION: frozenset({J.PUBLISHED, J.FAILED}),
    J.FAILED: frozenset({J.QUEUED}),
    J.PUBLISHED: frozenset(),
    J.CANCELLED: frozenset(),
}

LIVE = (J.SCHEDULED, J.QUEUED, J.PUBLISHING, J.NEEDS_RECONCILIATION)
RECONCILE_CHECKS = 3
STALE_PUBLISHING_AFTER = timedelta(minutes=10)


def _transition(job: PublishingJob, target: str) -> None:
    assert_transition("publishing job", TRANSITIONS, job.status, target)
    job.status = target


def compose_text(version: Any) -> str:
    """The exact text sent to the platform for a content version."""
    parts = [version.caption.strip()]
    if version.cta and version.cta.strip() not in version.caption:
        parts.append(version.cta.strip())
    if version.hashtags:
        parts.append(" ".join(version.hashtags))
    return "\n\n".join(p for p in parts if p)


def _set_item_status(item: ContentItem, target: str, *, actor: Any, reason: str) -> None:
    item.refresh_from_db(fields=["status"])
    if item.status != target:
        set_content_status(item, target, actor=actor, reason=reason, system=actor is None)


# --- Requesting -------------------------------------------------------------------------


def validate_publishable(item: ContentItem, account: SocialAccount) -> None:
    if account.organization_id != item.organization_id:
        raise ValidationError({"social_account": "Account not found."})
    if account.platform != item.platform:
        raise ValidationError(
            {
                "social_account": f"This is {item.get_platform_display()} content; "
                "choose a matching account."
            }
        )
    if not account.is_usable:
        raise Conflict(f"{account.name} needs to be reconnected before publishing.")
    if item.status != ContentItem.Status.APPROVED:
        raise Conflict("Only approved content can be published.")
    version = item.current_version
    if version is None:
        raise Conflict("This content has no text.")
    errors = [c["message"] for c in version.checks if c.get("severity") == "error"]
    if errors:
        raise Conflict("Fix these issues first: " + " ".join(errors))
    adapter = adapter_for(account.platform, mock=account.is_mock)
    caps = adapter.capabilities
    if item.format not in caps.publish_formats:
        raise Conflict(
            f"{caps.display_name} doesn't support {item.get_format_display()} posts yet."
        )
    media_count = item.assets.count()
    if item.format in caps.media_required_formats and media_count == 0:
        raise Conflict(f"{caps.display_name} needs an image for this format.")
    if media_count == 0 and not caps.supports_text_only:
        raise Conflict(f"{caps.display_name} doesn't allow text-only posts. Add an image.")
    if media_count > caps.max_images:
        raise Conflict(f"{caps.display_name} allows at most {caps.max_images} images.")
    if caps.image_types is not None:
        wrong = item.assets.exclude(content_type__in=caps.image_types).count()
        if wrong:
            allowed = ", ".join(sorted(t.split("/")[1].upper() for t in caps.image_types))
            raise Conflict(
                f"{caps.display_name} only accepts {allowed} images. Replace {wrong} image(s)."
            )
    if caps.requires_public_media_url and media_count and settings.STORAGE_BACKEND != "s3":
        raise Conflict(
            f"{caps.display_name} fetches images from a public URL, which needs S3 media "
            "storage. Ask an administrator to configure it."
        )


def publishes_last_24h(org: Organization) -> int:
    """Posts counted against the daily limit: requested in the last 24h and not
    cancelled or failed."""
    since = timezone.now() - timedelta(days=1)
    return (
        PublishingJob.objects.filter(organization=org, created_at__gte=since)
        .exclude(status__in=[J.CANCELLED, J.FAILED])
        .count()
    )


def _check_daily_quota(org: Organization) -> None:
    limit = get_limits(org).publishes_per_day
    if publishes_last_24h(org) >= limit:
        raise QuotaExceeded(f"Your organization can publish {limit} posts per day.")


def request_publish(
    org: Organization,
    *,
    item: ContentItem,
    account: SocialAccount,
    actor: Any,
    idempotency_key: str,
    scheduled_for: datetime | None = None,
    initiated_by: str = "user",
) -> tuple[PublishingJob, bool]:
    """Create a publishing job. Returns (job, created); repeats with the same key are no-ops."""
    existing = PublishingJob.objects.filter(
        organization=org, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.content_item_id != item.pk or existing.social_account_id != account.pk:
            raise Conflict("This idempotency key was already used for a different request.")
        return existing, False

    now = timezone.now()
    if scheduled_for is not None:
        if scheduled_for < now + timedelta(minutes=1):
            scheduled_for = None  # treat "now-ish" as immediate
        elif scheduled_for > now + timedelta(days=settings.PUBLISH_MAX_SCHEDULE_DAYS):
            raise ValidationError(
                {
                    "scheduled_for": "Schedule at most "
                    f"{settings.PUBLISH_MAX_SCHEDULE_DAYS} days ahead."
                }
            )

    with transaction.atomic():
        item = ContentItem.objects.select_for_update().get(pk=item.pk)
        validate_publishable(item, account)
        version = item.current_version
        if version is None:  # pragma: no cover - guaranteed by validate_publishable
            raise Conflict("This content has no text.")
        _check_daily_quota(org)
        from apps.automation.policy import enforce_publish_policy

        enforce_publish_policy(
            org, item=item, account=account, initiated_by=initiated_by, scheduled_for=scheduled_for
        )
        try:
            with transaction.atomic():
                job = PublishingJob.objects.create(
                    organization=org,
                    content_item=item,
                    version=version,
                    social_account=account,
                    status=J.SCHEDULED if scheduled_for else J.QUEUED,
                    scheduled_for=scheduled_for,
                    idempotency_key=idempotency_key,
                    max_attempts=settings.PUBLISH_MAX_ATTEMPTS,
                    is_mock=account.is_mock,
                    initiated_by=initiated_by,
                    created_by=actor if getattr(actor, "is_authenticated", False) else None,
                )
        except IntegrityError as exc:
            raise Conflict(
                "This content is already scheduled or published on that account."
            ) from exc
        _set_item_status(
            item, ContentItem.Status.SCHEDULED, actor=actor, reason="Publishing requested"
        )
        audit.record(
            "publishing.requested",
            organization=org,
            actor=actor,
            target=job,
            system=actor is None,
            metadata={
                "item": str(item.pk),
                "version": item.current_version.number if item.current_version else None,
                "account": str(account.pk),
                "platform": account.platform,
                "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
                "simulation": account.is_mock,
                "initiated_by": initiated_by,
            },
        )
        if job.status == J.QUEUED:
            _enqueue_on_commit(job)
    return job, True


def _enqueue_on_commit(job: PublishingJob) -> None:
    from .tasks import execute_publishing_job

    job_id = str(job.pk)
    transaction.on_commit(lambda: execute_publishing_job.delay(job_id))


# --- Executing ------------------------------------------------------------------------------


def _media_for(item: ContentItem) -> tuple[MediaFile, ...]:
    files = []
    for asset in item.assets.all():
        storage, name = asset.file.storage, asset.file.name or ""
        with storage.open(name, "rb") as fh:
            content = fh.read()
        public_url = (
            storage.url(asset.file.name) if storage.__class__.__name__ == "S3Storage" else None
        )
        files.append(
            MediaFile(
                content=content,
                content_type=asset.content_type,
                filename=name.rsplit("/", 1)[-1],
                public_url=public_url,
            )
        )
    return tuple(files)


def _begin_attempt(job_id: str) -> tuple[PublishingJob, PublishingAttempt] | None:
    with transaction.atomic():
        job = (
            PublishingJob.objects.select_for_update()
            .select_related("content_item", "version", "social_account")
            .get(pk=job_id)
        )
        now = timezone.now()
        if job.status != J.QUEUED or (job.next_attempt_at and job.next_attempt_at > now):
            return None  # already handled, cancelled, or not yet due (idempotent no-op)
        account = job.social_account
        if not account.is_usable:
            _fail(
                job,
                "reauth_required",
                f"{account.name} needs to be reconnected.",
                from_status=J.QUEUED,
            )
            return None
        if job.content_item.current_version_id != job.version_id:
            _fail(
                job,
                "content_changed",
                "The content changed after it was approved.",
                from_status=J.QUEUED,
            )
            return None
        _transition(job, J.PUBLISHING)
        job.attempts += 1
        job.last_sent_at = now
        job.next_attempt_at = None
        job.save()
        attempt = PublishingAttempt.objects.create(
            organization=job.organization, job=job, number=job.attempts, started_at=now
        )
    return job, attempt


def execute_job(job_id: str) -> None:
    begun = _begin_attempt(job_id)
    if begun is None:
        return
    job, attempt = begun
    account = job.social_account
    adapter = adapter_for(account.platform, mock=account.is_mock)
    try:
        request = PublishRequest(
            format=job.content_item.format,
            text=compose_text(job.version),
            media=_media_for(job.content_item),
            alt_text=job.version.alt_text,
        )
        result = adapter.publish(account_ref(account), request)
    except SocialError as exc:
        _handle_error(job.pk, attempt.pk, exc)
        return
    except Exception as exc:  # unexpected bug: the post may or may not have been sent
        logger.exception("Unexpected publishing error", extra={"job": str(job.pk)})
        err = SocialError("Unexpected error while publishing")
        err.code, err.uncertain = "internal_error", True
        _handle_error(job.pk, attempt.pk, err)
        del exc
        return
    _complete(job.pk, attempt.pk, result)


def _backoff(attempt: int) -> timedelta:
    base = settings.PUBLISH_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
    capped = min(base, 15 * 60)
    return timedelta(seconds=capped * random.uniform(0.8, 1.2))  # noqa: S311 - jitter, not crypto


def _close_attempt(
    attempt_id: Any, outcome: str, exc: SocialError | None = None, request_id: str = ""
) -> None:
    PublishingAttempt.objects.filter(pk=attempt_id).update(
        outcome=outcome,
        finished_at=timezone.now(),
        error_code=exc.code if exc else "",
        error_message=str(exc)[:500] if exc else "",
        request_id=(exc.request_id if exc else request_id)[:200],
    )


def _fail(job: PublishingJob, code: str, message: str, *, from_status: str) -> None:
    _transition(job, J.FAILED)
    job.error_code, job.error_message = code, message[:500]
    job.save()
    _set_item_status(
        job.content_item,
        ContentItem.Status.APPROVED,
        actor=None,
        reason=f"Publishing failed: {code}",
    )
    audit.record(
        "publishing.failed",
        organization=job.organization,
        target=job,
        system=True,
        metadata={"code": code, "attempts": job.attempts},
    )
    from apps.notifications.services import notify_publishing_failed

    notify_publishing_failed(job)


@transaction.atomic
def _handle_error(job_id: Any, attempt_id: Any, exc: SocialError) -> None:
    job = (
        PublishingJob.objects.select_for_update()
        .select_related("content_item", "social_account")
        .get(pk=job_id)
    )
    if exc.uncertain:
        _close_attempt(attempt_id, PublishingAttempt.Outcome.UNCERTAIN, exc)
        _transition(job, J.NEEDS_RECONCILIATION)
        job.error_code, job.error_message = exc.code, "Checking whether the post was published…"
        job.save()
        audit.record(
            "publishing.uncertain",
            organization=job.organization,
            target=job,
            system=True,
            metadata={"code": exc.code},
        )
        return
    if exc.needs_reauth:
        _close_attempt(attempt_id, PublishingAttempt.Outcome.PERMANENT_ERROR, exc)
        mark_needs_reauth(job.social_account, str(exc))
        _fail(
            job,
            "reauth_required",
            f"{job.social_account.name} needs to be reconnected.",
            from_status=J.PUBLISHING,
        )
        return
    if exc.retryable and job.attempts < job.max_attempts:
        _close_attempt(attempt_id, PublishingAttempt.Outcome.RETRYABLE_ERROR, exc)
        _transition(job, J.QUEUED)
        job.next_attempt_at = timezone.now() + _backoff(job.attempts)
        job.error_code, job.error_message = (
            exc.code,
            f"Temporary problem; retrying (attempt {job.attempts} of {job.max_attempts}).",
        )
        job.save()
        return
    _close_attempt(attempt_id, PublishingAttempt.Outcome.PERMANENT_ERROR, exc)
    _fail(job, exc.code, str(exc), from_status=J.PUBLISHING)


@transaction.atomic
def _complete(job_id: Any, attempt_id: Any, result: PublishResult) -> None:
    job = (
        PublishingJob.objects.select_for_update()
        .select_related("content_item", "social_account")
        .get(pk=job_id)
    )
    _close_attempt(attempt_id, PublishingAttempt.Outcome.SUCCEEDED, request_id=result.request_id)
    _record_published(job, result)


def _record_published(job: PublishingJob, result: PublishResult) -> None:
    _transition(job, J.PUBLISHED)
    now = timezone.now()
    job.external_post_id = result.external_post_id
    job.permalink = result.permalink[:500]
    job.published_at = now
    job.error_code = job.error_message = ""
    job.save()
    PublishedPost.objects.get_or_create(
        job=job,
        defaults={
            "organization": job.organization,
            "content_item": job.content_item,
            "social_account": job.social_account,
            "platform": job.social_account.platform,
            "format": job.content_item.format,
            "external_post_id": result.external_post_id,
            "permalink": result.permalink[:500],
            "published_at": now,
            "is_mock": job.is_mock,
        },
    )
    _set_item_status(job.content_item, ContentItem.Status.PUBLISHED, actor=None, reason="Published")
    audit.record(
        "publishing.published",
        organization=job.organization,
        target=job,
        system=True,
        metadata={"external_post_id": result.external_post_id, "simulation": job.is_mock},
    )


# --- Reconciliation and scheduling -------------------------------------------------------------


def reconcile_job(job_id: Any) -> None:
    """Determine the outcome of an uncertain publish without resubmitting it."""
    with transaction.atomic():
        job = (
            PublishingJob.objects.select_for_update()
            .select_related("content_item", "version", "social_account")
            .get(pk=job_id)
        )
        if job.status != J.NEEDS_RECONCILIATION:
            return
        job.reconciliation_checks += 1
        job.save(update_fields=["reconciliation_checks", "updated_at"])
    account = job.social_account
    adapter = adapter_for(account.platform, mock=account.is_mock)
    since = (job.last_sent_at or job.created_at) - timedelta(minutes=2)
    try:
        found = adapter.find_recent_post(
            account_ref(account), text=compose_text(job.version), since=since
        )
    except SocialError:
        return  # try again on the next sweep
    with transaction.atomic():
        job = (
            PublishingJob.objects.select_for_update()
            .select_related("content_item", "social_account")
            .get(pk=job_id)
        )
        if job.status != J.NEEDS_RECONCILIATION:
            return
        if found:
            _record_published(job, found)
            return
        if job.reconciliation_checks >= RECONCILE_CHECKS:
            _fail(
                job,
                "unconfirmed",
                "We couldn't confirm whether this was published. "
                "Check the account before retrying.",
                from_status=J.NEEDS_RECONCILIATION,
            )


def dispatch_due_jobs() -> int:
    """Promote due scheduled jobs and enqueue queued jobs that are ready. Safe to run often."""
    from .tasks import execute_publishing_job

    now = timezone.now()
    with transaction.atomic():
        due = list(
            PublishingJob.objects.select_for_update(skip_locked=True).filter(
                status=J.SCHEDULED, scheduled_for__lte=now
            )
        )
        for job in due:
            if job.initiated_by == "automation":
                from apps.automation.policy import is_organization_paused
                from apps.automation.services import automated_job_still_allowed

                if is_organization_paused(job.organization):
                    continue  # paused automation holds automated jobs; they stay scheduled
                if not automated_job_still_allowed(job):
                    continue  # cancelled and re-proposed under the current policy
            _transition(job, J.QUEUED)
            job.save(update_fields=["status", "updated_at"])
    ready = (
        PublishingJob.objects.filter(status=J.QUEUED)
        .exclude(next_attempt_at__gt=now)
        .values_list("pk", flat=True)
    )
    count = 0
    for job_id in ready:
        execute_publishing_job.delay(str(job_id))
        count += 1
    # Jobs stuck in "publishing" (worker died mid-call) may or may not have been sent.
    stale = PublishingJob.objects.filter(
        status=J.PUBLISHING, last_sent_at__lt=now - STALE_PUBLISHING_AFTER
    )
    for job in stale:
        with transaction.atomic():
            locked = PublishingJob.objects.select_for_update().get(pk=job.pk)
            if locked.status == J.PUBLISHING:
                _transition(locked, J.NEEDS_RECONCILIATION)
                locked.error_code = "worker_interrupted"
                locked.save()
    return count


def reconcile_due_jobs() -> int:
    cutoff = timezone.now() - timedelta(seconds=settings.PUBLISH_RECONCILE_DELAY_SECONDS)
    ids = list(
        PublishingJob.objects.filter(
            status=J.NEEDS_RECONCILIATION, updated_at__lte=cutoff
        ).values_list("pk", flat=True)
    )
    for job_id in ids:
        reconcile_job(job_id)
    return len(ids)


# --- User actions -------------------------------------------------------------------------------


@transaction.atomic
def cancel_job(job: PublishingJob, *, actor: Any, reason: str = "") -> PublishingJob:
    job = PublishingJob.objects.select_for_update().select_related("content_item").get(pk=job.pk)
    if job.status not in (J.SCHEDULED, J.QUEUED):
        raise Conflict("Only scheduled or queued posts can be cancelled.")
    _transition(job, J.CANCELLED)
    job.error_message = reason[:500]
    job.save()
    if not PublishingJob.objects.filter(
        content_item=job.content_item, status__in=[*LIVE, J.PUBLISHED]
    ).exists():
        _set_item_status(
            job.content_item,
            ContentItem.Status.APPROVED,
            actor=actor,
            reason="Publishing cancelled",
        )
    audit.record(
        "publishing.cancelled",
        organization=job.organization,
        actor=actor,
        target=job,
        metadata={"reason": reason[:200]},
    )
    return job


@transaction.atomic
def retry_job(
    job: PublishingJob, *, actor: Any, confirm_not_published: bool = False
) -> PublishingJob:
    job = (
        PublishingJob.objects.select_for_update()
        .select_related("content_item", "social_account")
        .get(pk=job.pk)
    )
    if job.status != J.FAILED:
        raise Conflict("Only failed posts can be retried.")
    if (
        job.error_code in {"unconfirmed", "outcome_unknown", "internal_error"}
        and not confirm_not_published
    ):
        raise Conflict(
            "Confirm you've checked the account and the post isn't there, to avoid posting twice."
        )
    item = ContentItem.objects.select_for_update().get(pk=job.content_item_id)
    if item.current_version_id != job.version_id:
        raise Conflict("The content changed since this job was created. Publish it again instead.")
    validate_publishable(item, job.social_account)
    _transition(job, J.QUEUED)
    job.attempts, job.reconciliation_checks = 0, 0
    job.next_attempt_at = None
    job.error_code = job.error_message = ""
    job.save()
    _set_item_status(item, ContentItem.Status.SCHEDULED, actor=actor, reason="Publishing retried")
    audit.record("publishing.retried", organization=job.organization, actor=actor, target=job)
    _enqueue_on_commit(job)
    return job


def cancel_pending_for_account(account: SocialAccount, *, actor: Any, reason: str) -> int:
    count = 0
    for job in PublishingJob.objects.filter(
        social_account=account, status__in=[J.SCHEDULED, J.QUEUED]
    ):
        cancel_job(job, actor=actor, reason=reason)
        count += 1
    return count
