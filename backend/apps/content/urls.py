from rest_framework.routers import SimpleRouter

from .views import (
    ApprovalViewSet,
    ContentItemViewSet,
    ContentTemplateViewSet,
    LibraryAssetViewSet,
    RenderJobViewSet,
)

router = SimpleRouter()
router.register("content-templates", ContentTemplateViewSet, basename="content-template")
router.register("render-jobs", RenderJobViewSet, basename="render-job")
router.register("library", LibraryAssetViewSet, basename="library-asset")
router.register("content", ContentItemViewSet, basename="content")
router.register("approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
