"""Instagram (professional accounts) via the Instagram API with Facebook Login.

Based on Meta's content-publishing documentation reviewed on 2026-10-20:
- Account discovery: Facebook Login, then each Page's linked
  ``instagram_business_account`` (GET /me/accounts?fields=instagram_business_account{...}).
  The Page access token is used for the Instagram Graph calls.
- Publishing: create a container (POST /{ig-id}/media with image_url, caption,
  alt_text; carousels use is_carousel_item children + media_type=CAROUSEL), poll
  status_code (FINISHED/IN_PROGRESS/ERROR/EXPIRED), then POST /{ig-id}/media_publish.
- Constraints: **JPEG only**; media must be at a **publicly reachable URL** (signed S3
  URLs work; local development storage does not); 100 API posts per 24h; no text-only
  posts; Reels/Stories need video (not supported by this integration yet).
- Permissions: instagram_basic, instagram_content_publish, pages_show_list,
  pages_read_engagement (+ instagram_manage_insights for metrics). Requires App Review
  for production; development mode works for app role holders.

Status: code complete, tested with Graph API responses stubbed. Not exercised against
the real API (no Meta app credentials configured).
"""

import contextlib
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from .base import (
    AccountCredentials,
    AccountRef,
    AuthorizationFailed,
    ContentRejected,
    MetricValue,
    PlatformCapabilities,
    PublishRequest,
    PublishResult,
    TransientError,
    UncertainOutcome,
    Unsupported,
)
from .facebook import FacebookAdapter

SCOPES = (
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
)


class InstagramAdapter(FacebookAdapter):
    platform = "instagram"
    capabilities = PlatformCapabilities(
        platform="instagram",
        display_name="Instagram professional account",
        publish_formats=frozenset({"post", "carousel"}),
        media_required_formats=frozenset({"post", "carousel"}),
        max_images=10,
        supports_text_only=False,
        supports_metrics=True,
        image_types=frozenset({"image/jpeg"}),
        requires_public_media_url=True,
        notes=(
            "Requires an Instagram professional account linked to a Facebook Page.",
            "Images must be JPEG and are fetched by Instagram from a public URL, so production "
            "media storage (S3) is required.",
            "Reels and Stories are not supported by this integration yet.",
            "Until Meta approves this app, only people with a role on the Meta app can connect.",
        ),
    )
    container_poll_seconds = 2.0
    container_poll_attempts = 15

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
                    "fields": "id,name,access_token,instagram_business_account{id,username,name}",
                    "access_token": long_lived["access_token"],
                },
            )
        except (ContentRejected, KeyError) as exc:
            raise AuthorizationFailed("Facebook did not complete the authorization.") from exc
        accounts = []
        for page in pages.get("data", []):
            ig = page.get("instagram_business_account")
            if not ig:
                continue
            accounts.append(
                AccountCredentials(
                    external_id=str(ig["id"]),
                    name=ig.get("name") or ig.get("username") or "Instagram account",
                    username=ig.get("username", ""),
                    account_type="instagram_professional",
                    access_token=page["access_token"],
                    scopes=SCOPES,
                    metadata={
                        "facebook_page_id": str(page["id"]),
                        "facebook_page_name": page.get("name", ""),
                    },
                )
            )
        if not accounts:
            raise AuthorizationFailed(
                "No Instagram professional accounts linked to your Facebook Pages were found."
            )
        return accounts

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult:
        if request.format not in self.capabilities.publish_formats:
            raise Unsupported(f"{request.format} isn't supported for Instagram yet.")
        if not request.media:
            raise ContentRejected("Instagram posts need at least one image.")
        for media in request.media:
            if media.content_type != "image/jpeg":
                raise ContentRejected(
                    "Instagram only accepts JPEG images. Re-upload the image as JPEG."
                )
            if not media.public_url:
                raise ContentRejected(
                    "Instagram fetches images from a public URL. "
                    "Configure S3 media storage to publish."
                )
        ig, token = account.external_id, {"access_token": account.access_token}
        if len(request.media) == 1:
            container = self._request(
                "POST",
                f"{ig}/media",
                data={
                    "image_url": request.media[0].public_url,
                    "caption": request.text,
                    **({"alt_text": request.alt_text} if request.alt_text else {}),
                    **token,
                },
            )["id"]
        else:
            children = [
                self._request(
                    "POST",
                    f"{ig}/media",
                    data={"image_url": m.public_url, "is_carousel_item": "true", **token},
                )["id"]
                for m in request.media[: self.capabilities.max_images]
            ]
            for child in children:
                self._wait_for_container(child, account.access_token)
            container = self._request(
                "POST",
                f"{ig}/media",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": request.text,
                    **token,
                },
            )["id"]
        self._wait_for_container(container, account.access_token)
        published = self._request(
            "POST", f"{ig}/media_publish", write=True, data={"creation_id": container, **token}
        )
        media_id = str(published.get("id", ""))
        if not media_id:
            raise UncertainOutcome("Instagram accepted the request but returned no media id.")
        permalink = ""
        with contextlib.suppress(TransientError):
            permalink = self._request("GET", media_id, params={"fields": "permalink", **token}).get(
                "permalink", ""
            )
        return PublishResult(
            external_post_id=media_id, permalink=permalink, raw={"container": container}
        )

    def _wait_for_container(self, container_id: str, token: str) -> None:
        for _ in range(self.container_poll_attempts):
            status = self._request(
                "GET", container_id, params={"fields": "status_code", "access_token": token}
            ).get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise ContentRejected(f"Instagram could not process the media ({status}).")
            time.sleep(self.container_poll_seconds)
        raise TransientError("Instagram is still processing the media; will retry.")

    def find_recent_post(
        self, account: AccountRef, *, text: str, since: datetime
    ) -> PublishResult | None:
        body = self._request(
            "GET",
            f"{account.external_id}/media",
            params={
                "fields": "id,caption,permalink,timestamp",
                "limit": 25,
                "access_token": account.access_token,
            },
        )
        for media in body.get("data", []):
            if (media.get("caption") or "").strip() == text.strip():
                return PublishResult(
                    external_post_id=str(media["id"]), permalink=media.get("permalink", "")
                )
        return None

    _IG_METRICS = {
        "views": "views",
        "reach": "reach",
        "likes": "likes",
        "comments": "comments",
        "saved": "saves",
        "shares": "shares",
    }

    def fetch_post_metrics(self, account: AccountRef, external_post_id: str) -> list[MetricValue]:
        body: dict[str, Any] = self._request(
            "GET",
            f"{external_post_id}/insights",
            params={"metric": ",".join(self._IG_METRICS), "access_token": account.access_token},
        )
        found: dict[str, float | None] = {}
        for entry in body.get("data", []):
            values = entry.get("values") or []
            raw = values[-1].get("value") if values else entry.get("total_value", {}).get("value")
            found[entry.get("name", "")] = float(raw) if isinstance(raw, int | float) else None
        return [MetricValue(key, found.get(name)) for name, key in self._IG_METRICS.items()]
