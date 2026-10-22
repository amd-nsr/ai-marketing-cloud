from django.urls import reverse


def test_generates_request_id_when_absent(api_client):
    response = api_client.get(reverse("health-live"))
    assert len(response["X-Request-ID"]) == 32


def test_propagates_safe_incoming_request_id(api_client):
    response = api_client.get(reverse("health-live"), HTTP_X_REQUEST_ID="frontend-abc.123")
    assert response["X-Request-ID"] == "frontend-abc.123"


def test_replaces_unsafe_incoming_request_id(api_client):
    response = api_client.get(reverse("health-live"), HTTP_X_REQUEST_ID="bad id\r\ninjected")
    assert response["X-Request-ID"] != "bad id\r\ninjected"
    assert len(response["X-Request-ID"]) == 32
