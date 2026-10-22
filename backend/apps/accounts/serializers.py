from typing import Any

from django.contrib.auth import password_validation
from rest_framework import serializers

from apps.organizations.serializers import MembershipSummarySerializer

from .models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "date_joined"]
        read_only_fields = ["id", "email", "date_joined"]


class MeSerializer(serializers.Serializer[User]):
    user = UserSerializer(source="*")
    memberships = serializers.SerializerMethodField()

    def get_memberships(self, user: User) -> list[dict[str, Any]]:
        qs = user.memberships.select_related("organization").order_by("organization__name")
        return MembershipSummarySerializer(qs, many=True).data  # type: ignore[return-value]


class RegisterSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        candidate = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs


class LoginSerializer(serializers.Serializer[None]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer[None]):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Incorrect password."})
        password_validation.validate_password(attrs["new_password"], user=user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer[None]):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer[None]):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
