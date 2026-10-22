"""Background-processing heartbeat.

Beat enqueues `operations.heartbeat` every minute and a worker records the time. A recent
heartbeat therefore proves that the scheduler, the broker and at least one worker all work.
"""

from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

HEARTBEAT_KEY = "operations:heartbeat"


def beat() -> None:
    cache.set(HEARTBEAT_KEY, timezone.now().isoformat(), timeout=None)


def status() -> dict[str, Any]:
    raw = cache.get(HEARTBEAT_KEY)
    if not raw:
        return {"status": "unknown", "last_heartbeat_at": None, "age_seconds": None}
    last = datetime.fromisoformat(raw)
    age = int((timezone.now() - last).total_seconds())
    healthy = age <= settings.OPERATIONS_HEARTBEAT_STALE_SECONDS
    return {"status": "ok" if healthy else "stale", "last_heartbeat_at": last, "age_seconds": age}
