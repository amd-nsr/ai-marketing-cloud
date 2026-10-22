from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class MetricSnapshot(OrganizationOwnedModel):
    """One metric value for one published post, as reported by the platform at a time.

    ``value`` is NULL when the platform did not report the metric: that is "missing",
    never zero.
    """

    published_post = models.ForeignKey(
        "publishing.PublishedPost", on_delete=models.CASCADE, related_name="metric_snapshots"
    )
    platform = models.CharField(max_length=16)
    metric_key = models.CharField(max_length=40)
    value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=20, default="count")
    period = models.CharField(max_length=20, default="lifetime")
    retrieved_at = models.DateTimeField()
    #: Where the number came from: "facebook", "instagram", "tiktok" or "simulation".
    source = models.CharField(max_length=20)
    is_mock = models.BooleanField(default=False)

    class Meta:
        ordering = ["-retrieved_at"]
        indexes = [
            models.Index(fields=["published_post", "metric_key", "-retrieved_at"]),
            models.Index(fields=["organization", "platform", "metric_key"]),
        ]


class MarketingRecommendation(OrganizationOwnedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        ACCEPTED = "accepted", "Accepted"
        DISMISSED = "dismissed", "Dismissed"

    class Kind(models.TextChoices):
        FORMAT_PERFORMANCE = "format_performance", "Format performance"
        TOP_POST = "top_post", "Top post"
        POSTING_GAP = "posting_gap", "Posting consistency"
        ACCOUNT_REAUTH = "account_reauth", "Account needs attention"
        STALE_APPROVALS = "stale_approvals", "Waiting approvals"
        PUBLISHING_FAILURES = "publishing_failures", "Publishing failures"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    #: Dedupe key: one live recommendation per kind+subject.
    fingerprint = models.CharField(max_length=200)
    priority = models.PositiveSmallIntegerField(default=2)  # 1 high, 3 low
    title = models.CharField(max_length=200)
    observation = models.TextField(max_length=2000)  # what the data shows
    rationale = models.TextField(max_length=2000)  # why we suggest acting
    suggested_action = models.TextField(max_length=1000)
    uncertainty = models.TextField(max_length=1000, blank=True)  # what we don't know
    link = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    #: Evidence comes (partly) from simulation accounts.
    uses_simulated_data = models.BooleanField(default=False)
    generated_at = models.DateTimeField()
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["priority", "-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "fingerprint"], name="uniq_recommendation_fingerprint"
            )
        ]


class RecommendationEvidence(OrganizationOwnedModel):
    recommendation = models.ForeignKey(
        MarketingRecommendation, on_delete=models.CASCADE, related_name="evidence"
    )
    description = models.CharField(max_length=300)
    platform = models.CharField(max_length=16, blank=True)
    metric_key = models.CharField(max_length=40, blank=True)
    value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    baseline = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    sample_size = models.PositiveIntegerField(null=True, blank=True)
    published_post = models.ForeignKey(
        "publishing.PublishedPost",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["created_at"]
