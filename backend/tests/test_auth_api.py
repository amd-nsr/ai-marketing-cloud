import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def csrf_client() -> APIClient:
    """A client that enforces CSRF exactly like a browser session would."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    sync_csrf(client)
    return client


def sync_csrf(client: APIClient) -> None:
    """Echo the current CSRF cookie in the header, as the frontend does per request.

    Django rotates the token at login, so a header captured earlier goes stale.
    """
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)


def login(client: APIClient, email: str, password: str = PASSWORD):
    response = client.post(
        "/api/v1/auth/login/", {"email": email, "password": password}, format="json"
    )
    sync_csrf(client)
    return response


def test_register_logs_in_and_returns_profile():
    client = csrf_client()
    response = client.post(
        "/api/v1/auth/register/",
        {"email": "New@Example.com", "password": PASSWORD, "full_name": "Nadia"},
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert response.json()["user"]["email"] == "new@example.com"
    assert response.json()["memberships"] == []
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert AuditEvent.objects.filter(action="user.registered").exists()


def test_register_rejects_weak_password_and_duplicate_email(make_user):
    make_user("taken@example.com")
    client = csrf_client()
    weak = client.post(
        "/api/v1/auth/register/", {"email": "a@example.com", "password": "short"}, format="json"
    )
    assert weak.status_code == 400
    dup = client.post(
        "/api/v1/auth/register/",
        {"email": "TAKEN@example.com", "password": PASSWORD},
        format="json",
    )
    assert dup.status_code == 400
    assert "email" in dup.json()["error"]["details"]


def test_login_requires_csrf_token():
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/login/", {"email": "x@example.com", "password": "x"}, format="json"
    )
    assert response.status_code == 403


def test_login_success_and_generic_failure(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    bad = client.post(
        "/api/v1/auth/login/", {"email": "owner@example.com", "password": "wrong"}, format="json"
    )
    assert bad.status_code in (401, 403)
    assert bad.json()["error"]["message"] == "Invalid email or password."
    unknown = client.post(
        "/api/v1/auth/login/", {"email": "nobody@example.com", "password": "x"}, format="json"
    )
    assert unknown.json()["error"]["message"] == "Invalid email or password."
    ok = client.post(
        "/api/v1/auth/login/", {"email": "OWNER@example.com", "password": PASSWORD}, format="json"
    )
    assert ok.status_code == 200
    assert AuditEvent.objects.filter(action="user.login_failed").count() == 2


def test_authenticated_unsafe_requests_require_csrf(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    login(client, "owner@example.com")
    client.credentials()  # drop the CSRF header
    response = client.post("/api/v1/orgs/", {"name": "Acme"}, format="json")
    assert response.status_code == 403


def test_logout_ends_session(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    login(client, "owner@example.com")
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 403


def test_login_is_rate_limited(settings, make_user):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "auth": "3/min",
        },
    }
    from rest_framework.settings import api_settings
    from rest_framework.throttling import SimpleRateThrottle

    SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
    try:
        client = csrf_client()
        codes = [
            client.post(
                "/api/v1/auth/login/", {"email": "a@example.com", "password": "x"}, format="json"
            ).status_code
            for _ in range(4)
        ]
    finally:
        SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
    assert codes[-1] == 429
    assert codes[:3] != [429, 429, 429]


def test_password_change_keeps_session(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    login(client, "owner@example.com")
    response = client.post(
        "/api/v1/auth/password/change/",
        {"current_password": PASSWORD, "new_password": "another-long-passphrase-42"},
        format="json",
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert User.objects.get().check_password("another-long-passphrase-42")


def test_password_reset_flow(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    response = client.post(
        "/api/v1/auth/password/reset/", {"email": "owner@example.com"}, format="json"
    )
    assert response.status_code == 202
    assert len(mail.outbox) == 1
    match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[0].body)
    assert match
    uid, token = match.groups()
    confirm = client.post(
        "/api/v1/auth/password/reset/confirm/",
        {"uid": uid, "token": token, "new_password": "brand-new-passphrase-77"},
        format="json",
    )
    assert confirm.status_code == 204
    reuse = client.post(
        "/api/v1/auth/password/reset/confirm/",
        {"uid": uid, "token": token, "new_password": "yet-another-passphrase-88"},
        format="json",
    )
    assert reuse.status_code == 400  # token is single-use (password hash changed)


def test_password_reset_does_not_reveal_unknown_emails():
    client = csrf_client()
    response = client.post(
        "/api/v1/auth/password/reset/", {"email": "nobody@example.com"}, format="json"
    )
    assert response.status_code == 202
    assert len(mail.outbox) == 0


def test_login_rotates_csrf_token(make_user):
    make_user("owner@example.com")
    client = csrf_client()
    before = client.cookies["csrftoken"].value
    client.post(
        "/api/v1/auth/login/", {"email": "owner@example.com", "password": PASSWORD}, format="json"
    )
    assert client.cookies["csrftoken"].value != before
    # The stale header is rejected; the frontend therefore reads the cookie per request.
    assert client.post("/api/v1/auth/logout/").status_code == 403
