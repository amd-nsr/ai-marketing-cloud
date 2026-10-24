"""Account-level Meta operations behind an internal interface.

``MetaAccountClient`` talks to the real Graph API through ``GraphClient``.
``SimulatedMetaAccountClient`` returns labelled simulation assets without contacting Meta
(used for local trials and automated tests; its Pages publish through the simulation
social adapter and never post anywhere).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

from django.utils import timezone

from apps.social.adapters.base import AuthorizationFailed, ContentRejected, ReauthRequired

from . import permissions
from .graph import GraphClient


@dataclass(frozen=True)
class UserToken:
    token: str
    expires_at: datetime | None


@dataclass(frozen=True)
class MetaPage:
    id: str
    name: str
    category: str
    tasks: tuple[str, ...]
    link: str = ""
    #: Only present when fetched for connecting; never persisted outside SocialAccount.
    access_token: str = ""

    @property
    def can_publish(self) -> bool:
        return bool(set(self.tasks) & {"CREATE_CONTENT", "MANAGE"})

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "link": self.link,
            "can_publish": self.can_publish,
        }


@dataclass(frozen=True)
class MetaAdAccountInfo:
    id: str  # "act_<number>"
    name: str
    currency: str
    timezone_name: str
    account_status: int

    @property
    def is_active(self) -> bool:
        return self.account_status == 1

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "currency": self.currency,
            "timezone_name": self.timezone_name,
            "account_status": self.account_status,
            "is_active": self.is_active,
        }


class AccountClient(Protocol):
    is_mock: bool

    def authorization_url(self, *, state: str, redirect_uri: str) -> str: ...

    def exchange_code(self, *, code: str, redirect_uri: str) -> UserToken: ...

    def me(self, token: str) -> dict[str, str]: ...

    def permissions(self, token: str) -> tuple[list[str], list[str]]: ...

    def pages(self, token: str, *, with_tokens: bool = False) -> list[MetaPage]: ...

    def ad_accounts(self, token: str) -> list[MetaAdAccountInfo]: ...

    def revoke(self, token: str) -> None: ...


class MetaAccountClient:
    is_mock = False

    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        self.graph.require_config()
        params = {
            "client_id": self.graph.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": ",".join(permissions.requested_scopes()),
            # Re-show declined permissions when someone reconnects.
            "auth_type": "rerequest",
        }
        return f"{self.graph.dialog}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> UserToken:
        self.graph.require_config()
        try:
            short = self.graph.request(
                "GET",
                "oauth/access_token",
                params={
                    "client_id": self.graph.app_id,
                    "client_secret": self.graph.app_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            long_lived = self.graph.request(
                "GET",
                "oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.graph.app_id,
                    "client_secret": self.graph.app_secret,
                    "fb_exchange_token": short["access_token"],
                },
            )
        except (ContentRejected, ReauthRequired, KeyError) as exc:
            raise AuthorizationFailed("Facebook did not complete the authorization.") from exc
        expires_in = long_lived.get("expires_in")
        return UserToken(
            token=long_lived["access_token"],
            expires_at=timezone.now() + timedelta(seconds=int(expires_in)) if expires_in else None,
        )

    def me(self, token: str) -> dict[str, str]:
        body = self.graph.request("GET", "me", token=token, params={"fields": "id,name"})
        return {"id": str(body["id"]), "name": str(body.get("name", ""))}

    def permissions(self, token: str) -> tuple[list[str], list[str]]:
        granted: list[str] = []
        declined: list[str] = []
        for p in self.graph.paginate("me/permissions", token=token):
            (granted if p.get("status") == "granted" else declined).append(p["permission"])
        return sorted(granted), sorted(declined)

    def pages(self, token: str, *, with_tokens: bool = False) -> list[MetaPage]:
        fields = "id,name,category,tasks,link" + (",access_token" if with_tokens else "")
        return [
            MetaPage(
                id=str(p["id"]),
                name=p.get("name", "Facebook Page"),
                category=p.get("category", ""),
                tasks=tuple(p.get("tasks", [])),
                link=p.get("link", ""),
                access_token=p.get("access_token", "") if with_tokens else "",
            )
            for p in self.graph.paginate("me/accounts", token=token, params={"fields": fields})
        ]

    def ad_accounts(self, token: str) -> list[MetaAdAccountInfo]:
        fields = "id,name,currency,timezone_name,account_status"
        return [
            MetaAdAccountInfo(
                id=str(a["id"]),
                name=a.get("name") or a["id"],
                currency=a.get("currency", ""),
                timezone_name=a.get("timezone_name", ""),
                account_status=int(a.get("account_status") or 0),
            )
            for a in self.graph.paginate("me/adaccounts", token=token, params={"fields": fields})
        ]

    def revoke(self, token: str) -> None:
        """Remove every permission this person granted to the app (Meta-side logout)."""
        self.graph.request("DELETE", "me/permissions", token=token, write=True)


class SimulatedMetaAccountClient:
    """Labelled simulation: two Pages and one ad account, no network calls."""

    is_mock = True
    USER_ID = "sim-meta-user"

    def __init__(self, frontend_url: str) -> None:
        self.frontend_url = frontend_url.rstrip("/")

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?{urlencode({'state': state, 'code': 'mock-code'})}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> UserToken:
        return UserToken("mock-user-token", timezone.now() + timedelta(days=60))

    def me(self, token: str) -> dict[str, str]:
        return {"id": self.USER_ID, "name": "Simulated Meta user"}

    def permissions(self, token: str) -> tuple[list[str], list[str]]:
        return permissions.requested_scopes(), []

    def pages(self, token: str, *, with_tokens: bool = False) -> list[MetaPage]:
        return [
            MetaPage(
                id="sim-page-1",
                name="Simulated Café Page",
                category="Coffee shop",
                tasks=("MANAGE", "CREATE_CONTENT"),
                access_token="mock-page-token-1" if with_tokens else "",
            ),
            MetaPage(
                id="sim-page-2",
                name="Simulated Read-only Page",
                category="Bakery",
                tasks=("ANALYZE",),
                access_token="mock-page-token-2" if with_tokens else "",
            ),
        ]

    def ad_accounts(self, token: str) -> list[MetaAdAccountInfo]:
        return [MetaAdAccountInfo("act_sim_1", "Simulated ad account", "USD", "UTC", 1)]

    def revoke(self, token: str) -> None:
        return None


def account_client(*, mock: bool) -> AccountClient:
    from django.conf import settings

    from apps.social.adapters.base import NotConfigured

    if mock:
        if not settings.SOCIAL_MOCK_ENABLED:
            raise NotConfigured("Simulation accounts are disabled in this environment.")
        return SimulatedMetaAccountClient(settings.FRONTEND_URL)
    return MetaAccountClient(GraphClient.from_settings())
