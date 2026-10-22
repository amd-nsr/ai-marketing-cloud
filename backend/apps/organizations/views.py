from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import current_user

from . import services
from .api import OrganizationScopedMixin, OrganizationScopedViewSet
from .models import Invitation, Membership, Organization
from .roles import Perm
from .serializers import (
    AcceptInvitationSerializer,
    InvitationSerializer,
    MemberSerializer,
    MembershipSummarySerializer,
    OrganizationSerializer,
    RoleUpdateSerializer,
)


class OrganizationListCreateView(ListCreateAPIView):  # type: ignore[type-arg]
    """Organizations the caller belongs to; POST creates one with the caller as owner."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> Any:
        return Organization.objects.filter(memberships__user=current_user(self.request)).order_by(
            "name"
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = services.create_organization(
            user=request.user, name=serializer.validated_data["name"], request=request
        )
        return Response(self.get_serializer(org).data, status=status.HTTP_201_CREATED)


class OrganizationDetailView(OrganizationScopedMixin, APIView):
    read_permission = Perm.ORG_VIEW
    write_permission = Perm.ORG_MANAGE

    @extend_schema(responses=OrganizationSerializer)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(OrganizationSerializer(self.organization).data)

    @extend_schema(request=OrganizationSerializer, responses=OrganizationSerializer)
    def patch(self, request: Request, org_id: str) -> Response:
        serializer = OrganizationSerializer(self.organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        org = services.update_organization(
            self.organization,
            actor=request.user,
            name=serializer.validated_data.get("name", self.organization.name),
            request=request,
        )
        return Response(OrganizationSerializer(org).data)


class MyMembershipView(OrganizationScopedMixin, APIView):
    """The caller's role and permissions in this organization."""

    @extend_schema(responses=MembershipSummarySerializer)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(MembershipSummarySerializer(self.membership).data)


class MemberViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    model = Membership
    serializer_class = MemberSerializer
    read_permission = Perm.MEMBERS_VIEW
    write_permission = Perm.MEMBERS_MANAGE

    def get_queryset(self) -> Any:
        return super().get_queryset().select_related("user").order_by("created_at")

    def required_permission(self, request: Request) -> str | None:
        # Any member may leave (delete their own membership).
        if self.action == "destroy" and str(self.kwargs.get("pk")) == str(self.membership.pk):
            return None
        return super().required_permission(request)

    @extend_schema(request=RoleUpdateSerializer, responses=MemberSerializer)
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = RoleUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        updated = services.change_role(
            actor=self.membership,
            membership=self.get_object(),
            role=payload.validated_data["role"],
            request=request,
        )
        return Response(MemberSerializer(updated).data)

    def perform_destroy(self, instance: Membership) -> None:
        services.remove_member(actor=self.membership, membership=instance, request=self.request)


class InvitationViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
):
    model = Invitation
    serializer_class = InvitationSerializer
    read_permission = Perm.MEMBERS_MANAGE
    write_permission = Perm.MEMBERS_MANAGE

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("invited_by").order_by("-created_at")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.invite_member(
            actor=self.membership,
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            request=request,
        )
        return Response(self.get_serializer(invitation).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Invitation) -> None:
        services.revoke_invitation(actor=self.membership, invitation=instance, request=self.request)


class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=AcceptInvitationSerializer, responses=MembershipSummarySerializer)
    def post(self, request: Request) -> Response:
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            user=request.user, token=serializer.validated_data["token"], request=request
        )
        return Response(MembershipSummarySerializer(membership).data)
