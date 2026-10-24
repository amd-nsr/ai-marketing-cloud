import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from django.utils import timezone

from apps.social.adapters import base as b
from apps.social.adapters.facebook import FacebookAdapter
from apps.social.adapters.instagram import InstagramAdapter
from apps.social.adapters.tiktok import TikTokAdapter
from apps.social.models import OAuthState, SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def connect_mock(client, org, platform="instagram"):
    start = client.post(
        url(org, "social/accounts/connect/"),
        {"platform": platform, "simulation": True},
        format="json",
    )
    assert start.status_code == 200, start.json()
    qs = parse_qs(urlparse(start.json()["authorization_url"]).query)
    return client.post(
        "/api/v1/social/oauth/callback/",
        {"state": qs["state"][0], "code": qs["code"][0]},
        format="json",
    )


# --- API ------------------------------------------------------------------------------


def test_platform_catalogue_reports_configuration(org_client):
    client, org = org_client("editor")
    platforms = {
        p["platform"]: p for p in client.get(url(org, "social/accounts/platforms/")).json()
    }
    assert set(platforms) == {"instagram", "facebook", "tiktok"}
    assert all(p["configured"] is False for p in platforms.values())  # no app credentials in tests
    assert platforms["facebook"]["simulation_available"] is True
    assert platforms["instagram"]["supports_text_only"] is False


def test_real_connection_requires_app_credentials(org_client):
    client, org = org_client("owner")
    response = client.post(
        url(org, "social/accounts/connect/"), {"platform": "facebook"}, format="json"
    )
    assert response.status_code == 400
    assert "configured" in json.dumps(response.json())


def test_simulated_connection_stores_encrypted_tokens(org_client):
    client, org = org_client("owner")
    response = connect_mock(client, org)
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["organization_id"] == str(org.id)
    account = payload["accounts"][0]
    assert account["is_mock"] is True and account["status"] == "connected"
    assert not any("token" in k and "expires" not in k for k in account)  # no token fields exposed
    stored = SocialAccount.objects.get(pk=account["id"])
    assert stored.access_token_enc and "mock-token" not in stored.access_token_enc
    assert stored.access_token == "mock-token-instagram"


def test_oauth_state_is_single_use_user_bound_and_expires(org_client, make_user):
    client, org = org_client("owner")
    start = client.post(
        url(org, "social/accounts/connect/"),
        {"platform": "facebook", "simulation": True},
        format="json",
    )
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    other, _ = org_client("owner")
    assert (
        other.post(
            "/api/v1/social/oauth/callback/", {"state": state, "code": "x"}, format="json"
        ).status_code
        == 403
    )

    assert (
        client.post(
            "/api/v1/social/oauth/callback/", {"state": state, "code": "x"}, format="json"
        ).status_code
        == 200
    )
    reuse = client.post(
        "/api/v1/social/oauth/callback/", {"state": state, "code": "x"}, format="json"
    )
    assert reuse.status_code == 400

    start = client.post(
        url(org, "social/accounts/connect/"),
        {"platform": "facebook", "simulation": True},
        format="json",
    )
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    OAuthState.objects.filter(state=state).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert (
        client.post(
            "/api/v1/social/oauth/callback/", {"state": state, "code": "x"}, format="json"
        ).status_code
        == 400
    )


def test_only_managers_connect_and_disconnect(org_client):
    owner, org = org_client("owner")
    connect_mock(owner, org)
    editor, _ = org_client("editor", org=org)
    assert editor.get(url(org, "social/accounts/")).json()["count"] == 1
    assert (
        editor.post(
            url(org, "social/accounts/connect/"),
            {"platform": "facebook", "simulation": True},
            format="json",
        ).status_code
        == 403
    )
    account = SocialAccount.objects.get(organization=org)
    assert editor.delete(url(org, f"social/accounts/{account.id}/")).status_code == 403
    analyst, _ = org_client("analyst", org=org)
    assert analyst.get(url(org, "social/accounts/")).status_code == 403


def test_disconnect_destroys_tokens(org_client):
    client, org = org_client("owner")
    connect_mock(client, org)
    account = SocialAccount.objects.get(organization=org)
    assert client.delete(url(org, f"social/accounts/{account.id}/")).status_code == 204
    account.refresh_from_db()
    assert (
        account.status == "disconnected"
        and account.access_token_enc == ""
        and account.access_token is None
    )
    assert client.get(url(org, "social/accounts/")).json()["count"] == 0


def test_simulation_can_be_disabled(org_client, settings):
    settings.SOCIAL_MOCK_ENABLED = False
    client, org = org_client("owner")
    response = client.post(
        url(org, "social/accounts/connect/"),
        {"platform": "facebook", "simulation": True},
        format="json",
    )
    assert response.status_code == 400


