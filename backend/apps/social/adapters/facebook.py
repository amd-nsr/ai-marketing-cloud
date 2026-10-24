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

Connecting goes through ``apps.meta`` (Meta login, then the person selects Pages); this
adapter publishes and reads insights for a selected Page. All HTTP goes through
``apps.meta.graph.GraphClient`` (appsecret_proof, throttling, error normalization).

Status: code complete and covered by tests with Graph API responses stubbed. Not yet
exercised against the real Graph API (no Meta app credentials configured).
"""

import json
from datetime import datetime
from typing import Any

import httpx

from .base import (
    AccountCredentials,
    AccountRef,
    AuthorizationFailed,
    MetricValue,
    PlatformCapabilities,
    PublishRequest,
    PublishResult,
    UncertainOutcome,
    Unsupported,
)


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
        from apps.meta.client import MetaAccountClient
        from apps.meta.graph import GraphClient

        self._graph = GraphClient(
            app_id=app_id,
            app_secret=app_secret,
            version=graph_version,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self._accounts = MetaAccountClient(self._graph)

    def is_configured(self) -> bool:
        return self._graph.is_configured()

    # Used by the Instagram adapter, which shares the Meta app and login dialog.
    @property
    def app_id(self) -> str | None:
        return self._graph.app_id

    @property
    def app_secret(self) -> str | None:
        return self._graph.app_secret

    @property
    def dialog(self) -> str:
        return self._graph.dialog

    def _require_config(self) -> None:
        self._graph.require_config()

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        write: bool = False,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        page: str | None = None,
    ) -> dict[str, Any]:
        # Subclasses (Instagram) may pass the token inside params/data; lift it out so the
        # client adds appsecret_proof and never sends it twice.
        if token is None:
            for source in (params, data):
                if source and "access_token" in source:
                    source = dict(source)
                    token = str(source.pop("access_token"))
                    if params is not None and "access_token" in params:
                        params = source
                    else:
                        data = source
                    break
        return self._graph.request(
            method,
            path,
            token=token,
            params=params,
            data=data,
            files=files,
            write=write,
            throttle_key=f"page:{page}" if page else None,
        )

    # --- Authorization -------------------------------------------------------------
    # The app connects Facebook through apps.meta (login, then Page selection). These
    # implement the adapter contract for completeness and reuse the same Meta client.

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str) -> str:
        return self._accounts.authorization_url(state=state, redirect_uri=redirect_uri)

    def complete_authorization(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> list[AccountCredentials]:
        from apps.meta import permissions

        user = self._accounts.exchange_code(code=code, redirect_uri=redirect_uri)
        pages = [p for p in self._accounts.pages(user.token, with_tokens=True) if p.can_publish]
        if not pages:
            raise AuthorizationFailed(
                "No Facebook Pages you can publish to were shared with this app."
            )
        scopes = permissions.FEATURE_PERMISSIONS[permissions.PAGES_FEATURE]
        return [
            AccountCredentials(
                external_id=p.id,
                name=p.name,
                username="",
                account_type="facebook_page",
                access_token=p.access_token,
                scopes=scopes,
                metadata={"category": p.category, "link": p.link},
            )
            for p in pages
        ]

    # --- Publishing ------------------------------------------------------------------

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult:
        if request.format not in self.capabilities.publish_formats:
            raise Unsupported(f"{request.format} posts aren't supported for Facebook yet.")
        token = account.access_token
        page = account.external_id
        if not request.media:
            fields = {"message": request.text, **({"link": request.link} if request.link else {})}
            result = self._request(
                "POST", f"{page}/feed", token=token, write=True, data=fields, page=page
            )
            return self._result(result)
        if len(request.media) == 1:
            media = request.media[0]
            result = self._request(
                "POST",
                f"{page}/photos",
                token=token,
                write=True,
                data={"message": request.text, "published": "true"},
                files={"source": (media.filename, media.content, media.content_type)},
                page=page,
            )
            return self._result({"id": result.get("post_id") or result.get("id")})
        # Multi-photo: upload unpublished photos, then attach them to one feed post.
        media_ids = []
        for media in request.media[: self.capabilities.max_images]:
            uploaded = self._request(
                "POST",
                f"{page}/photos",
                token=token,
                data={"published": "false"},
                files={"source": (media.filename, media.content, media.content_type)},
                page=page,
            )
            media_ids.append(uploaded["id"])
        data: dict[str, str] = {"message": request.text}
        for i, media_id in enumerate(media_ids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": media_id})
        return self._result(
            self._request("POST", f"{page}/feed", token=token, write=True, data=data, page=page)
        )

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
            token=account.access_token,
            params={
                "fields": "id,message,permalink_url,created_time",
                "since": int(since.timestamp()),
                "limit": 25,
            },
            page=account.external_id,
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
            token=account.access_token,
            params={"metric": ",".join(self._METRICS)},
            page=account.external_id,
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
