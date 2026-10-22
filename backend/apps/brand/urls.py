from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("brand/audiences", views.TargetAudienceViewSet, basename="audience")
router.register("brand/assets", views.BrandAssetViewSet, basename="brand-asset")

urlpatterns = [
    path("business-profile/", views.BusinessProfileView.as_view(), name="business-profile"),
    path("brand/guidelines/", views.BrandGuidelineView.as_view(), name="brand-guidelines"),
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("business-context/", views.BusinessContextView.as_view(), name="business-context"),
    path("", include(router.urls)),
]
