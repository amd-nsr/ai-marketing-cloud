import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.brand.services import get_profile
from apps.core.management.commands.seed_demo import DEMO_ORG, DEMO_PASSWORD, DEMO_USERS
from apps.organizations.models import Membership, Organization

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_one_user_per_role_and_is_idempotent(settings):
    settings.DEBUG = True
    call_command("seed_demo")
    call_command("seed_demo")

    org = Organization.objects.get(name=DEMO_ORG)
    roles = dict(Membership.objects.filter(organization=org).values_list("user__email", "role"))
    assert roles == {email: role for email, _, role in DEMO_USERS}
    assert get_profile(org).onboarding_completed_at is not None

    for email, _, _ in DEMO_USERS:
        cache.clear()  # each login is its own check; don't trip the login rate limit
        client = APIClient()
        response = client.post(
            "/api/v1/auth/login/", {"email": email, "password": DEMO_PASSWORD}, format="json"
        )
        assert response.status_code == 200, (email, response.json())


def test_seed_demo_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
