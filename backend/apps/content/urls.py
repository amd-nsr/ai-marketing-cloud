from rest_framework.routers import SimpleRouter

from .views import ApprovalViewSet, ContentItemViewSet

router = SimpleRouter()
router.register("content", ContentItemViewSet, basename="content")
router.register("approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
