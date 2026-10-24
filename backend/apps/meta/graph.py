"""Versioned client for Meta's Graph API and Marketing API.

Every call to Meta goes through ``GraphClient``; nothing else in the application builds
Graph URLs. The client:

- pins the API version (``META_GRAPH_VERSION``);
- signs every token-bearing call with ``appsecret_proof`` (HMAC-SHA256 of the token with
  the app secret), so a leaked token alone can't be used against our app;
- follows cursor pagination (``paging.next``) up to a page limit;
- reads Meta's usage headers (``X-App-Usage``, ``X-Business-Use-Case-Usage``,
  ``X-Ad-Account-Usage``) and stops calling for a while once usage approaches the limit,
  instead of waiting to be blocked;
- normalizes Meta errors into the integration error types in
  ``apps.social.adapters.base`` (retry, reconnect, rejected, uncertain).

Tokens are passed per call and never logged. Based on Meta's Graph API / Marketing API
documentation (v26.0) as reviewed on 2026-10-23; not yet exercised against the live API.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.social.adapters.base import (
    ContentRejected,
    NotConfigured,
    PermissionMissing,
    RateLimited,
    ReauthRequired,
    SocialError,
    TransientError,
    UncertainOutcome,
)

logger = logging.getLogger(__name__)

GRAPH_HOST = "https://graph.facebook.com"
DIALOG_HOST = "https://www.facebook.com"

# https://developers.facebook.com/docs/graph-api/guides/error-handling
_AUTH_CODES = {102, 190}
_AUTH_SUBCODES = {458, 459, 460, 463, 464, 467, 492}
_PERMISSION_CODES = {10, *range(200, 300)}
_RATE_LIMIT_CODES = {4, 17, 32, 613, *range(80000, 80015)}
_TRANSIENT_CODES = {1, 2}

#: Test hook: when set, clients built from settings use this transport (no network).
TRANSPORT: httpx.BaseTransport | None = None

_THROTTLE_PREFIX = "meta:throttle:"
_DEFAULT_THROTTLE_SECONDS = 300


class GraphClient:
    def __init__(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        version: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.version = version
        self.base = f"{GRAPH_HOST}/{version}"
        self.dialog = f"{DIALOG_HOST}/{version}/dialog/oauth"
        self._http = httpx.Client(timeout=timeout_seconds, transport=transport)

    @classmethod
    def from_settings(cls, transport: httpx.BaseTransport | None = None) -> "GraphClient":
        return cls(
            app_id=settings.META_APP_ID,
            app_secret=settings.META_APP_SECRET,
            version=settings.META_GRAPH_VERSION,
            timeout_seconds=settings.SOCIAL_HTTP_TIMEOUT_SECONDS,
            transport=transport or TRANSPORT,
        )

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def require_config(self) -> None:
        if not self.is_configured():
            raise NotConfigured("META_APP_ID and META_APP_SECRET are not set.")

    def appsecret_proof(self, token: str) -> str:
        self.require_config()
        secret = str(self.app_secret)
        return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    # --- Requests ------------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        write: bool = False,
        throttle_key: str | None = None,
    ) -> dict[str, Any]:
        """One Graph call. ``write`` marks requests whose effect may persist even if the
        response is lost (their timeouts become ``UncertainOutcome``)."""
        self._check_throttle(throttle_key)
        url = _strip_auth(path) if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        params = dict(params or {})
        if "?" in url:
            # httpx replaces a URL's query when ``params`` is given; keep both.
            from urllib.parse import parse_qsl

            url, query = url.split("?", 1)
            params = {**dict(parse_qsl(query, keep_blank_values=True)), **params}
        body = dict(data) if data is not None else None
        if token:
            auth = {"access_token": token}
            if self.app_secret:
                auth["appsecret_proof"] = self.appsecret_proof(token)
            if body is not None:
                body.update(auth)
            else:
                params.update(auth)
        try:
            response = self._http.request(method, url, params=params, data=body, files=files)
        except httpx.TimeoutException as exc:
            if write:
                raise UncertainOutcome("Timed out waiting for Meta") from exc
            raise TransientError("Timed out waiting for Meta") from exc
        except httpx.TransportError as exc:
            if write and not isinstance(exc, httpx.ConnectError):
                raise UncertainOutcome("Connection to Meta dropped during a write") from exc
            raise TransientError("Could not reach Meta") from exc

        trace = response.headers.get("x-fb-trace-id", "")
        self._record_usage(response.headers, throttle_key)
        try:
            payload: Any = response.json()
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"data": payload}
        result: dict[str, Any] = payload
        if response.status_code >= 500 and "error" not in payload:
            raise TransientError(f"Meta returned {response.status_code}", request_id=trace)
        if "error" in payload or response.status_code >= 400:
            error = normalize_error(payload.get("error") or {}, response.status_code, trace)
            if isinstance(error, RateLimited):
                self._throttle(throttle_key, error.retry_after_seconds)
            logger.info(
                "Meta API error",
                extra={
                    "path": _redact_path(path),
                    "status": response.status_code,
                    "error_code": error.code,
                    "fbtrace_id": trace,
                },
            )
            raise error
        return result

    def paginate(
        self,
        path: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 25,
        throttle_key: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every item across cursor pages (``data`` + ``paging.next``)."""
        next_url: str | None = path
        page_params: dict[str, Any] | None = params
        for _ in range(max_pages):
            if not next_url:
                return
            body = self.request(
                "GET", next_url, token=token, params=page_params, throttle_key=throttle_key
            )
            yield from body.get("data", [])
            next_url = (body.get("paging") or {}).get("next")
            # The ``next`` URL already carries every query parameter except the proof,
            # which ``request`` adds again from the token.
            page_params = None
        logger.warning("Stopped paginating after %s pages", max_pages, extra={"path": path})

    # --- Usage-based throttling ----------------------------------------------------------

    def _check_throttle(self, key: str | None) -> None:
        for k in ("app", key):
            if k and (until := cache.get(_THROTTLE_PREFIX + k)):
                raise RateLimited(
                    "Meta usage limit reached; calls are paused briefly.",
                    retry_after_seconds=int(until),
                )

    def _throttle(self, key: str | None, seconds: int | None) -> None:
        seconds = max(60, seconds or _DEFAULT_THROTTLE_SECONDS)
        cache.set(_THROTTLE_PREFIX + (key or "app"), seconds, timeout=seconds)

    def _record_usage(self, headers: httpx.Headers, key: str | None) -> None:
        threshold = settings.META_USAGE_THROTTLE_PERCENT
        app = _json_header(headers.get("x-app-usage"))
        if app and _max_pct(app) >= threshold:
            self._throttle("app", None)
        buc = _json_header(headers.get("x-business-use-case-usage"))
        if isinstance(buc, dict):
            for entries in buc.values():
                for entry in entries if isinstance(entries, list) else []:
                    if _max_pct(entry) >= threshold:
                        wait = int(entry.get("estimated_time_to_regain_access") or 0) * 60
                        self._throttle(key, wait or None)
        account = _json_header(headers.get("x-ad-account-usage"))
        if account and float(account.get("acc_id_util_pct") or 0) >= threshold:
            self._throttle(key, int(account.get("reset_time_duration") or 0) or None)


