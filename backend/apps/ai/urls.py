from rest_framework.routers import SimpleRouter

from .views import AIWorkflowRunViewSet

router = SimpleRouter()
router.register("ai/runs", AIWorkflowRunViewSet, basename="ai-run")

urlpatterns = router.urls
