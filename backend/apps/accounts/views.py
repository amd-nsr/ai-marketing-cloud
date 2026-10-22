from typing import Any

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit

from . import services
from .models import current_user
from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import AuthRateThrottle

_ok = inline_serializer("Ok", {"detail": serializers.CharField()})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the CSRF cookie. The frontend calls this before its first unsafe request."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(responses=_ok, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response({"detail": "CSRF cookie set."})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: MeSerializer}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(**serializer.validated_data, request=request)
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=LoginSerializer, responses=MeSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            audit.record(
                "user.login_failed",
                metadata={"email": serializer.validated_data["email"].lower()},
                request=request._request,
            )
            raise AuthenticationFailed("Invalid email or password.")
        login(request._request, user)
        audit.record("user.logged_in", actor=user, target=user, request=request._request)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        if request.user.is_authenticated:
            audit.record("user.logged_out", actor=request.user, request=request._request)
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(current_user(request)).data)

    @extend_schema(request=UserSerializer, responses=MeSerializer, tags=["auth"])
    def patch(self, request: Request) -> Response:
        user = current_user(request)
        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(user).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=PasswordChangeSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user: Any = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        update_session_auth_hash(request._request, user)
        audit.record("user.password_changed", actor=user, target=user, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses={202: _ok}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(
            serializer.validated_data["email"], request=request._request
        )
        return Response(
            {"detail": "If an account exists for this email, a reset link has been sent."},
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(**serializer.validated_data, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
