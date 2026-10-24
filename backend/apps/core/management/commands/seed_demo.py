"""Create local demo users (one per role) and an onboarded organization. Development only.

    uv run python manage.py seed_demo      # or: make seed (make dev runs it automatically)

Idempotent: existing users, memberships and profile data are left as they are; anything
missing is added. The credentials below are for local development databases only and
the command refuses to run when DEBUG is False.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.brand.models import TargetAudience
from apps.brand.services import complete_onboarding, get_guideline, get_profile
from apps.organizations.models import Membership, Organization
from apps.organizations.services import create_organization

DEMO_PASSWORD = "demo-local-only-passphrase"  # noqa: S105 - local development fixture
DEMO_ORG = "Demo Coffee Roasters"
DEMO_EMAIL = "demo.owner@example.com"  # the organization's creator

# (email, full name, role) — one user per role, all members of DEMO_ORG.
DEMO_USERS = [
    (DEMO_EMAIL, "Demo Owner", "owner"),
    ("demo.admin@example.com", "Demo Admin", "admin"),
    ("demo.editor@example.com", "Demo Editor", "editor"),
    ("demo.analyst@example.com", "Demo Analyst", "analyst"),
    ("demo.viewer@example.com", "Demo Viewer", "viewer"),
]


class Command(BaseCommand):
    help = "Create demo users (one per role) and an onboarded organization for local development."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True (development settings).")

        users = {email: self._user(email, name) for email, name, _ in DEMO_USERS}
        owner = users[DEMO_EMAIL]

        membership = Membership.objects.filter(user=owner, organization__name=DEMO_ORG).first()
        if membership is None:
            org = create_organization(user=owner, name=DEMO_ORG)
            self.stdout.write(f"Created organization {org.name} ({org.id})")
        else:
            org = membership.organization

        for email, _, role in DEMO_USERS:
            _, created = Membership.objects.get_or_create(
                organization=org, user=users[email], defaults={"role": role}
            )
            if created:
                self.stdout.write(f"Added {email} as {role}")

        self._onboard(org, owner)

        self.stdout.write(self.style.SUCCESS(f"Demo users ready in {org.name}:"))
        for email, _, role in DEMO_USERS:
            self.stdout.write(f"  {role:<8} {email}")
        self.stdout.write(f"  password for all: {DEMO_PASSWORD}")

    def _user(self, email: str, full_name: str) -> User:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email, DEMO_PASSWORD, full_name=full_name)
            self.stdout.write(f"Created user {email}")
        return user

    def _onboard(self, org: Organization, owner: User) -> None:
        """Fill only what's missing, so manual edits to the demo org are kept."""
        profile = get_profile(org)
        defaults = {
            "business_name": DEMO_ORG,
            "industry": "restaurant",
            "description": (
                "Independent specialty coffee roaster with a café, selling single-origin "
                "beans, espresso drinks and fresh pastries. Open daily from 7am."
            ),
            "goals": ["foot_traffic"],
            "preferred_platforms": ["facebook", "instagram"],
        }
        changed = [f for f, v in defaults.items() if not getattr(profile, f)]
        for field in changed:
            setattr(profile, field, defaults[field])
        if changed:
            profile.save(update_fields=[*changed, "updated_at"])

        guideline = get_guideline(org)
        if not (guideline.tone or guideline.voice_description):
            guideline.voice_description = "Warm, knowledgeable and unpretentious."
            guideline.save(update_fields=["voice_description", "updated_at"])

        if not TargetAudience.objects.filter(organization=org).exists():
            TargetAudience.objects.create(
                organization=org, name="Local commuters and remote workers", is_primary=True
            )

        if profile.onboarding_completed_at is None:
            complete_onboarding(org, actor=owner)
            self.stdout.write("Completed onboarding")
