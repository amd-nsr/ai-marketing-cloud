"""Facebook Pages integration (Graph API).

Based on Meta's documentation as reviewed on 2026-10-20 (Graph API v26.0):
- Facebook Login manual flow: /dialog/oauth -> /oauth/access_token (code exchange),
  then fb_exchange_token for a ~60-day user token; GET /me/accounts returns Page
  access tokens, which do not expire under normal conditions.
- Publishing: POST /{page-id}/feed (text, optional link); POST /{page-id}/photos for a
  photo (multipart ``source``); multi-photo posts by uploading photos unpublished and
  attaching them to a feed post via ``attached_media``.
- Post insights: post_media_view, post_total_media_view_unique, post_clicks,
  post_reactions_by_type_total (post_impressions* are deprecated above v25).
- Permissions: pages_show_list, pages_manage_posts, pages_read_engagement, read_insights.
  Development mode only works for people with a role on the Meta app; production use
  requires Meta App Review of these permissions.

Status: code complete and covered by tests with Graph API responses stubbed. Not yet
exercised against the real Graph API (no Meta app credentials configured).
"""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from .base import (
    AccountCredentials,
    AccountRef,
    AuthorizationFailed,
    ContentRejected,
    MetricValue,
    NotConfigured,
    PlatformCapabilities,
    PublishRequest,
    PublishResult,
    RateLimited,
    ReauthRequired,
    SocialError,
    TransientError,
    UncertainOutcome,
    Unsupported,
)

SCOPES = ("pages_show_list", "pages_manage_posts", "pages_read_engagement", "read_insights")
_RATE_LIMIT_CODES = {4, 17, 32, 613, 80001}
_TRANSIENT_CODES = {1, 2}
_AUTH_CODES = {190, 102}
_PERMISSION_CODES = {10, 200, 299}