def normalize_error(error: dict[str, Any], status: int, trace: str = "") -> SocialError:
    code = error.get("code")
    subcode = error.get("error_subcode")
    # Marketing API errors carry a user-facing title/message worth showing as-is.
    message = str(error.get("error_user_msg") or error.get("message") or f"Meta error {status}")[
        :300
    ]
    if code in _AUTH_CODES or subcode in _AUTH_SUBCODES:
        return ReauthRequired(message, request_id=trace)
    if code in _PERMISSION_CODES:
        return PermissionMissing(f"Missing permission: {message}", request_id=trace)
    if code in _RATE_LIMIT_CODES or status == 429:
        return RateLimited(message, request_id=trace)
    if code in _TRANSIENT_CODES or error.get("is_transient"):
        return TransientError(message, request_id=trace)
    return ContentRejected(message, request_id=trace)


def _json_header(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _max_pct(usage: dict[str, Any]) -> float:
    keys = ("call_count", "total_cputime", "total_time")
    return max((float(usage.get(k) or 0) for k in keys), default=0.0)


def _strip_auth(url: str) -> str:
    """Remove token parameters from a Meta-provided URL (e.g. ``paging.next``); the
    client re-adds the current token and its proof."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in {"access_token", "appsecret_proof"}
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _redact_path(path: str) -> str:
    """Paths are logged without query strings (which may carry tokens)."""
    return path.split("?", 1)[0]
