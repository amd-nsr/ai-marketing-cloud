"""Durable asynchronous AI workflows.

A workflow is a plain function registered under a name. ``start_workflow`` persists an
``AIWorkflowRun`` and enqueues it; the Celery task executes the registered handler with
explicit state transitions. Handlers return ``(result_type, result_id, summary)``.
"""

import logging
from collections.abc import Callable
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.errors import ServiceUnavailable
from apps.organizations.models import Organization

from .models import AIWorkflowRun
from .providers.base import AIProviderError
from .providers.registry import get_provider

logger = logging.getLogger(__name__)

WorkflowResult = tuple[str, str, dict[str, Any]]
WorkflowHandler = Callable[[AIWorkflowRun], WorkflowResult]
_HANDLERS: dict[str, WorkflowHandler] = {}


def register_workflow(name: str) -> Callable[[WorkflowHandler], WorkflowHandler]:
    def decorator(fn: WorkflowHandler) -> WorkflowHandler:
        _HANDLERS[name] = fn
        return fn

    return decorator


def start_workflow(
    org: Organization, workflow: str, *, user: Any, payload: dict[str, Any]
) -> AIWorkflowRun:
    if workflow not in _HANDLERS:
        raise ValueError(f"Unknown workflow {workflow}")
    try:
        provider = get_provider()
    except AIProviderError as exc:
        raise ServiceUnavailable(exc.user_message) from exc
    run = AIWorkflowRun.objects.create(
        organization=org,
        workflow=workflow,
        input=payload,
        created_by=user,
        provider=provider.name,
        model=provider.model,
        is_mock=provider.is_mock,
    )
    audit.record(
        "ai_workflow.started",
        organization=org,
        actor=user,
        target=run,
        metadata={"workflow": workflow, "provider": provider.name, "model": provider.model},
    )
    from .tasks import execute_workflow_run

    transaction.on_commit(lambda: execute_workflow_run.delay(str(run.id)))
    return run


def execute(run_id: str) -> None:
    """Run one workflow. Idempotent: terminal or already-running runs are skipped."""
    with transaction.atomic():
        run = AIWorkflowRun.objects.select_for_update().get(pk=run_id)
        if run.status != AIWorkflowRun.Status.QUEUED:
            logger.info("Skipping workflow run in status %s", run.status, extra={"run_id": run_id})
            return
        run.status = AIWorkflowRun.Status.RUNNING
        run.started_at = timezone.now()
        run.attempts += 1
        run.save(update_fields=["status", "started_at", "attempts", "updated_at"])

    handler = _HANDLERS.get(run.workflow)
    if handler is None:
        # e.g. a worker running older code; fail visibly instead of hanging in "running".
        logger.error(
            "No handler registered for workflow %s", run.workflow, extra={"run_id": run_id}
        )
        _finish(
            run,
            failed=True,
            code="workflow_unavailable",
            message="This job type isn't available. Please retry.",
        )
        return
    try:
        result_type, result_id, summary = handler(run)
    except AIProviderError as exc:
        _finish(run, failed=True, code=exc.code, message=exc.user_message)
        return
    except Exception as exc:
        logger.exception(
            "Workflow handler crashed", extra={"run_id": run_id, "workflow": run.workflow}
        )
        code = getattr(exc, "default_code", "workflow_error")
        detail = getattr(exc, "detail", None)
        message = (
            str(detail) if detail else "Something went wrong while generating. Please try again."
        )
        _finish(run, failed=True, code=str(code), message=message[:500])
        return
    run.result_type, run.result_id, run.output = result_type, result_id, summary
    _finish(run, failed=False)


def _finish(run: AIWorkflowRun, *, failed: bool, code: str = "", message: str = "") -> None:
    with transaction.atomic():
        current = AIWorkflowRun.objects.select_for_update().values_list("status", flat=True)
        status = current.get(pk=run.pk)
        if status != AIWorkflowRun.Status.RUNNING and failed:
            # Already finalized elsewhere (e.g. timed out by the sweeper); keep that outcome.
            return
        # A late success after a timeout still wins: the result exists and is real.
        _save_outcome(run, failed=failed, code=code, message=message)


def _save_outcome(run: AIWorkflowRun, *, failed: bool, code: str, message: str) -> None:
    run.status = AIWorkflowRun.Status.FAILED if failed else AIWorkflowRun.Status.SUCCEEDED
    run.error_code, run.error_message = code, message
    run.finished_at = timezone.now()
    run.save()
    audit.record(
        "ai_workflow.failed" if failed else "ai_workflow.succeeded",
        organization=run.organization,
        target=run,
        system=True,
        metadata={"workflow": run.workflow, "error_code": code}
        if failed
        else {"workflow": run.workflow},
    )
