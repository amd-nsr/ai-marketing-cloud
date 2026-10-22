from collections.abc import Callable
from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.organizations.models import Membership, Organization
from apps.organizations.services import create_organization

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttling state must not leak between tests
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db) -> Callable[..., User]:
    counter = {"n": 0}

    def _make(email: str | None = None, **extra: Any) -> User:
        counter["n"] += 1
        return User.objects.create_user(
            email or f"user{counter['n']}@example.com", PASSWORD, **extra
        )

    return _make


@pytest.fixture
def make_org(make_user) -> Callable[..., Organization]:
    def _make(name: str = "Acme Coffee", owner: User | None = None) -> Organization:
        return create_organization(user=owner or make_user(), name=name)

    return _make


@pytest.fixture
def add_member() -> Callable[[Organization, User, str], Membership]:
    def _add(org: Organization, user: User, role: str) -> Membership:
        return Membership.objects.create(organization=org, user=user, role=role)

    return _add


@pytest.fixture
def org_client(make_user, make_org, add_member) -> Callable[..., tuple[APIClient, Organization]]:
    """Returns an authenticated client for a fresh user holding ``role`` in a fresh org."""

    def _make(
        role: str = "owner", org: Organization | None = None
    ) -> tuple[APIClient, Organization]:
        user = make_user()
        if org is None:
            org = make_org(owner=user) if role == "owner" else make_org()
        if role != "owner" or not Membership.objects.filter(organization=org, user=user).exists():
            add_member(org, user, role)
        client = APIClient()
        client.force_authenticate(user)
        client.user = user
        return client, org

    return _make


@pytest.fixture
def ready_org(org_client) -> Callable[..., tuple[APIClient, Organization]]:
    """An org whose required onboarding steps are complete."""

    def _make(role: str = "owner", **profile: Any) -> tuple[APIClient, Organization]:
        from apps.brand.models import TargetAudience
        from apps.brand.services import get_profile

        client, org = org_client(role)
        p = get_profile(org)
        p.industry = profile.get("industry", "restaurant")
        p.description = profile.get("description", "Specialty coffee and pastries.")
        p.goals = profile.get("goals", ["foot_traffic"])
        p.preferred_platforms = profile.get("platforms", ["instagram", "facebook"])
        p.save()
        TargetAudience.objects.create(organization=org, name="Local commuters", is_primary=True)
        return client, org

    return _make