class FacebookAdapter:
    platform = "facebook"
    is_mock = False
    capabilities = PlatformCapabilities(
        platform="facebook",
        display_name="Facebook Page",
        publish_formats=frozenset({"post", "carousel"}),
        media_required_formats=frozenset({"carousel"}),
        max_images=10,
        supports_text_only=True,
        supports_metrics=True,
        notes=(
            "Publishes to Facebook Pages you manage (not personal profiles).",
            "Reels and Stories are not supported by this integration yet.",
            "Until Meta approves this app, only people with a role on the Meta app can connect.",
        ),
    )

    def __init__(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        graph_version: str,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.graph = f"https://graph.facebook.com/{graph_version}"
        self.dialog = f"https://www.facebook.com/{graph_version}/dialog/oauth"
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _require_config(self) -> None:
        if not self.is_configured():
            raise NotConfigured("META_APP_ID and META_APP_SECRET are not set.")

    # --- HTTP -----------------------------------------------------------------

    def _request(
        self, method: str, path: str, *, write: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.graph}/{path.lstrip('/')}"
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            # A write that timed out may still have been applied by Meta.
            if write:
                raise UncertainOutcome("Timed out waiting for Facebook") from exc
            raise TransientError("Timed out waiting for Facebook") from exc
        except httpx.TransportError as exc:
            if write and not isinstance(exc, httpx.ConnectError):
                raise UncertainOutcome("Connection dropped while publishing") from exc
            raise TransientError("Could not reach Facebook") from exc
        trace = response.headers.get("x-fb-trace-id", "")
        try:
            body: dict[str, Any] = response.json()
        except json.JSONDecodeError:
            body = {}
        if response.status_code >= 500:
            raise TransientError(f"Facebook returned {response.status_code}", request_id=trace)
        if "error" in body or response.status_code >= 400:
            raise _normalize(body.get("error", {}), response.status_code, trace)
        return body

    # --- Authorization -------------------------------------------------------------

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str) -> str:
        self._require_config()
        params = {
            "client_id": self.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": ",".join(SCOPES),
        }
        return f"{self.dialog}?{urlencode(params)}"

    def complete_authorization(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> list[AccountCredentials]:
        self._require_config()
        try:
            short = self._request(
                "GET",
                "oauth/access_token",
                params={
                    "client_id": self.app_id,
                    "redirect_uri": redirect_uri,
                    "client_secret": self.app_secret,
                    "code": code,
                },
            )
            long_lived = self._request(
                "GET",
                "oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": short["access_token"],
                },
            )
            pages = self._request(
                "GET",
                "me/accounts",
                params={
                    "fields": "id,name,access_token,tasks,category,link",
                    "access_token": long_lived["access_token"],
                },
            )
        except (ContentRejected, ReauthRequired, KeyError) as exc:
            raise AuthorizationFailed("Facebook did not complete the authorization.") from exc
        accounts = []
        for page in pages.get("data", []):
            tasks = set(page.get("tasks", []))
            if not tasks & {"CREATE_CONTENT", "MANAGE"}:
                continue  # the person can't publish to this Page
            accounts.append(
                AccountCredentials(
                    external_id=str(page["id"]),
                    name=page.get("name", "Facebook Page"),
                    username="",
                    account_type="facebook_page",
                    access_token=page["access_token"],
                    scopes=SCOPES,
                    metadata={"category": page.get("category", ""), "link": page.get("link", "")},
                )
            )
        if not accounts:
            raise AuthorizationFailed(
                "No Facebook Pages you can publish to were shared with this app."
            )
        return accounts

    # --- Publishing ------------------------------------------------------------------

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult:
        if request.format not in self.capabilities.publish_formats:
            raise Unsupported(f"{request.format} posts aren't supported for Facebook yet.")
        token = {"access_token": account.access_token}
        page = account.external_id
        if not request.media:
            fields = {"message": request.text, **({"link": request.link} if request.link else {})}
            result = self._request("POST", f"{page}/feed", write=True, data={**fields, **token})
            return self._result(result)
        if len(request.media) == 1:
            media = request.media[0]
            result = self._request(
                "POST",
                f"{page}/photos",
                write=True,
                data={"message": request.text, "published": "true", **token},
                files={"source": (media.filename, media.content, media.content_type)},
            )
            return self._result({"id": result.get("post_id") or result.get("id")})
        # Multi-photo: upload unpublished photos, then attach them to one feed post.
        media_ids = []
        for media in request.media[: self.capabilities.max_images]:
            uploaded = self._request(
                "POST",
                f"{page}/photos",
                data={"published": "false", **token},
                files={"source": (media.filename, media.content, media.content_type)},
            )
            media_ids.append(uploaded["id"])
        data: dict[str, str] = {"message": request.text, **token}
        for i, media_id in enumerate(media_ids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": media_id})
        return self._result(self._request("POST", f"{page}/feed", write=True, data=data))

    def _result(self, body: dict[str, Any]) -> PublishResult:
        post_id = str(body.get("id", ""))
        if not post_id:
            raise UncertainOutcome("Facebook accepted the request but returned no post id.")
        return PublishResult(
            external_post_id=post_id, permalink=f"https://www.facebook.com/{post_id}", raw=body
        )

    def find_recent_post(
        self, account: AccountRef, *, text: str, since: datetime
    ) -> PublishResult | None:
        body = self._request(
            "GET",
            f"{account.external_id}/posts",
            params={
                "fields": "id,message,permalink_url,created_time",
                "since": int(since.timestamp()),
                "limit": 25,
                "access_token": account.access_token,
            },
        )
        for post in body.get("data", []):
            if (post.get("message") or "").strip() == text.strip():
                return PublishResult(
                    external_post_id=str(post["id"]), permalink=post.get("permalink_url", "")
                )
        return None

    # --- Metrics -----------------------------------------------------------------------

    _METRICS = {
        "post_media_view": "views",
        "post_total_media_view_unique": "reach",
        "post_clicks": "clicks",
        "post_reactions_by_type_total": "reactions",
    }

    def fetch_post_metrics(self, account: AccountRef, external_post_id: str) -> list[MetricValue]:
        body = self._request(
            "GET",
            f"{external_post_id}/insights",
            params={"metric": ",".join(self._METRICS), "access_token": account.access_token},
        )
        found: dict[str, float | None] = {}
        for entry in body.get("data", []):
            values = entry.get("values") or []
            raw = values[-1].get("value") if values else None
            if isinstance(raw, dict):  # e.g. reactions by type -> total
                raw = sum(v for v in raw.values() if isinstance(v, int | float))
            found[entry.get("name", "")] = float(raw) if isinstance(raw, int | float) else None
        # Metrics the platform did not return stay None (missing), never 0.
        return [MetricValue(key, found.get(name)) for name, key in self._METRICS.items()]


def _normalize(error: dict[str, Any], status: int, trace: str) -> SocialError:
    code = error.get("code")
    message = str(error.get("message") or f"Facebook error {status}")[:300]
    if code in _AUTH_CODES or (error.get("type") == "OAuthException" and code == 190):
        return ReauthRequired(message, request_id=trace)
    if code in _PERMISSION_CODES:
        return ReauthRequired(f"Missing permission: {message}", request_id=trace)
    if code in _RATE_LIMIT_CODES or status == 429:
        return RateLimited(message, request_id=trace)
    if code in _TRANSIENT_CODES or error.get("is_transient"):
        return TransientError(message, request_id=trace)
    return ContentRejected(message, request_id=trace)
