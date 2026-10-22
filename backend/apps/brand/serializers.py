import re
from typing import Any

from rest_framework import serializers

from .models import BrandAsset, BrandGuideline, BusinessProfile, TargetAudience
from .presets import PLATFORMS

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def string_list(max_items: int = 20, max_length: int = 200) -> serializers.ListField:
    return serializers.ListField(
        child=serializers.CharField(max_length=max_length, trim_whitespace=True),
        max_length=max_items,
        required=False,
    )


class ProductServiceSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )


class BusinessProfileSerializer(serializers.ModelSerializer[BusinessProfile]):
    products_services = ProductServiceSerializer(many=True, required=False)
    goals = string_list(10, 200)
    preferred_platforms = serializers.ListField(
        child=serializers.ChoiceField(choices=list(PLATFORMS)), required=False, max_length=3
    )
    languages = string_list(5, 10)

    class Meta:
        model = BusinessProfile
        fields = [
            "business_name",
            "industry",
            "website",
            "description",
            "products_services",
            "location",
            "service_area",
            "goals",
            "preferred_platforms",
            "languages",
            "onboarding_completed_at",
            "updated_at",
        ]
        read_only_fields = ["onboarding_completed_at", "updated_at"]

    def validate_products_services(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 30:
            raise serializers.ValidationError("Add at most 30 products or services.")
        return [{"name": v["name"], "description": v.get("description", "")} for v in value]

    def validate_languages(self, value: list[str]) -> list[str]:
        for code in value:
            if not _LANG.match(code):
                raise serializers.ValidationError(
                    f"'{code}' is not a language code like 'en' or 'ar'."
                )
        return list(dict.fromkeys(value))

    def validate_goals(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(v for v in value if v))

    def validate_preferred_platforms(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class BrandGuidelineSerializer(serializers.ModelSerializer[BrandGuideline]):
    tone = string_list(8, 40)
    do_list = string_list(20, 300)
    dont_list = string_list(20, 300)
    restricted_claims = string_list(30, 300)
    example_posts = string_list(10, 2200)
    colors = string_list(10, 7)
    fonts = string_list(5, 80)

    class Meta:
        model = BrandGuideline
        fields = [
            "tone",
            "voice_description",
            "do_list",
            "dont_list",
            "restricted_claims",
            "example_posts",
            "colors",
            "fonts",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_colors(self, value: list[str]) -> list[str]:
        for c in value:
            if not _HEX.match(c):
                raise serializers.ValidationError(f"'{c}' is not a hex colour like #1A2B3C.")
        return [c.upper() for c in value]


class TargetAudienceSerializer(serializers.ModelSerializer[TargetAudience]):
    interests = string_list(15, 100)
    pain_points = string_list(15, 200)

    class Meta:
        model = TargetAudience
        fields = [
            "id",
            "name",
            "description",
            "age_range",
            "locations",
            "interests",
            "pain_points",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BrandAssetSerializer(serializers.ModelSerializer[BrandAsset]):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BrandAsset
        fields = [
            "id",
            "kind",
            "title",
            "original_filename",
            "content_type",
            "size_bytes",
            "width",
            "height",
            "file_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_file_url(self, obj: BrandAsset) -> str:
        # Authorized download endpoint (proxied same-origin), never a raw storage URL.
        return f"/api/v1/orgs/{obj.organization_id}/brand/assets/{obj.id}/file/"


class BrandAssetUploadSerializer(serializers.Serializer[None]):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=BrandAsset.Kind.choices, default=BrandAsset.Kind.IMAGE)
    title = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")


class OnboardingStepSerializer(serializers.Serializer[dict[str, Any]]):
    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]  # shadows Field.label
    required = serializers.BooleanField()  # type: ignore[assignment]  # shadows Field.required
    complete = serializers.BooleanField()


class OnboardingStatusSerializer(serializers.Serializer[dict[str, Any]]):
    steps = OnboardingStepSerializer(many=True)
    percent = serializers.IntegerField()
    can_complete = serializers.BooleanField()
    completed_at = serializers.DateTimeField(allow_null=True)


class IndustryPresetSerializer(serializers.Serializer[None]):
    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]  # shadows Field.label
    suggested_goals = serializers.ListField(child=serializers.CharField())
    suggested_platforms = serializers.ListField(child=serializers.CharField())
    example_audiences = serializers.ListField(child=serializers.CharField())
    content_themes = serializers.ListField(child=serializers.CharField())
    compliance_notes = serializers.ListField(child=serializers.CharField())


class ReferenceDataSerializer(serializers.Serializer[None]):
    industries = IndustryPresetSerializer(many=True)
    goals = serializers.DictField(child=serializers.CharField())
    platforms = serializers.DictField(child=serializers.CharField())
