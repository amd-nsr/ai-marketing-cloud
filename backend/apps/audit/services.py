import logging
from typing import Any

from django.db import models
from django.http import HttpRequest

from apps.core.request_context import request_id_var

from .models import AuditEvent

logger = logging.getLogger("audit")

_SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", "secret", "api_key"}


def _client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(
    action: str,
    *,
    organization: Any = None,
    actor: Any = None,
    target: models.Model | None = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
    system: bool = False,
) -> AuditEvent:
    """Persist an audit event and mirror it to the structured log."""
    clean = {k: v for k, v in (metadata or {}).items() if k.lower() not in _SENSITIVE_KEYS}
    actor_obj = actor if actor is not None and getattr(actor, "is_authenticated", False) else None
    event = AuditEvent.objects.create(
        organization=organization,
        actor=actor_obj,
        actor_type=AuditEvent.ActorType.SYSTEM if system else AuditEvent.ActorType.USER,
        action=action,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        metadata=clean,
        ip_address=_client_ip(request),
        request_id=request_id_var.get() if request_id_var.get() != "-" else "",
    )
    logger.info(
        "audit",
        extra={
            "audit_action": action,
            "organization_id": str(organization.pk) if organization is not None else None,
            "actor_id": str(actor_obj.pk) if actor_obj is not None else None,
            "target": f"{event.target_type}:{event.target_id}",
        },
    )
    return event
