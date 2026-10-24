from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdAccountViewSet, AdCampaignViewSet, AdInsightsSummaryView

router = SimpleRouter()
router.register("ads/accounts", AdAccountViewSet, basename="ad-account")
router.register("ads/campaigns", AdCampaignViewSet, basename="ad-campaign")
urlpatterns = [
    path("ads/insights/", AdInsightsSummaryView.as_view(), name="ads-insights"),
    *router.urls,
]
