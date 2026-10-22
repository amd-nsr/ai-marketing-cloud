from rest_framework import serializers

from .models import Invitation, Membership, Organization
from .roles import Role


class OrganizationSerializer(serializers.ModelSerializer[Organization]):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        return value


class MembershipSummarySerializer(serializers.ModelSerializer[Membership]):
    """A caller's own membership, used by /auth/me/ and the org switcher."""

    organization = OrganizationSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["id", "organization", "role", "permissions"]

    def get_permissions(self, obj: Membership) -> list[str]:
        return sorted(obj.permissions)


class MemberSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "full_name", "role", "created_at"]
        read_only_fields = ["id", "user_id", "email", "full_name", "created_at"]


class RoleUpdateSerializer(serializers.Serializer[None]):
    role = serializers.ChoiceField(choices=Role.choices)


class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "status",
            "invited_by_email",
            "expires_at",
            "accepted_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "invited_by_email",
            "expires_at",
            "accepted_at",
            "created_at",
        ]


class AcceptInvitationSerializer(serializers.Serializer[None]):
    token = serializers.CharField(max_length=64)
