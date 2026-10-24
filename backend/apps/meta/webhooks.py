"""Processing of verified Meta webhook deliveries.

Handled: ``ad_account`` changes (campaign/ad issues, status changes) trigger a sync of
the matching connected ad account; ``user`` ``permissions`` changes re-read the
person's grants. Other objects (e.g. ``page`` feed) are stored for later use.
Webhook payloads never contain tokens.
"""

from typing import Any

from django.utils import timezone

from .models import MetaConnection, MetaWebhookEvent


def process_delivery(payload: dict[str, Any]) -> int:
    obj = str(payload.get("object", ""))[:40]
    stored = 0
    for entry in payload.get("entry", []) or []:
        entry_id = str(entry.get("id", ""))[:64]
        for change in entry.get("changes", []) or [{"field": "", "value": entry}]:
            event = MetaWebhookEvent.objects.create(
                object=obj,
                field=str(change.get("field", ""))[:80],
                entry_id=entry_id,
                payload={"change": change, "time": entry.get("time")},
            )
            event.result = _handle(obj, event.field, entry_id)
            event.processed_at = timezone.now()
            event.save(update_fields=["result", "processed_at", "updated_at"])
            stored += 1
    return stored


def _handle(obj: str, field: str, entry_id: str) -> str:
    if obj == "ad_account":
        from apps.ads.models import AdAccount
        from apps.ads.tasks import sync_ad_account

        ids = list(
            AdAccount.objects.filter(
                external_id__in=[entry_id, f"act_{entry_id}"], status=AdAccount.Status.CONNECTED
            ).values_list("pk", flat=True)
        )
        for pk in ids:
            sync_ad_account.delay(str(pk))
        return f"sync queued for {len(ids)} ad account(s)"
    if obj == "user" and field == "permissions":
        from .tasks import refresh_connection_task

        ids = list(
            MetaConnection.objects.filter(
                meta_user_id=entry_id, status=MetaConnection.Status.ACTIVE
            ).values_list("pk", flat=True)
        )
        for pk in ids:
            refresh_connection_task.delay(str(pk))
        return f"permissions refresh queued for {len(ids)} connection(s)"
    return "stored"
