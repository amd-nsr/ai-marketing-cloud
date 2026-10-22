from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("recommendations", views.RecommendationViewSet, basename="recommendation")

urlpatterns = [
    path("analytics/overview/", views.AnalyticsOverviewView.as_view(), name="analytics-overview"),
    path("analytics/posts/", views.AnalyticsPostsView.as_view(), name="analytics-posts"),
    path("analytics/trend/", views.AnalyticsTrendView.as_view(), name="analytics-trend"),
    path("analytics/refresh/", views.AnalyticsRefreshView.as_view(), name="analytics-refresh"),
    *router.urls,
]
