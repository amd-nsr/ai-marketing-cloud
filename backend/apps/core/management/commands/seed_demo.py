"""Create a local demo account and organization. Development only.

    uv run python manage.py seed_demo

The credentials below are for local development databases only and are refused
when DEBUG is False.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.organizations.models import Membership
from apps.organizations.services import create_organization

DEMO_EMAIL = "demo.owner@example.com"
DEMO_PASSWORD = "demo-local-only-passphrase"  # noqa: S105 - local development fixture
DEMO_ORG = "Demo Coffee Roasters"


class Command(BaseCommand):
    help = "Create a demo owner and organization for local development."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True (development settings).")
        user = User.objects.filter(email=DEMO_EMAIL).first()
        if user is None:
            user = User.objects.create_user(DEMO_EMAIL, DEMO_PASSWORD, full_name="Demo Owner")
            self.stdout.write(f"Created user {DEMO_EMAIL}")
        if not Membership.objects.filter(user=user).exists():
            org = create_organization(user=user, name=DEMO_ORG)
            self.stdout.write(f"Created organization {org.name} ({org.id})")
        self.stdout.write(self.style.SUCCESS(f"Sign in as {DEMO_EMAIL} (password in this file)."))
