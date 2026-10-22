from celery import shared_task

from . import services


@shared_task(name="publishing.execute_job", acks_late=True)
def execute_publishing_job(job_id: str) -> None:
    services.execute_job(job_id)


@shared_task(name="publishing.dispatch_due")
def dispatch_due_publishing_jobs() -> int:
    return services.dispatch_due_jobs()


@shared_task(name="publishing.reconcile")
def reconcile_publishing_jobs() -> int:
    return services.reconcile_due_jobs()
