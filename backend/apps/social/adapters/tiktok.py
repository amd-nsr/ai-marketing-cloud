"""TikTok via Login Kit (OAuth v2 + PKCE) and the Content Posting API.

Based on TikTok's developer documentation reviewed on 2026-10-20:
- OAuth: https://www.tiktok.com/v2/auth/authorize/ (client_key, scope, response_type=code,
  redirect_uri, state, code_challenge, code_challenge_method=S256); token exchange at
  https://open.tiktokapis.com/v2/oauth/token/ (grant_type=authorization_code, code_verifier).
  Access tokens are short-lived and refreshed with the refresh token.
- Posting: POST /v2/post/publish/creator_info/query/ (privacy options), then
  POST /v2/post/publish/content/init/ for photo posts (PULL_FROM_URL from a *verified*
  domain) or /v2/post/publish/video/init/ for video; status via /v2/post/publish/status/fetch/.
- **Unaudited API clients can only post with private (SELF_ONLY) visibility.** Public
  posting requires passing TikTok's app audit.

This integration currently supports photo posts (``carousel`` format = TikTok photo
mode) from public URLs. Video upload is not implemented yet. Not exercised against the
real API (no TikTok app credentials configured).
"""

from datetime import UTC, datetime, timedelta
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

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = ("user.info.basic", "video.publish", "video.list")


class TikTokAdapter:
    platform = "tiktok"
    is_mock = False
    capabilities = PlatformCapabilities(
        platform="tiktok",
        display_name="TikTok",
        publish_formats=frozenset({"carousel"}),
        media_required_formats=frozenset({"carousel"}),
        max_images=35,
        supports_text_only=False,
        supports_metrics=False,
        requires_public_media_url=True,
        notes=(
            "Until TikTok audits this app, posts are only visible to the account owner (private).",
            "Photo posts only for now; video upload is not implemented yet.",
            "Images are pulled by TikTok from a public URL on a verified domain "
            "(S3 + domain verification).",
        ),
    )

    def __init__(
        self,
        *,
        client_key: str | None,
        client_secret: str | None,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_key = client_key
        self.client_secret = client_secret
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def _post(
        self, path: str, *, token: str | None = None, write: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = self._client.post(f"{API}/{path}", headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            if write:
                raise UncertainOutcome("Timed out waiting for TikTok") from exc
            raise TransientError("Timed out waiting for TikTok") from exc
        except httpx.TransportError as exc:
            raise TransientError("Could not reach TikTok") from exc
        if response.status_code >= 500:
            raise TransientError(f"TikTok returned {response.status_code}")
        try:
            body: dict[str, Any] = response.json()
        except ValueError:
            body = {}
        error = body.get("error") or {}
        code = error.get("code", "ok") if isinstance(error, dict) else "ok"
        if code not in ("ok", "", None) or response.status_code >= 400:
            raise _normalize(str(code), str(error.get("message", "")), error.get("log_id", ""))
        return body

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str) -> str:
        if not self.is_configured():
            raise NotConfigured("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET are not set.")
        params = {
            "client_key": self.client_key,
            "scope": ",".join(SCOPES),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def complete_authorization(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> list[AccountCredentials]:
        try:
            token = self._post(
                "oauth/token/",
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
            )
            info = self._post(
                "user/info/?fields=open_id,display_name,username",
                token=token["access_token"],
            )
        except (SocialError, KeyError) as exc:
            raise AuthorizationFailed("TikTok did not complete the authorization.") from exc
        user = info.get("data", {}).get("user", {})
        return [
            AccountCredentials(
                external_id=str(token.get("open_id") or user.get("open_id")),
                name=user.get("display_name") or "TikTok account",
                username=user.get("username", ""),
                account_type="tiktok_creator",
                access_token=token["access_token"],
                refresh_token=token.get("refresh_token"),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=int(token.get("expires_in", 86400))),
                scopes=tuple(str(token.get("scope", "")).split(",")),
            )
        ]

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult:
        if request.format not in self.capabilities.publish_formats:
            raise Unsupported("Only photo posts are supported for TikTok so far.")
        urls = [m.public_url for m in request.media if m.public_url]
        if not urls or len(urls) != len(request.media):
            raise ContentRejected(
                "TikTok pulls images from a public, verified URL. Configure S3 media storage."
            )
        creator = self._post("post/publish/creator_info/query/", token=account.access_token)
        options = creator.get("data", {}).get("privacy_level_options", [])
        privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else "SELF_ONLY"
        init = self._post(
            "post/publish/content/init/",
            token=account.access_token,
            write=True,
            json={
                "post_info": {
                    "title": request.text[:90],
                    "description": request.text,
                    "privacy_level": privacy,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_images": urls,
                    "photo_cover_index": 0,
                },
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
            },
        )
        publish_id = init.get("data", {}).get("publish_id")
        if not publish_id:
            raise UncertainOutcome("TikTok accepted the request but returned no publish id.")
        # TikTok processes asynchronously; the publish_id identifies the post until then.
        return PublishResult(external_post_id=str(publish_id), raw={"privacy_level": privacy})

    def find_recent_post(
        self, account: AccountRef, *, text: str, since: datetime
    ) -> PublishResult | None:
        # The Content Posting API has no lookup by caption; reconciliation can't confirm.
        return None

    def fetch_post_metrics(self, account: AccountRef, external_post_id: str) -> list[MetricValue]:
        raise Unsupported("TikTok metrics are not supported by this integration yet.")


def _normalize(code: str, message: str, log_id: str) -> SocialError:
    msg = message[:300] or code
    if code in {"access_token_invalid", "scope_not_authorized", "token_expired"}:
        return ReauthRequired(msg, request_id=log_id)
    if code in {"rate_limit_exceeded", "spam_risk_too_many_posts"}:
        return RateLimited(msg, request_id=log_id)
    if code in {"internal_error", "service_unavailable"}:
        return TransientError(msg, request_id=log_id)
    return ContentRejected(msg, request_id=log_id)
