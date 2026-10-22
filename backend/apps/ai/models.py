from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class AIWorkflowRun(OrganizationOwnedModel):
    """A durable, asynchronous AI job (e.g. "generate a marketing plan").

    Created by the API, executed by a Celery worker, polled by the client.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    workflow = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    input = models.JSONField(default=dict, blank=True)
    #: Small JSON summary of the result; domain objects hold the real output.
    output = models.JSONField(default=dict, blank=True)
    result_type = models.CharField(max_length=60, blank=True)
    result_id = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    model = models.CharField(max_length=80, blank=True)
    is_mock = models.BooleanField(default=False)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "workflow", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.SUCCEEDED, self.Status.FAILED, self.Status.CANCELLED}


class AIUsageRecord(OrganizationOwnedModel):
    """One provider call: who, what, which model, how many tokens, estimated cost."""

    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=80)
    operation = models.CharField(max_length=80)
    workflow_run = models.ForeignKey(
        AIWorkflowRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_records",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    #: Estimate from configured list prices, not an invoice amount.
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    currency = models.CharField(max_length=3, default="USD")
    success = models.BooleanField()
    error_code = models.CharField(max_length=60, blank=True)
    request_id = models.CharField(max_length=120, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    is_mock = models.BooleanField(default=False)
    served_by_fallback = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "created_at"])]
