import contextlib
from typing import Any

from celery import shared_task

from apps.core.errors import Conflict

from . import services
from .models import MetaConnection


@shared_task(name="meta.check_connections")
def check_connections() -> dict[str, Any]:
    return services.check_connections()


@shared_task(name="meta.refresh_connection")
def refresh_connection_task(connection_id: str) -> None:
    connection = MetaConnection.objects.filter(pk=connection_id).first()
    if connection is None or not connection.is_usable:
        return
    with contextlib.suppress(Conflict):  # the error is recorded on the connection
        services.refresh_connection(connection)
