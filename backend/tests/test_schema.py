import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_openapi_schema_is_generated_and_lists_health_endpoints(api_client):
    staff = User.objects.create_user("staff@example.com", "a-long-test-password", is_staff=True)
    api_client.force_authenticate(staff)
    response = api_client.get(reverse("openapi-schema"), HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health/live/" in paths
    assert "/api/v1/health/ready/" in paths


@pytest.mark.parametrize("staff", [None, False])
def test_openapi_schema_is_not_served_to_anonymous_or_regular_users(api_client, staff):
    if staff is not None:
        user = User.objects.create_user("user@example.com", "a-long-test-password")
        api_client.force_authenticate(user)
    response = api_client.get(reverse("openapi-schema"))
    assert response.status_code == 403
