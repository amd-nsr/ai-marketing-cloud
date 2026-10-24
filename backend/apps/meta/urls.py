from rest_framework.routers import SimpleRouter

from .views import MetaConnectionViewSet

router = SimpleRouter()
router.register("meta/connections", MetaConnectionViewSet, basename="meta-connection")
urlpatterns = router.urls
