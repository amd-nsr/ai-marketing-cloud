from celery import shared_task
from django.conf import settings

from . import workflows

# The soft limit raises inside the handler, so the run is marked failed with a clear error;
# the hard limit kills a stuck process, and the operations sweeper then fails the run.
_HARD_LIMIT = settings.AI_RUN_TIMEOUT_MINUTES * 60


@shared_task(
    name="ai.execute_workflow_run",
    acks_late=True,
    soft_time_limit=_HARD_LIMIT - 60,
    time_limit=_HARD_LIMIT,
)
def execute_workflow_run(run_id: str) -> None:
    workflows.execute(run_id)