def test_accounts_are_tenant_isolated(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    connect_mock(client_b, org_b)
    account_b = SocialAccount.objects.get(organization=org_b)
    assert client_a.get(url(org_a, f"social/accounts/{account_b.id}/")).status_code == 404
    assert client_a.delete(url(org_a, f"social/accounts/{account_b.id}/")).status_code == 404


# --- Facebook adapter (Graph API stubbed) ------------------------------------------------------


def fb(handler) -> FacebookAdapter:
    return FacebookAdapter(
        app_id="app",
        app_secret="secret",
        graph_version="v26.0",
        transport=httpx.MockTransport(handler),
    )


ACCOUNT = b.AccountRef(external_id="page1", access_token="page-token", metadata={})


def test_facebook_authorization_url():
    adapter = fb(lambda r: httpx.Response(200, json={}))
    parsed = urlparse(
        adapter.authorization_url(state="s1", redirect_uri="https://app/cb", code_challenge="c")
    )
    assert parsed.netloc == "www.facebook.com" and parsed.path == "/v26.0/dialog/oauth"
    qs = parse_qs(parsed.query)
    assert qs["state"] == ["s1"] and "pages_manage_posts" in qs["scope"][0]


def test_facebook_completes_authorization_with_publishable_pages_only():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token", "expires_in": 5000})
        assert request.url.path.endswith("me/accounts")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1",
                        "name": "Cafe",
                        "access_token": "p1",
                        "tasks": ["CREATE_CONTENT", "MODERATE"],
                    },
                    {"id": "2", "name": "Read only", "access_token": "p2", "tasks": ["ANALYZE"]},
                ]
            },
        )

    accounts = fb(handler).complete_authorization(
        code="c", redirect_uri="https://app/cb", code_verifier="v"
    )
    assert [(a.external_id, a.access_token) for a in accounts] == [("1", "p1")]


def test_facebook_text_and_photo_publish():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("content-type", "")))
        if request.url.path.endswith("/feed"):
            return httpx.Response(200, json={"id": "page1_111"})
        return httpx.Response(200, json={"id": "photo1", "post_id": "page1_222"})

    adapter = fb(handler)
    text = adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="Hello"))
    assert text.external_post_id == "page1_111"
    photo = adapter.publish(
        ACCOUNT,
        b.PublishRequest(
            format="post", text="Hi", media=(b.MediaFile(b"\xff\xd8", "image/jpeg", "a.jpg"),)
        ),
    )
    assert photo.external_post_id == "page1_222"
    assert seen[1][0].endswith("/page1/photos") and "multipart/form-data" in seen[1][1]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"code": 190, "type": "OAuthException", "message": "expired"}, b.ReauthRequired),
        ({"code": 200, "message": "permission"}, b.ReauthRequired),
        ({"code": 4, "message": "too many calls"}, b.RateLimited),
        ({"code": 2, "message": "temporary"}, b.TransientError),
        ({"code": 100, "message": "invalid parameter"}, b.ContentRejected),
    ],
)
def test_facebook_error_normalization(error, expected):
    adapter = fb(lambda r: httpx.Response(400, json={"error": error}))
    with pytest.raises(expected):
        adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="x"))


def test_facebook_timeout_on_write_is_uncertain_but_on_read_is_transient():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    adapter = fb(timeout)
    with pytest.raises(b.UncertainOutcome):
        adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="x"))
    with pytest.raises(b.TransientError):
        adapter.find_recent_post(ACCOUNT, text="x", since=datetime.now(UTC))


def test_facebook_metrics_keep_missing_values_missing():
    body = {
        "data": [
            {"name": "post_media_view", "values": [{"value": 120}]},
            {"name": "post_reactions_by_type_total", "values": [{"value": {"like": 3, "love": 2}}]},
        ]
    }
    metrics = {
        m.key: m.value
        for m in fb(lambda r: httpx.Response(200, json=body)).fetch_post_metrics(ACCOUNT, "p")
    }
    assert metrics == {"views": 120.0, "reach": None, "clicks": None, "reactions": 5.0}


def test_facebook_rejects_unsupported_formats():
    with pytest.raises(b.Unsupported):
        fb(lambda r: httpx.Response(200, json={})).publish(
            ACCOUNT, b.PublishRequest(format="reel", text="x")
        )


# --- Instagram & TikTok adapters -------------------------------------------------------------


def ig(handler) -> InstagramAdapter:
    adapter = InstagramAdapter(
        app_id="app", app_secret="s", graph_version="v26.0", transport=httpx.MockTransport(handler)
    )
    adapter.container_poll_seconds = 0
    return adapter


