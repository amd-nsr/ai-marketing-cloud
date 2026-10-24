"""Verification of requests Meta sends to us (no user session involved).

- ``signed_request`` (deauthorize and data-deletion callbacks): ``<sig>.<payload>``, both
  base64url; ``sig`` is HMAC-SHA256 of the raw payload segment keyed with the app secret.
- Webhooks: ``X-Hub-Signature-256: sha256=<hex>`` = HMAC-SHA256 of the raw body.
- Webhook subscription check: ``hub.mode=subscribe`` with our verify token → echo
  ``hub.challenge``.
"""

import base64
import hashlib
import hmac
import json
from typing import Any

from django.conf import settings


class InvalidSignature(Exception):
    pass


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def parse_signed_request(signed_request: str, *, app_secret: str | None = None) -> dict[str, Any]:
    secret = app_secret or settings.META_APP_SECRET
    if not secret:
        raise InvalidSignature("META_APP_SECRET is not set.")
    try:
        encoded_sig, payload = signed_request.split(".", 1)
        signature = _b64url_decode(encoded_sig)
        data = json.loads(_b64url_decode(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidSignature("Malformed signed_request.") from exc
    if str(data.get("algorithm", "")).upper() != "HMAC-SHA256":
        raise InvalidSignature("Unexpected signing algorithm.")
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise InvalidSignature("Signature mismatch.")
    if not data.get("user_id"):
        raise InvalidSignature("No user in signed_request.")
    return dict(data)


def verify_webhook_signature(
    body: bytes, header: str | None, *, app_secret: str | None = None
) -> None:
    secret = app_secret or settings.META_APP_SECRET
    if not secret:
        raise InvalidSignature("META_APP_SECRET is not set.")
    if not header or not header.startswith("sha256="):
        raise InvalidSignature("Missing signature.")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(header.removeprefix("sha256="), expected):
        raise InvalidSignature("Signature mismatch.")


def verify_subscription(params: dict[str, str]) -> str | None:
    """Return the challenge to echo if this is our subscription check, else None."""
    token = settings.META_WEBHOOK_VERIFY_TOKEN
    if (
        token
        and params.get("hub.mode") == "subscribe"
        and hmac.compare_digest(params.get("hub.verify_token", ""), token)
    ):
        return params.get("hub.challenge", "")
    return None
