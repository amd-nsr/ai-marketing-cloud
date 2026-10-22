from rest_framework.routers import SimpleRouter

from .views import PublishedPostViewSet, PublishingJobViewSet

router = SimpleRouter()
router.register("publishing/jobs", PublishingJobViewSet, basename="publishing-job")
router.register("publishing/posts", PublishedPostViewSet, basename="published-post")
urlpatterns = router.urls
