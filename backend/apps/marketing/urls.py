from rest_framework.routers import SimpleRouter

from .views import CampaignViewSet, MarketingPlanViewSet

router = SimpleRouter()
router.register("marketing-plans", MarketingPlanViewSet, basename="marketing-plan")
router.register("campaigns", CampaignViewSet, basename="campaign")

urlpatterns = router.urls
