import logging

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpRequest
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit

from .models import User

logger = logging.getLogger(__name__)


def register_user(
    *, email: str, password: str, full_name: str = "", request: HttpRequest | None = None
) -> User:
    user = User.objects.create_user(email=email, password=password, full_name=full_name)
    audit.record("user.registered", actor=user, target=user, request=request)
    return user


def request_password_reset(email: str, request: HttpRequest | None = None) -> None:
    """Send a reset link if the account exists. Callers always report success."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None or not user.has_usable_password():
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
    try:
        send_mail(
            subject="Reset your AI Marketing Cloud password",
            message=(
                "We received a request to reset your password.\n\n"
                f"Choose a new password: {url}\n\n"
                "If you didn't ask for this, you can ignore this email."
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception:
        logger.exception("Failed to send password reset email")
    audit.record("user.password_reset_requested", actor=None, target=user, request=request)


def confirm_password_reset(
    *, uid: str, token: str, new_password: str, request: HttpRequest | None = None
) -> User:
    invalid = ValidationError({"token": "This reset link is invalid or has expired."})
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError) as exc:
        raise invalid from exc
    if not default_token_generator.check_token(user, token):
        raise invalid
    password_validation.validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    audit.record("user.password_reset", actor=user, target=user, request=request)
    return user
