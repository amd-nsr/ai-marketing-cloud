from django.urls import path

from .views import UsageSummaryView

urlpatterns = [path("usage/", UsageSummaryView.as_view(), name="usage-summary")]
