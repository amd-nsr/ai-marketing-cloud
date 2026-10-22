from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("automation/actions", views.ActionViewSet, basename="automation-action")

urlpatterns = [
    path("automation/policy/", views.PolicyView.as_view(), name="automation-policy"),
    path(
        "automation/pause/",
        views.PolicyControlView.as_view(command="pause"),
        name="automation-pause",
    ),
    path(
        "automation/resume/",
        views.PolicyControlView.as_view(command="resume"),
        name="automation-resume",
    ),
    path(
        "automation/cancel-pending/",
        views.CancelPendingView.as_view(),
        name="automation-cancel-pending",
    ),
    path("automation/run-now/", views.RunNowView.as_view(), name="automation-run-now"),
    *router.urls,
]
