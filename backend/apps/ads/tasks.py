from typing import Any

from celery import shared_task

from . import services
from .models import AdAccount


@shared_task(name="ads.sync_due")
def sync_due() -> int:
    return services.sync_due_accounts()


@shared_task(name="ads.sync_account")
def sync_ad_account(account_id: str, trigger: str = "schedule") -> dict[str, Any] | None:
    account = (
        AdAccount.objects.filter(pk=account_id, status=AdAccount.Status.CONNECTED)
        .select_related("meta_connection")
        .first()
    )
    if account is None:
        return None
    run = services.sync_account(account, trigger=trigger)
    return {"status": run.status, "counts": run.counts}


@shared_task(name="ads.optimize")
def optimize() -> dict[str, int]:
    from .optimizer import run_for_all

    return run_for_all()