def test_instagram_requires_public_jpeg():
    adapter = ig(lambda r: httpx.Response(200, json={}))
    png = b.MediaFile(b"x", "image/png", "a.png", public_url="https://cdn/a.png")
    with pytest.raises(b.ContentRejected, match="JPEG"):
        adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="x", media=(png,)))
    private = b.MediaFile(b"x", "image/jpeg", "a.jpg")
    with pytest.raises(b.ContentRejected, match="public URL"):
        adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="x", media=(private,)))
    with pytest.raises(b.ContentRejected):
        adapter.publish(ACCOUNT, b.PublishRequest(format="post", text="text only"))


def test_instagram_container_then_publish():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/media") and request.method == "POST":
            return httpx.Response(200, json={"id": "container1"})
        if request.url.path.endswith("container1"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.url.path.endswith("media_publish"):
            return httpx.Response(200, json={"id": "media1"})
        return httpx.Response(200, json={"permalink": "https://instagram.com/p/abc"})

    media = b.MediaFile(b"x", "image/jpeg", "a.jpg", public_url="https://cdn/a.jpg")
    result = ig(handler).publish(
        ACCOUNT, b.PublishRequest(format="post", text="Hi", media=(media,))
    )
    assert result.external_post_id == "media1" and result.permalink.endswith("/abc")
    assert [p.rsplit("/", 1)[-1] for p in calls[:3]] == ["media", "container1", "media_publish"]


def test_instagram_container_error_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "c1"})
        return httpx.Response(200, json={"status_code": "ERROR"})

    media = b.MediaFile(b"x", "image/jpeg", "a.jpg", public_url="https://cdn/a.jpg")
    with pytest.raises(b.ContentRejected):
        ig(handler).publish(ACCOUNT, b.PublishRequest(format="post", text="x", media=(media,)))


def test_tiktok_uses_pkce_and_private_visibility_when_unaudited():
    adapter = TikTokAdapter(
        client_key="k",
        client_secret="s",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    qs = parse_qs(
        urlparse(
            adapter.authorization_url(
                state="s", redirect_uri="https://app/cb", code_challenge="abc"
            )
        ).query
    )
    assert qs["code_challenge"] == ["abc"] and qs["code_challenge_method"] == ["S256"]

    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("creator_info/query/"):
            return httpx.Response(
                200,
                json={"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}},
            )
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"data": {"publish_id": "p_1"}, "error": {"code": "ok"}})

    adapter = TikTokAdapter(
        client_key="k", client_secret="s", transport=httpx.MockTransport(handler)
    )
    media = b.MediaFile(b"x", "image/jpeg", "a.jpg", public_url="https://cdn.example.com/a.jpg")
    result = adapter.publish(
        ACCOUNT, b.PublishRequest(format="carousel", text="Hi", media=(media,))
    )
    assert result.external_post_id == "p_1"
    assert sent["post_info"]["privacy_level"] == "SELF_ONLY"
    with pytest.raises(b.Unsupported):
        adapter.publish(ACCOUNT, b.PublishRequest(format="short_video", text="x"))


def test_rotate_social_tokens_command(org_client, settings):
    from cryptography.fernet import Fernet
    from django.core.management import call_command

    from apps.social import crypto

    _, org = org_client("owner")
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.SOCIAL_TOKEN_ENCRYPTION_KEYS = [old]
    crypto.reset_cache()
    account = SocialAccount.objects.create(
        organization=org, platform="facebook", external_id="rot", name="Rot", is_mock=True
    )
    account.set_tokens("secret-access", "secret-refresh")
    account.save()

    settings.SOCIAL_TOKEN_ENCRYPTION_KEYS = [new, old]
    crypto.reset_cache()
    call_command("rotate_social_tokens")

    settings.SOCIAL_TOKEN_ENCRYPTION_KEYS = [new]  # old key removed
    crypto.reset_cache()
    account.refresh_from_db()
    assert (account.access_token, account.refresh_token) == ("secret-access", "secret-refresh")
    crypto.reset_cache()


def test_instagram_login_still_works_through_the_shared_meta_client():
    """Regression: Instagram reuses the Facebook adapter's Meta app settings and client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token", "expires_in": 5000})
        assert "appsecret_proof" in request.url.params  # signed like every Meta call
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "p1",
                        "name": "Cafe",
                        "access_token": "page-token",
                        "instagram_business_account": {"id": "ig1", "username": "cafe"},
                    }
                ]
            },
        )

    adapter = ig(handler)
    auth = urlparse(
        adapter.authorization_url(state="s", redirect_uri="https://app/cb", code_challenge="c")
    )
    assert auth.path == "/v26.0/dialog/oauth"
    accounts = adapter.complete_authorization(
        code="c", redirect_uri="https://app/cb", code_verifier="v"
    )
    assert [(a.external_id, a.access_token) for a in accounts] == [("ig1", "page-token")]
