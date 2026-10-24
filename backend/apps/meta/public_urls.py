from django.urls import path

from .views import DataDeletionStatusView, DataDeletionView, DeauthorizeView, WebhookView

urlpatterns = [
    path("webhooks/", WebhookView.as_view(), name="meta-webhooks"),
    path("deauthorize/", DeauthorizeView.as_view(), name="meta-deauthorize"),
    path("data-deletion/", DataDeletionView.as_view(), name="meta-data-deletion"),
    path(
        "data-deletion/<str:code>/",
        DataDeletionStatusView.as_view(),
        name="meta-data-deletion-status",
    ),
]
