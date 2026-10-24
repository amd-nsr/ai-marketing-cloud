"""Meta integration layer: Graph client, connection lifecycle, callbacks. No real calls:
Graph responses come from an httpx.MockTransport or the labelled simulation."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from django.utils import timezone

from apps.ads.models import AdAccount
from apps.meta import graph as graph_module
from apps.meta import services
from apps.meta.graph import GraphClient
from apps.meta.models import MetaConnection, MetaDataDeletionRequest, MetaWebhookEvent
from apps.social.adapters import base as b
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db
SECRET = "test-secret"


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


@pytest.fixture
def meta_app(settings):
    settings.META_APP_ID = "test-app"
    settings.META_APP_SECRET = SECRET
    yield
    graph_module.TRANSPORT = None


def use_graph(handler):
    graph_module.TRANSPORT = httpx.MockTransport(handler)


def client(handler) -> GraphClient:
    return GraphClient(
        app_id="app", app_secret=SECRET, version="v26.0", transport=httpx.MockTransport(handler)
    )


# --- Graph client --------------------------------------------------------------------------


def test_every_token_call_is_signed_with_appsecret_proof():
    seen = {}

    def handler(request):
        seen.update(parse_qs(request.url.query.decode()))
        return httpx.Response(200, json={"id": "1"})

    client(handler).request("GET", "me", token="user-token")
    expected = hmac.new(SECRET.encode(), b"user-token", hashlib.sha256).hexdigest()
    assert seen["appsecret_proof"] == [expected]


def test_pagination_follows_next_without_duplicating_the_token():
    calls = []

    def handler(request):
        q = parse_qs(request.url.query.decode())
        calls.append(q)
        if "after" not in q:
            nxt = "https://graph.facebook.com/v26.0/me/accounts?after=c2&access_token=OLD"
            return httpx.Response(200, json={"data": [{"id": "1"}], "paging": {"next": nxt}})
        return httpx.Response(200, json={"data": [{"id": "2"}], "paging": {}})

    items = list(client(handler).paginate("me/accounts", token="T"))
    assert [i["id"] for i in items] == ["1", "2"]
    assert calls[1]["access_token"] == ["T"]  # the stale token from `next` was replaced


def test_usage_headers_throttle_further_calls():
    calls = []

    def handler(request):
        calls.append(1)
        usage = json.dumps({"call_count": 95, "total_cputime": 10, "total_time": 10})
        return httpx.Response(200, json={"id": "1"}, headers={"x-app-usage": usage})

    graph = client(handler)
    graph.request("GET", "me", token="t")
    with pytest.raises(b.RateLimited):
        graph.request("GET", "me", token="t")
    assert len(calls) == 1  # the second call never left the app


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"code": 190, "error_subcode": 463}, b.ReauthRequired),
        ({"code": 200}, b.PermissionMissing),
        ({"code": 17}, b.RateLimited),
        ({"code": 80004}, b.RateLimited),
        ({"code": 2}, b.TransientError),
        ({"code": 100, "error_user_msg": "Budget too low"}, b.ContentRejected),
    ],
)
def test_error_normalization(error, expected):
    graph = client(lambda r: httpx.Response(400, json={"error": error}))
    with pytest.raises(expected) as exc:
        graph.request("GET", "x", token="t")
    if "error_user_msg" in error:
        assert "Budget too low" in str(exc.value)


def test_write_timeouts_are_uncertain_reads_are_transient():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    graph = client(timeout)
    with pytest.raises(b.UncertainOutcome):
        graph.request("POST", "x", token="t", data={}, write=True)
    with pytest.raises(b.TransientError):
        graph.request("GET", "x", token="t")


# --- Real login flow (Graph stubbed) -----------------------------------------------------------


def graph_handler(*, declined=(), revoke=None):
    def handler(request):
        path = request.url.path
        if path.endswith("oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token", "expires_in": 5184000})
        if path.endswith("/me/permissions"):
            if request.method == "DELETE":
                if revoke is not None:
                    revoke.append(1)
                return httpx.Response(200, json={"success": True})
            perms = [
                "pages_show_list",
                "pages_manage_posts",
                "pages_read_engagement",
                "read_insights",
                "ads_read",
                "ads_management",
            ]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"permission": p, "status": "declined" if p in declined else "granted"}
                        for p in perms
                    ]
                },
            )
        if path.endswith("/me/accounts"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "111",
                            "name": "Cafe Page",
                            "category": "Cafe",
                            "tasks": ["MANAGE", "CREATE_CONTENT"],
                            "access_token": "page-token-111",
                        },
                        {
                            "id": "222",
                            "name": "Read only",
                            "tasks": ["ANALYZE"],
                            "access_token": "p2",
                        },
                    ]
                },
            )
        if path.endswith("/me/adaccounts"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "act_9",
                            "name": "Cafe ads",
                            "currency": "USD",
                            "timezone_name": "UTC",
                            "account_status": 1,
                        }
                    ]
                },
            )
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "fb-user-1", "name": "Dana"})
        return httpx.Response(200, json={"data": []})

    return handler


def start_and_callback(client_, org, *, simulation=False):
    start = client_.post(
        url(org, "social/accounts/connect/"),
        {"platform": "facebook", "simulation": simulation},
        format="json",
    )
    assert start.status_code == 200, start.json()
    auth = urlparse(start.json()["authorization_url"])
    qs = parse_qs(auth.query)
    code = qs.get("code", ["real-code"])[0]
    return auth, client_.post(
        "/api/v1/social/oauth/callback/", {"state": qs["state"][0], "code": code}, format="json"
    )


def test_real_login_records_grants_and_discovers_assets_without_connecting(org_client, meta_app):
    use_graph(graph_handler(declined=("read_insights",)))
    client_, org = org_client("owner")
    auth, response = start_and_callback(client_, org)
    scopes = parse_qs(auth.query)["scope"][0].split(",")
    assert {"pages_manage_posts", "ads_read", "ads_management"} <= set(scopes)
    assert parse_qs(auth.query)["auth_type"] == ["rerequest"]
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["accounts"] == [] and body["meta_connection_id"]

    detail = client_.get(url(org, f"meta/connections/{body['meta_connection_id']}/")).json()
    assert detail["declined_permissions"] == ["read_insights"]
    assert not any(k for k in detail if "token" in k and "expires" not in k)
    pages = {p["id"]: p for p in detail["pages"]}
    assert pages["111"]["can_publish"] and not pages["222"]["can_publish"]
    # read_insights was declined, so publishing Pages isn't available until reconnecting
    assert {f["feature"]: f["available"] for f in detail["features"]}["pages"] is False
    assert SocialAccount.objects.filter(organization=org).count() == 0

    conn = MetaConnection.objects.get(pk=body["meta_connection_id"])
    assert conn.user_token == "user-token" and "user-token" not in conn.user_token_enc


def test_selecting_pages_stores_page_tokens_and_rejects_read_only(org_client, meta_app):
    use_graph(graph_handler())
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org)
    cid = response.json()["meta_connection_id"]

    bad = client_.post(
        url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["222"]}, format="json"
    )
    assert bad.status_code == 400
    ok = client_.post(
        url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["111"]}, format="json"
    )
    assert ok.status_code == 200, ok.json()
    page = SocialAccount.objects.get(organization=org, external_id="111")
    assert page.access_token == "page-token-111" and page.meta_connection_id is not None
    assert not page.is_mock


def test_connection_endpoints_are_tenant_scoped_and_role_checked(org_client, add_member, make_user):
    client_a, org_a = org_client("owner")
    _, response = start_and_callback(client_a, org_a, simulation=True)
    cid = response.json()["meta_connection_id"]
    client_b, org_b = org_client("owner")
    assert client_b.get(url(org_a, f"meta/connections/{cid}/")).status_code == 404
    assert client_b.get(url(org_b, f"meta/connections/{cid}/")).status_code == 404

    from rest_framework.test import APIClient

    editor = make_user("editor@example.com")
    add_member(org_a, editor, "editor")
    c = APIClient()
    c.force_authenticate(editor)
    assert c.get(url(org_a, f"meta/connections/{cid}/")).status_code == 200
    denied = c.post(url(org_a, f"meta/connections/{cid}/pages/"), {"page_ids": []}, format="json")
    assert denied.status_code == 403


def test_simulation_flow_selects_page_and_ad_account(
    org_client, django_capture_on_commit_callbacks
):
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org, simulation=True)
    cid = response.json()["meta_connection_id"]
    client_.post(
        url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["sim-page-1"]}, format="json"
    )
    with django_capture_on_commit_callbacks(execute=True):
        r = client_.post(
            url(org, f"meta/connections/{cid}/ad-accounts/"),
            {"account_ids": ["act_sim_1"]},
            format="json",
        )
    assert r.status_code == 200, r.json()
    account = AdAccount.objects.get(organization=org)
    assert account.is_mock and account.last_sync_status == "succeeded"
    detail = client_.get(url(org, f"meta/connections/{cid}/")).json()
    assert [p["connected"] for p in detail["pages"]] == [True, False]
    assert detail["ad_accounts"][0]["connected"] is True


def test_disconnect_revokes_on_meta_and_detaches_everything(org_client, meta_app):
    revoked: list[int] = []
    use_graph(graph_handler(revoke=revoked))
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org)
    cid = response.json()["meta_connection_id"]
    client_.post(url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["111"]}, format="json")
    assert client_.delete(url(org, f"meta/connections/{cid}/")).status_code == 204
    assert revoked == [1]
    conn = MetaConnection.objects.get(pk=cid)
    assert conn.status == "disconnected" and not conn.user_token_enc
    page = SocialAccount.objects.get(external_id="111")
    assert page.status == "disconnected" and page.access_token is None


def test_failed_revoke_still_disconnects_locally(org_client, meta_app):
    client_, org = org_client("owner")
    use_graph(graph_handler())
    _, response = start_and_callback(client_, org)
    cid = response.json()["meta_connection_id"]
    use_graph(lambda r: httpx.Response(500, json={}))
    conn = MetaConnection.objects.get(pk=cid)
    result = services.disconnect(conn, actor=None)
    assert result["revoked_on_meta"] is False and result["revoke_error"]
    conn.refresh_from_db()
    assert conn.status == "disconnected"


def test_token_expiry_is_warned_then_requires_reconnect(org_client):
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org, simulation=True)
    conn = MetaConnection.objects.get(pk=response.json()["meta_connection_id"])
    conn.token_expires_at = timezone.now() + timedelta(days=2)
    conn.save()
    assert services.check_connections()["expiring"] == 1
    conn.token_expires_at = timezone.now() - timedelta(minutes=1)
    conn.save()
    assert services.check_connections()["expired"] == 1
    conn.refresh_from_db()
    assert conn.status == "needs_reauth"


def test_removed_publishing_permission_pauses_pages(org_client, meta_app):
    use_graph(graph_handler())
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org)
    cid = response.json()["meta_connection_id"]
    client_.post(url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["111"]}, format="json")
    use_graph(graph_handler(declined=("pages_manage_posts",)))
    client_.post(url(org, f"meta/connections/{cid}/refresh/"))
    assert SocialAccount.objects.get(external_id="111").status == "needs_reauth"


# --- Callbacks from Meta ---------------------------------------------------------------------


def signed_request(payload, secret=SECRET):
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode() + "." + raw


def test_webhook_subscription_check(api_client):
    ok = api_client.get(
        "/api/v1/meta/webhooks/",
        {"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"},
    )
    assert ok.status_code == 200 and ok.content == b"42"
    bad = api_client.get(
        "/api/v1/meta/webhooks/",
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
    )
    assert bad.status_code == 403


def test_webhook_requires_valid_signature_and_queues_ad_sync(
    api_client, org_client, meta_app, django_capture_on_commit_callbacks
):
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org, simulation=True)
    cid = response.json()["meta_connection_id"]
    with django_capture_on_commit_callbacks(execute=True):
        client_.post(
            url(org, f"meta/connections/{cid}/ad-accounts/"),
            {"account_ids": ["act_sim_1"]},
            format="json",
        )
    body = json.dumps(
        {
            "object": "ad_account",
            "entry": [{"id": "sim_1", "changes": [{"field": "with_issues_ad_objects"}]}],
        }
    ).encode()
    bad = api_client.post(
        "/api/v1/meta/webhooks/",
        body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert bad.status_code == 403 and MetaWebhookEvent.objects.count() == 0
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    ok = api_client.post(
        "/api/v1/meta/webhooks/",
        body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": sig},
    )
    assert ok.status_code == 200
    event = MetaWebhookEvent.objects.get()
    assert event.object == "ad_account" and event.processed_at is not None


def test_deauthorize_callback_revokes_everywhere(api_client, org_client, meta_app):
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org, simulation=True)
    cid = response.json()["meta_connection_id"]
    client_.post(
        url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["sim-page-1"]}, format="json"
    )
    assert (
        api_client.post(
            "/api/v1/meta/deauthorize/", {"signed_request": "forged.payload"}
        ).status_code
        == 403
    )
    sr = signed_request({"algorithm": "HMAC-SHA256", "user_id": "sim-meta-user"})
    assert api_client.post("/api/v1/meta/deauthorize/", {"signed_request": sr}).status_code == 200
    assert MetaConnection.objects.get(pk=cid).status == "revoked"
    assert SocialAccount.objects.get(external_id="sim-page-1").status == "disconnected"


def test_data_deletion_callback_deletes_and_reports_status(
    api_client, org_client, meta_app, django_capture_on_commit_callbacks
):
    client_, org = org_client("owner")
    _, response = start_and_callback(client_, org, simulation=True)
    cid = response.json()["meta_connection_id"]
    with django_capture_on_commit_callbacks(execute=True):
        client_.post(
            url(org, f"meta/connections/{cid}/ad-accounts/"),
            {"account_ids": ["act_sim_1"]},
            format="json",
        )
    sr = signed_request({"algorithm": "HMAC-SHA256", "user_id": "sim-meta-user"})
    r = api_client.post("/api/v1/meta/data-deletion/", {"signed_request": sr})
    assert r.status_code == 200
    code = r.json()["confirmation_code"]
    assert r.json()["url"].endswith(f"/meta/data-deletion/{code}")
    status = api_client.get(f"/api/v1/meta/data-deletion/{code}/").json()
    assert status["status"] == "completed"
    conn = MetaConnection.objects.get(pk=cid)
    assert conn.status == "deleted" and conn.name == "" and conn.available_pages == []
    assert MetaDataDeletionRequest.objects.get().summary["connections"] == 1
    assert api_client.get("/api/v1/meta/data-deletion/nope/").status_code == 404
