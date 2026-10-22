from dataclasses import dataclass
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.core.uploads import validate_image
from apps.organizations.models import Organization
from apps.usage.storage import check_storage_quota

from .models import BrandAsset, BrandGuideline, BusinessProfile, TargetAudience
from .presets import GOALS, PLATFORMS, PRESETS_BY_KEY


def get_profile(org: Organization) -> BusinessProfile:
    profile, _ = BusinessProfile.objects.get_or_create(
        organization=org, defaults={"business_name": org.name}
    )
    return profile


def get_guideline(org: Organization) -> BrandGuideline:
    guideline, _ = BrandGuideline.objects.get_or_create(organization=org)
    return guideline


# --- Onboarding --------------------------------------------------------------


@dataclass(frozen=True)
class OnboardingStep:
    key: str
    label: str
    required: bool
    complete: bool


def onboarding_steps(org: Organization) -> list[OnboardingStep]:
    profile = get_profile(org)
    guideline = get_guideline(org)
    has_audience = TargetAudience.objects.filter(organization=org).exists()
    has_assets = BrandAsset.objects.filter(organization=org).exists()
    return [
        OnboardingStep(
            "business",
            "Business basics",
            True,
            bool(profile.business_name and profile.industry and profile.description),
        ),
        OnboardingStep("audience", "Target audience", True, has_audience),
        OnboardingStep(
            "goals",
            "Goals and platforms",
            True,
            bool(profile.goals and profile.preferred_platforms),
        ),
        OnboardingStep(
            "voice",
            "Brand voice",
            False,
            bool(guideline.tone or guideline.voice_description),
        ),
        OnboardingStep("assets", "Brand assets", False, has_assets),
    ]


def complete_onboarding(
    org: Organization, *, actor: Any, request: HttpRequest | None = None
) -> BusinessProfile:
    missing = [s.label for s in onboarding_steps(org) if s.required and not s.complete]
    if missing:
        raise Conflict(f"Complete these steps first: {', '.join(missing)}.")
    profile = get_profile(org)
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = timezone.now()
        profile.save(update_fields=["onboarding_completed_at", "updated_at"])
        audit.record(
            "onboarding.completed", organization=org, actor=actor, target=profile, request=request
        )
    return profile


# --- Assets ------------------------------------------------------------------


@transaction.atomic
def upload_asset(
    org: Organization,
    *,
    actor: Any,
    upload: UploadedFile[Any],
    kind: str,
    title: str = "",
    request: HttpRequest | None = None,
) -> BrandAsset:
    info = validate_image(upload)
    check_storage_quota(org, info.size_bytes)
    original_name = (upload.name or "")[:255]
    upload.name = f"upload{info.extension}"  # the stored name never derives from client input
    asset = BrandAsset.objects.create(
        organization=org,
        kind=kind,
        title=title.strip()[:160],
        file=upload,
        original_filename=original_name,
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        sha256=info.sha256,
        uploaded_by=actor,
    )
    audit.record(
        "brand_asset.uploaded",
        organization=org,
        actor=actor,
        target=asset,
        metadata={"kind": kind, "size_bytes": info.size_bytes, "content_type": info.content_type},
        request=request,
    )
    return asset


# --- Business context for AI workflows ----------------------------------------


def build_business_context(org: Organization) -> dict[str, Any]:
    """Assemble the organization-specific context AI workflows may use.

    Contains only facts the business supplied (``source: user``) plus generic industry
    guidance labelled ``source: industry_preset``. It deliberately excludes members,
    credentials, and anything not needed to plan or write marketing content.
    """
    profile = get_profile(org)
    guideline = get_guideline(org)
    preset = PRESETS_BY_KEY.get(profile.industry)
    audiences = TargetAudience.objects.filter(organization=org)
    return {
        "business": {
            "source": "user",
            "name": profile.business_name or org.name,
            "industry": preset["label"] if preset else None,
            "website": profile.website or None,
            "description": profile.description or None,
            "products_services": profile.products_services,
            "location": profile.location or None,
            "service_area": profile.service_area or None,
            "languages": profile.languages or ["en"],
        },
        "goals": {
            "source": "user",
            "items": [GOALS.get(g, g) for g in profile.goals],
        },
        "platforms": {
            "source": "user",
            "items": [PLATFORMS.get(p, p) for p in profile.preferred_platforms],
        },
        "audiences": {
            "source": "user",
            "items": [
                {
                    "name": a.name,
                    "description": a.description or None,
                    "age_range": a.age_range or None,
                    "locations": a.locations or None,
                    "interests": a.interests,
                    "pain_points": a.pain_points,
                    "primary": a.is_primary,
                }
                for a in audiences
            ],
        },
        "brand_voice": {
            "source": "user",
            "tone": guideline.tone,
            "description": guideline.voice_description or None,
            "do": guideline.do_list,
            "dont": guideline.dont_list,
            "example_posts": guideline.example_posts[:5],
        },
        "restrictions": {
            "source": "user",
            "claims_to_avoid": guideline.restricted_claims,
        },
        "industry_guidance": (
            {
                "source": "industry_preset",
                "note": "Generic suggestions for this industry, not facts about this business.",
                "content_themes": preset["content_themes"],
                "compliance_notes": preset["compliance_notes"],
            }
            if preset
            else None
        ),
    }
