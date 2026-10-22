"""Simulation adapter: behaves like a platform without contacting one.

Accounts it creates are flagged ``is_mock`` and labelled "Simulation" everywhere; posts
are never visible anywhere outside this application. It exists for automated tests and
for trying the full workflow locally. Behaviour can be steered from the caption:

- ``[mock:transient]`` → retryable platform error
- ``[mock:reject]`` → permanent content rejection
- ``[mock:reauth]`` → credentials revoked
- ``[mock:uncertain]`` → timeout after sending (outcome unknown; post *was* created)
- ``[mock:lost]`` → timeout after sending (outcome unknown; post was *not* created)
"""

import hashlib
from datetime import UTC, datetime
from urllib.parse import urlencode

from .base import (
    AccountCredentials,
    AccountRef,
    ContentRejected,
    MetricValue,
    PlatformCapabilities,
    PublishRequest,
    PublishResult,
    ReauthRequired,
    TransientError,
    UncertainOutcome,
)

#: In-process record of simulated posts, keyed by account; used for reconciliation tests.
_POSTS: dict[str, list[tuple[str, str, datetime]]] = {}


class MockAdapter:
    is_mock = True

    def __init__(self, platform: str, frontend_url: str) -> None:
        self.platform = platform
        self.frontend_url = frontend_url.rstrip("/")
        formats = {
            "instagram": {"post", "carousel", "reel", "story"},
            "facebook": {"post", "carousel", "reel", "story"},
            "tiktok": {"short_video", "carousel"},
        }[platform]
        self.capabilities = PlatformCapabilities(
            platform=platform,
            display_name=f"{platform.title()} (simulation)",
            publish_formats=frozenset(formats),
            media_required_formats=frozenset(),
            max_images=10,
            supports_text_only=True,
            supports_metrics=True,
            notes=("Simulation only: nothing is posted to a real platform.",),
        )

    def is_configured(self) -> bool:
        return True

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str) -> str:
        # No external consent screen: return straight to our callback.
        return f"{redirect_uri}?{urlencode({'state': state, 'code': 'mock-code'})}"

    def complete_authorization(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> list[AccountCredentials]:
        return [
            AccountCredentials(
                external_id=f"mock-{self.platform}-1",
                name=f"Simulated {self.platform.title()} account",
                username=f"sim_{self.platform}",
                account_type=f"mock_{self.platform}",
                access_token=f"mock-token-{self.platform}",
                scopes=("simulation",),
                metadata={"simulation": True},
            )
        ]

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult:
        text = request.text
        if "[mock:transient]" in text:
            raise TransientError("Simulated temporary outage")
        if "[mock:reject]" in text:
            raise ContentRejected("Simulated content rejection")
        if "[mock:reauth]" in text:
            raise ReauthRequired("Simulated revoked credentials")
        post_id = (
            "mock_"
            + hashlib.sha256(
                f"{account.external_id}{text}{datetime.now(UTC)}".encode()
            ).hexdigest()[:16]
        )
        if "[mock:lost]" in text:
            raise UncertainOutcome("Simulated timeout; nothing was created")
        _POSTS.setdefault(account.external_id, []).append((post_id, text, datetime.now(UTC)))
        if "[mock:uncertain]" in text:
            raise UncertainOutcome("Simulated timeout after the post was created")
        return PublishResult(external_post_id=post_id)  # simulated posts have no public URL

    def find_recent_post(
        self, account: AccountRef, *, text: str, since: datetime
    ) -> PublishResult | None:
        for post_id, body, created in reversed(_POSTS.get(account.external_id, [])):
            if body == text and created >= since:
                return PublishResult(external_post_id=post_id)
        return None

    def fetch_post_metrics(self, account: AccountRef, external_post_id: str) -> list[MetricValue]:
        seed = int(hashlib.sha256(external_post_id.encode()).hexdigest()[:8], 16)
        reach = 200 + seed % 800
        return [
            MetricValue("impressions", float(reach + seed % 300)),
            MetricValue("reach", float(reach)),
            MetricValue("engagements", float(10 + seed % 60)),
            MetricValue("comments", float(seed % 12)),
            # Simulates a metric the platform does not report for this post.
            MetricValue("saves", None),
        ]
