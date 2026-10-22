from typing import Any

from celery import shared_task

from . import heartbeat, sweeper


@shared_task(name="operations.heartbeat", ignore_result=True)
def record_heartbeat() -> None:
    heartbeat.beat()


@shared_task(name="operations.sweep")
def sweep_stuck_work() -> dict[str, Any]:
    return sweeper.sweep()
