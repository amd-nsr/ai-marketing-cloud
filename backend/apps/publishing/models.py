from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class PublishingJob(OrganizationOwnedModel):
    """A durable request to publish one approved content version to one account.

    Lifecycle::

        scheduled ──(due)──▶ queued ──▶ publishing ──▶ published
            │                  ▲  │          │
            ▼                  │  ▼          ├──▶ failed (permanent / retries exhausted)
        cancelled ◀────────────┘ cancelled   └──▶ needs_reconciliation ──▶ published | failed

    ``needs_reconciliation`` means the platform may have received the post (e.g. timeout
    after sending). The job is never resubmitted automatically from that state.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        QUEUED = "queued", "Queued"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        NEEDS_RECONCILIATION = "needs_reconciliation", "Checking outcome"

    content_item = models.ForeignKey(
        "content.ContentItem", on_delete=models.PROTECT, related_name="publishing_jobs"
    )
    #: The exact approved version being published.
    version = models.ForeignKey(
        "content.ContentVersion", on_delete=models.PROTECT, related_name="+"
    )
    social_account = models.ForeignKey(
        "social.SocialAccount", on_delete=models.PROTECT, related_name="publishing_jobs"
    )
    status = models.CharField(max_length=24, choices=Status.choices)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=100)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=4)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    #: When the most recent attempt started sending (bounds reconciliation lookups).
    last_sent_at = models.DateTimeField(null=True, blank=True)
    reconciliation_checks = models.PositiveSmallIntegerField(default=0)
    external_post_id = models.CharField(max_length=200, blank=True)
    permalink = models.URLField(max_length=500, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    is_mock = models.BooleanField(default=False)
    #: Who or what initiated the publish (user, or the automation engine).
    initiated_by = models.CharField(max_length=16, default="user")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="uniq_publish_idempotency_key"
            ),
            # Never two live jobs for the same content on the same account.
            models.UniqueConstraint(
                fields=["content_item", "social_account"],
                condition=models.Q(
                    status__in=[
                        "scheduled",
                        "queued",
                        "publishing",
                        "needs_reconciliation",
                        "published",
                    ]
                ),
                name="uniq_live_job_per_item_account",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["organization", "-created_at"]),
        ]


class PublishingAttempt(OrganizationOwnedModel):
    class Outcome(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUCCEEDED = "succeeded", "Succeeded"
        RETRYABLE_ERROR = "retryable_error", "Temporary error"
        PERMANENT_ERROR = "permanent_error", "Permanent error"
        UNCERTAIN = "uncertain", "Outcome unknown"

    job = models.ForeignKey(PublishingJob, on_delete=models.CASCADE, related_name="attempt_log")
    number = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.IN_PROGRESS)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    request_id = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["job", "number"], name="uniq_attempt_number")
        ]


class PublishedPost(OrganizationOwnedModel):
    """A post that exists on a platform. Metrics attach here."""

    job = models.OneToOneField(
        PublishingJob, on_delete=models.PROTECT, related_name="published_post"
    )
    content_item = models.ForeignKey(
        "content.ContentItem", on_delete=models.PROTECT, related_name="+"
    )
    social_account = models.ForeignKey(
        "social.SocialAccount", on_delete=models.PROTECT, related_name="+"
    )
    platform = models.CharField(max_length=16)
    format = models.CharField(max_length=16)
    external_post_id = models.CharField(max_length=200)
    permalink = models.URLField(max_length=500, blank=True)
    published_at = models.DateTimeField()
    is_mock = models.BooleanField(default=False)
    metrics_last_collected_at = models.DateTimeField(null=True, blank=True)
    #: "ok", "unsupported" (platform/integration offers no metrics), or an error code.
    metrics_status = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-published_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["social_account", "external_post_id"], name="uniq_published_external_id"
            )
        ]
        indexes = [models.Index(fields=["organization", "-published_at"])]
