from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AcceptInvitationView,
    InvitationViewSet,
    MemberViewSet,
    MyMembershipView,
    OrganizationDetailView,
    OrganizationListCreateView,
)

router = SimpleRouter()
router.register("members", MemberViewSet, basename="member")
router.register("invitations", InvitationViewSet, basename="invitation")

org_patterns: list[URLPattern | URLResolver] = [
    path("", OrganizationDetailView.as_view(), name="organization-detail"),
    path("me/", MyMembershipView.as_view(), name="organization-my-membership"),
    path("", include(router.urls)),
    path("audit-events/", include("apps.audit.urls")),
    path("", include("apps.brand.urls")),
    path("", include("apps.ai.urls")),
    path("", include("apps.usage.urls")),
    path("", include("apps.marketing.urls")),
    path("", include("apps.content.urls")),
    path("", include("apps.social.urls")),
    path("", include("apps.publishing.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.automation.urls")),
    path("", include("apps.operations.urls")),
]

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organization-list"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    path("<uuid:org_id>/", include(org_patterns)),
]
