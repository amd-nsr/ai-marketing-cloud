"""Finds background work that stopped making progress and resolves it visibly.

- AI runs queued too long are re-submitted once they look lost (execution is idempotent),
  and failed if they never start.
- AI runs "running" past the timeout are failed with `timed_out` (a late, real result still
  wins: see apps.ai.workflows._finish).
- Automation actions stuck in "executing" are resolved from what actually happened: if the
  publishing job exists the action succeeded, otherwise it failed as interrupted.

Publishing jobs stuck mid-send are handled by the publishing engine (needs_reconciliation),
never re-sent from here.
"""

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

logger = logging.getLogger(__name__)


def sweep_ai_runs() -> dict[str, int]:
    from apps.ai.models import AIWorkflowRun
    from apps.ai.tasks import execute_workflow_run

    R = AIWorkflowRun.Status
    now = timezone.now()
    counts = {"resubmitted": 0, "never_started": 0, "timed_out": 0}

    queued = AIWorkflowRun.objects.filter(status=R.QUEUED)
    for run in queued.filter(
        created_at__lt=now - timedelta(minutes=settings.AI_RUN_QUEUE_TIMEOUT_MINUTES)
    ):
        if _fail_run(run.pk, R.QUEUED, "never_started", "This job never started. Please retry."):
            counts["never_started"] += 1
    for run_id in queued.filter(
        created_at__lt=now - timedelta(minutes=settings.AI_RUN_RESUBMIT_AFTER_MINUTES)
    ).values_list("pk", flat=True):
        execute_workflow_run.delay(str(run_id))
        counts["resubmitted"] += 1

    for run in AIWorkflowRun.objects.filter(
        status=R.RUNNING,
        started_at__lt=now - timedelta(minutes=settings.AI_RUN_TIMEOUT_MINUTES),
    ):
        if _fail_run(
            run.pk, R.RUNNING, "timed_out", "This job took too long and was stopped. Please retry."
        ):
            counts["timed_out"] += 1
    return counts


def _fail_run(run_id: Any, expected: str, code: str, message: str) -> bool:
    from apps.ai.models import AIWorkflowRun

    with transaction.atomic():
        run = AIWorkflowRun.objects.select_for_update().get(pk=run_id)
        if run.status != expected:
            return False
        run.status = AIWorkflowRun.Status.FAILED
        run.error_code, run.error_message = code, message
        run.finished_at = timezone.now()
        run.save()
    logger.warning("Swept AI run", extra={"run_id": str(run_id), "error_code": code})
    audit.record(
        "ai_workflow.failed",
        organization=run.organization,
        target=run,
        system=True,
        metadata={"workflow": run.workflow, "error_code": code, "swept": True},
    )
    return True


def sweep_automation_actions() -> dict[str, int]:
    from apps.automation.models import AutomationAction
    from apps.publishing.models import PublishingJob

    A = AutomationAction.Status
    cutoff = timezone.now() - timedelta(minutes=settings.AUTOMATION_ACTION_STUCK_MINUTES)
    counts = {"recovered": 0, "interrupted": 0}
    for action_id in AutomationAction.objects.filter(
        status=A.EXECUTING, updated_at__lt=cutoff
    ).values_list("pk", flat=True):
        with transaction.atomic():
            action = AutomationAction.objects.select_for_update().get(pk=action_id)
            if action.status != A.EXECUTING:
                continue
            job = PublishingJob.objects.filter(
                organization=action.organization, idempotency_key=f"automation:{action.pk}"
            ).first()
            if action.ad_campaign_id is not None:
                # Ad writes: what reached Meta is unknown here. Fail visibly; a creation
                # keeps its saved progress, so a retry resumes and re-checks by name tag.
                from apps.ads.models import AdCampaign

                AdCampaign.objects.filter(
                    pk=action.ad_campaign_id, state=AdCampaign.State.CREATING
                ).update(
                    state=AdCampaign.State.FAILED,
                    last_error="Interrupted. Retry to resume; the next sync shows what exists.",
                )
                action.status = A.FAILED
                action.error = (
                    "The ad change was interrupted. The next sync shows what Meta applied; "
                    "retry if it's missing."
                )
                counts["interrupted"] += 1
            elif job is not None:
                action.publishing_job = job
                action.status = A.SUCCEEDED
                action.executed_at = action.executed_at or timezone.now()
                counts["recovered"] += 1
            else:
                action.status = A.FAILED
                action.error = (
                    "The action was interrupted before it finished. Check the content and "
                    "propose it again if needed."
                )
                counts["interrupted"] += 1
            action.save()
        audit.record(
            "automation.action_swept",
            organization=action.organization,
            target=action,
            system=True,
            metadata={"status": action.status},
        )
    return counts


def sweep() -> dict[str, dict[str, int]]:
    result = {"ai_runs": sweep_ai_runs(), "automation_actions": sweep_automation_actions()}
    if any(v for group in result.values() for v in group.values()):
        logger.info("Sweeper resolved stuck work", extra={"result": result})
    return result
