import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import path
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class _Payload(serializers.Serializer):
    name = serializers.CharField(max_length=5)


class _ErrorView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, kind: str):
        if kind == "404":
            raise Http404("secret-object-name")
        if kind == "403":
            raise PermissionDenied
        if kind == "crash":
            raise RuntimeError("database password is hunter2")
        return Response({"ok": True})

    def post(self, request, kind: str):
        _Payload(data=request.data).is_valid(raise_exception=True)
        return Response({"ok": True})


class _ProtectedView(APIView):
    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("err/<str:kind>/", _ErrorView.as_view()),
    path("protected/", _ProtectedView.as_view()),
]


@pytest.fixture(autouse=True)
def _urls(settings):
    settings.ROOT_URLCONF = __name__


def _assert_envelope(body: dict, code: str) -> None:
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["request_id"]


def test_not_found_envelope_hides_internal_message(api_client):
    response = api_client.get("/err/404/")
    assert response.status_code == 404
    _assert_envelope(response.json(), "not_found")
    assert "secret-object-name" not in response.content.decode()


def test_permission_denied_envelope(api_client):
    response = api_client.get("/err/403/")
    assert response.status_code == 403
    _assert_envelope(response.json(), "permission_denied")


def test_unauthenticated_requests_are_rejected_by_default(api_client):
    response = api_client.get("/protected/")
    assert response.status_code == 403  # Session auth has no WWW-Authenticate challenge.
    _assert_envelope(response.json(), "not_authenticated")


def test_validation_error_envelope_includes_field_details(api_client):
    response = api_client.post("/err/x/", {"name": "too-long-name"}, format="json")
    assert response.status_code == 400
    body = response.json()
    _assert_envelope(body, "validation_error")
    assert "name" in body["error"]["details"]


def test_unhandled_exception_returns_generic_500_without_leaking(api_client):
    api_client.raise_request_exception = False
    response = api_client.get("/err/crash/")
    assert response.status_code == 500
    _assert_envelope(response.json(), "server_error")
    assert "hunter2" not in response.content.decode()


def test_request_id_matches_response_header(api_client):
    response = api_client.get("/err/404/")
    assert response["X-Request-ID"] == response.json()["error"]["request_id"]


def test_unknown_url_returns_json_envelope(client, settings):
    settings.ROOT_URLCONF = "config.urls"
    response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert response["Content-Type"] == "application/json"
    _assert_envelope(response.json(), "not_found")
