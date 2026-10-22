from django.urls import path

from .views import OperationsOverviewView

urlpatterns = [
    path("operations/", OperationsOverviewView.as_view(), name="operations-overview"),
]
