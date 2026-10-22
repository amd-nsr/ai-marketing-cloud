from rest_framework.routers import SimpleRouter

from .views import SocialAccountViewSet

router = SimpleRouter()
router.register("social/accounts", SocialAccountViewSet, basename="social-account")
urlpatterns = router.urls
