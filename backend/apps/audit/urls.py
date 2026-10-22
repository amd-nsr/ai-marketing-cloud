from django.urls import path

from .views import AuditEventViewSet

urlpatterns = [
    path("", AuditEventViewSet.as_view({"get": "list"}), name="audit-event-list"),
]
