"""Advertising: drafts, validation, policy-enforced writes, sync. Simulation ad accounts and
stubbed Marketing API responses only — nothing is created on Meta, no money is spent."""

import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ads import simulation
from apps.ads.meta_platform import MetaAdsPlatform
from apps.ads.models import AdAccount, AdCampaign, AdInsight
from apps.ads.platform import AccountContext, CampaignSpec
from apps.automation.models import AutomationAction
from apps.automation.policy import get_policy
from apps.automation.services import approve_action, propose_ad_action
from apps.meta.graph import GraphClient
from apps.organizations.models import Membership
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


@pytest.fixture
def ads_org(org_client, django_capture_on_commit_callbacks):
    """An org with a simulated Meta connection, one Page and one synced ad account."""
    client, org = org_client("owner")
    start = client.post(
        url(org, "social/accounts/connect/"),
        {"platform": "facebook", "simulation": True},
        format="json",
    )
    qs = parse_qs(urlparse(start.json()["authorization_url"]).query)
    cb = client.post(
        "/api/v1/social/oauth/callback/",
        {"state": qs["state"][0], "code": "mock-code"},
        format="json",
    )
    cid = cb.json()["meta_connection_id"]
    client.post(
        url(org, f"meta/connections/{cid}/pages/"), {"page_ids": ["sim-page-1"]}, format="json"
    )
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            url(org, f"meta/connections/{cid}/ad-accounts/"),
            {"account_ids": ["act_sim_1"]},
            format="json",
        )
    account = AdAccount.objects.get(organization=org)
    page = SocialAccount.objects.get(organization=org, platform="facebook")
    return client, org, account, page


def set_limits(client, org, **extra):
    body = {
        "ads_limit_currency": "USD",
        "ads_max_daily_budget_per_campaign": "50.00",
        "ads_max_total_daily_budget": "80.00",
        "ads_monthly_spend_limit": "1000.00",
        **extra,
    }
    r = client.patch(url(org, "automation/policy/"), body, format="json")
    assert r.status_code == 200, r.json()


def draft_body(account, page, **overrides):
    body = {
        "ad_account": str(account.id),
        "name": "Rye launch",
        "objective": "OUTCOME_TRAFFIC",
        "daily_budget": "20.00",
        "special_ad_categories": [],
        "spec": {
            "targeting": {"countries": ["US"], "age_min": 21, "age_max": 55, "genders": []},
            "creative": {
                "page_account_id": str(page.id),
                "primary_text": "Fresh rye sourdough every Saturday.",
                "headline": "New rye loaf",
                "link": "https://example.com/rye",
                "call_to_action": "LEARN_MORE",
            },
            "schedule": {},
        },
    }
    body.update(overrides)
    return body


def approved_campaign(client, org, account, page, **overrides):
    r = client.post(
        url(org, "ads/campaigns/"), draft_body(account, page, **overrides), format="json"
    )
    assert r.status_code == 201, r.json()
    cid = r.json()["id"]
    a = client.post(url(org, f"ads/campaigns/{cid}/approve/"))
    assert a.status_code == 200, a.json()
    return cid


def created_campaign(client, org, account, page, django_capture_on_commit_callbacks, **overrides):
    cid = approved_campaign(client, org, account, page, **overrides)
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(url(org, f"ads/campaigns/{cid}/create-on-platform/"))
    assert r.json()["action"]["status"] == "succeeded", r.json()["action"]
    return cid


# --- Drafts --------------------------------------------------------------------------------


def test_draft_validation_and_approval_roles(ads_org, add_member, make_user):
    client, org, account, page = ads_org
    bad = client.post(
        url(org, "ads/campaigns/"),
        draft_body(
            account,
            page,
            daily_budget="0.50",
            spec={"targeting": {}, "creative": {}, "schedule": {}},
        ),
        format="json",
    )
    assert bad.status_code == 201
    fields = {i["field"] for i in bad.json()["issues"]}
    assert {"daily_budget", "targeting.countries", "creative.link", "creative.page"} <= fields
    assert client.post(url(org, f"ads/campaigns/{bad.json()['id']}/approve/")).status_code == 400

    editor = make_user("ed@example.com")
    add_member(org, editor, "editor")
    ed = APIClient()
    ed.force_authenticate(editor)
    r = ed.post(url(org, "ads/campaigns/"), draft_body(account, page), format="json")
    assert r.status_code == 201  # editors draft...
    assert (
        ed.post(url(org, f"ads/campaigns/{r.json()['id']}/approve/")).status_code == 403
    )  # ...not approve


def test_editing_an_approved_draft_needs_reapproval(ads_org):
    client, org, account, page = ads_org
    cid = approved_campaign(client, org, account, page)
    client.patch(url(org, f"ads/campaigns/{cid}/"), {"daily_budget": "25.00"}, format="json")
    c = AdCampaign.objects.get(pk=cid)
    assert c.state == "draft" and not c.is_approved


def test_restricted_categories_cannot_narrow_targeting(ads_org):
    client, org, account, page = ads_org
    r = client.post(
        url(org, "ads/campaigns/"),
        draft_body(account, page, special_ad_categories=["HOUSING"]),
        format="json",
    )
    assert any(i["field"] == "targeting" for i in r.json()["issues"])


def test_ai_generates_a_labelled_draft_only(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(
            url(org, "ads/campaigns/generate/"),
            {
                "ad_account": str(account.id),
                "brief": "Promote rye bread",
                "page_account": str(page.id),
                "link": "https://example.com/rye",
            },
            format="json",
        )
    assert r.status_code == 202, r.json()
    campaign = AdCampaign.objects.get(organization=org, source="ai")
    assert campaign.state == "draft" and campaign.is_mock_ai and campaign.external_id is None
    issues = client.get(url(org, f"ads/campaigns/{campaign.id}/")).json()["issues"]
    assert issues == []  # the mock draft plus the Page and link given is complete


# --- Create on Meta ---------------------------------------------------------------------


def test_creation_is_refused_until_limits_are_set(ads_org):
    client, org, account, page = ads_org
    cid = approved_campaign(client, org, account, page)
    r = client.post(url(org, f"ads/campaigns/{cid}/create-on-platform/"))
    action = r.json()["action"]
    assert action["status"] == "rejected"
    assert "Set the advertising limits first" in action["decision_reasons"][0]


def test_create_builds_everything_paused(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    c = AdCampaign.objects.get(pk=cid)
    assert c.state == "created" and c.configured_status == "PAUSED"
    assert set(c.progress) >= {"campaign_id", "adset_id", "creative_id", "ad_id"}
    assert c.external_id == c.progress["campaign_id"]
    assert c.ad_sets.count() == 1 and c.ad_sets.get().ads.count() == 1  # mirrored by sync


def test_budget_above_per_campaign_limit_is_refused_at_creation(ads_org):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = approved_campaign(client, org, account, page, daily_budget="60.00")
    action = client.post(url(org, f"ads/campaigns/{cid}/create-on-platform/")).json()["action"]
    assert action["status"] == "rejected" and "above the limit" in action["decision_reasons"][0]


def test_partial_failure_resumes_without_duplicates(
    ads_org, monkeypatch, django_capture_on_commit_callbacks
):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = approved_campaign(client, org, account, page, name="Rye [sim:fail-adset]")
    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(url(org, f"ads/campaigns/{cid}/create-on-platform/")).json()["action"]
    c = AdCampaign.objects.get(pk=cid)
    assert first["status"] == "failed" and c.state == "failed"
    assert list(c.progress) == ["campaign_id"] and "ad set" in c.last_error
    campaign_id = c.progress["campaign_id"]
    # Editing is blocked while part of it exists on Meta.
    assert (
        client.patch(url(org, f"ads/campaigns/{cid}/"), {"name": "x"}, format="json").status_code
        == 409
    )

    monkeypatch.setattr(
        simulation.SimulatedAdsPlatform, "create_ad_set", lambda self, *a, **k: "sim_adset_retry"
    )
    with django_capture_on_commit_callbacks(execute=True):
        retry = client.post(url(org, f"ads/campaigns/{cid}/create-on-platform/")).json()["action"]
    c.refresh_from_db()
    assert retry["status"] == "succeeded"
    assert c.progress["campaign_id"] == campaign_id  # not created twice
    assert c.progress["adset_id"] == "sim_adset_retry"


def test_lost_response_is_recovered_by_name_tag(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(
        client,
        org,
        account,
        page,
        django_capture_on_commit_callbacks,
        name="Rye [sim:lost-campaign]",
    )
    c = AdCampaign.objects.get(pk=cid)
    assert c.external_id and c.external_id.startswith("sim_campaign_")


# --- Activation, budgets, kill switch -------------------------------------------------------


def test_activation_respects_total_and_monthly_limits(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    a = created_campaign(
        client, org, account, page, django_capture_on_commit_callbacks, daily_budget="50.00"
    )
    b = created_campaign(
        client, org, account, page, django_capture_on_commit_callbacks, daily_budget="40.00"
    )
    with django_capture_on_commit_callbacks(execute=True):
        ok = client.post(url(org, f"ads/campaigns/{a}/activate/")).json()["action"]
    assert ok["status"] == "succeeded"
    over = client.post(url(org, f"ads/campaigns/{b}/activate/")).json()["action"]
    assert over["status"] == "rejected" and "above the limit of 80" in over["decision_reasons"][0]

    # Monthly limit reached (recorded spend) blocks further activation.
    client.post(url(org, f"ads/campaigns/{a}/pause/"))
    AdInsight.objects.create(
        organization=org,
        ad_account=account,
        campaign_external_id="x",
        date=timezone.now().date(),
        currency="USD",
        spend=Decimal("1000"),
        retrieved_at=timezone.now(),
    )
    blocked = client.post(url(org, f"ads/campaigns/{b}/activate/")).json()["action"]
    assert "reached the limit" in blocked["decision_reasons"][0]


def test_stale_spend_data_blocks_spend_increases(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    AdAccount.objects.filter(pk=account.pk).update(
        last_synced_at=timezone.now() - timedelta(days=2)
    )
    action = client.post(url(org, f"ads/campaigns/{cid}/activate/")).json()["action"]
    assert action["status"] == "rejected" and "out of date" in action["decision_reasons"][0]


def test_budget_change_cap_and_currency_mismatch(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    too_much = client.post(
        url(org, f"ads/campaigns/{cid}/budget/"), {"daily_budget": "30.00"}, format="json"
    )
    assert "above the 20% allowed" in too_much.json()["action"]["decision_reasons"][0]
    with django_capture_on_commit_callbacks(execute=True):
        ok = client.post(
            url(org, f"ads/campaigns/{cid}/budget/"), {"daily_budget": "24.00"}, format="json"
        )
    assert ok.json()["action"]["status"] == "succeeded"
    assert AdCampaign.objects.get(pk=cid).daily_budget == Decimal("24.00")
    down = client.post(
        url(org, f"ads/campaigns/{cid}/budget/"), {"daily_budget": "5.00"}, format="json"
    )
    assert down.json()["action"]["status"] == "succeeded"  # decreases aren't capped

    set_limits(client, org, ads_limit_currency="EUR")
    eur = client.post(url(org, f"ads/campaigns/{cid}/activate/")).json()["action"]
    assert "set in EUR" in eur["decision_reasons"][0]


def test_kill_switch_blocks_spend_but_allows_pausing(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url(org, f"ads/campaigns/{cid}/activate/"))
    set_limits(client, org, ads_writes_paused=True)
    blocked = client.post(
        url(org, f"ads/campaigns/{cid}/budget/"), {"daily_budget": "22"}, format="json"
    )
    assert "kill switch" in blocked.json()["action"]["decision_reasons"][0]
    with django_capture_on_commit_callbacks(execute=True):
        paused = client.post(url(org, f"ads/campaigns/{cid}/pause/")).json()["action"]
    assert paused["status"] == "succeeded"
    assert AdCampaign.objects.get(pk=cid).configured_status == "PAUSED"


def test_only_ads_managers_change_campaigns(
    ads_org, add_member, make_user, django_capture_on_commit_callbacks
):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    editor = make_user("ed2@example.com")
    add_member(org, editor, "editor")
    ed = APIClient()
    ed.force_authenticate(editor)
    assert ed.post(url(org, f"ads/campaigns/{cid}/activate/")).status_code == 403
    other, other_org = make_user("o@example.com"), None
    assert other_org is None
    stranger = APIClient()
    stranger.force_authenticate(other)
    assert stranger.get(url(org, f"ads/campaigns/{cid}/")).status_code == 404


# --- Automation ------------------------------------------------------------------------------


def test_automation_needs_approval_in_semi_mode_and_never_creates(
    ads_org, django_capture_on_commit_callbacks
):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url(org, f"ads/campaigns/{cid}/activate/"))
    campaign = AdCampaign.objects.get(pk=cid)

    manual = propose_ad_action(
        org, campaign=campaign, action_type="ads_pause", initiated_by="automation", workflow="t"
    )
    assert manual.status == "rejected"  # manual mode

    client.patch(url(org, "automation/policy/"), {"mode": "semi_automatic"}, format="json")
    off = propose_ad_action(
        org, campaign=campaign, action_type="ads_pause", initiated_by="automation", workflow="t"
    )
    assert off.status == "rejected" and "switched off" in off.decision_reasons[0]

    set_limits(client, org, ads_automation_enabled=True)
    action = propose_ad_action(
        org, campaign=campaign, action_type="ads_pause", initiated_by="automation", workflow="t"
    )
    assert action.status == "awaiting_approval"
    again = propose_ad_action(
        org, campaign=campaign, action_type="ads_pause", initiated_by="automation", workflow="t"
    )
    assert again.pk == action.pk  # no duplicate pending actions

    create = propose_ad_action(
        org, campaign=campaign, action_type="ads_create", initiated_by="automation", workflow="t"
    )
    assert create.status == "rejected"

    owner = Membership.objects.get(organization=org, role="owner")
    with django_capture_on_commit_callbacks(execute=True):
        approve_action(action, approver=owner)
    action.refresh_from_db()
    assert action.status == "succeeded"
    assert AdCampaign.objects.get(pk=cid).configured_status == "PAUSED"


def test_automatic_mode_executes_only_allowed_changes(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(
        client, org, mode="automatic", ads_automation_enabled=True, ads_allow_automated_pause=True
    )
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    campaign = AdCampaign.objects.get(pk=cid)
    activation = propose_ad_action(
        org, campaign=campaign, action_type="ads_activate", initiated_by="automation", workflow="t"
    )
    assert activation.status == "awaiting_approval"  # automated activation not allowed
    activation.status = "cancelled"
    activation.save()
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url(org, f"ads/campaigns/{cid}/activate/"))
    pause = propose_ad_action(
        org,
        campaign=AdCampaign.objects.get(pk=cid),
        action_type="ads_pause",
        initiated_by="automation",
        workflow="t",
    )
    assert pause.status == "succeeded"
    assert get_policy(org).ads_allow_automated_pause is True


def test_actions_are_tenant_scoped(ads_org, org_client, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    other_client, other_org = org_client("owner")
    assert other_client.post(url(other_org, f"ads/campaigns/{cid}/activate/")).status_code == 404
    r = other_client.post(
        url(other_org, "ads/campaigns/"), draft_body(account, page), format="json"
    )
    assert r.status_code == 400  # another tenant's ad account can't be referenced
    assert AutomationAction.objects.filter(organization=other_org).count() == 0


def test_insights_summary_reports_simulated_spend(ads_org, django_capture_on_commit_callbacks):
    client, org, account, page = ads_org
    set_limits(client, org)
    cid = created_campaign(client, org, account, page, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url(org, f"ads/campaigns/{cid}/activate/"))
    body = client.get(url(org, "ads/insights/?days=7")).json()
    usd = body["currencies"][0]
    assert usd["currency"] == "USD" and usd["is_mock"] is True
    assert Decimal(usd["totals"]["spend"]) == Decimal("17.00")  # 85% of 20.00, one day
    assert Decimal(usd["active_daily_budget"]) == Decimal("20.00")


# --- Real Marketing API request shapes (stubbed) -----------------------------------------------


def meta_platform(handler) -> MetaAdsPlatform:
    return MetaAdsPlatform(
        GraphClient(
            app_id="a", app_secret="s", version="v26.0", transport=httpx.MockTransport(handler)
        )
    )


CTX = AccountContext(external_id="act_9", token="t", currency="USD")
SPEC = CampaignSpec(
    name="Rye",
    objective="OUTCOME_TRAFFIC",
    daily_budget=Decimal("12.50"),
    special_ad_categories=[],
    countries=["US"],
    age_min=21,
    age_max=55,
    genders=[],
    page_id="111",
    primary_text="Hi",
    headline="Rye",
    description="",
    link="https://example.com",
    call_to_action="LEARN_MORE",
    start_time=None,
    end_time=None,
)


def test_meta_campaign_is_created_paused_in_minor_units():
    seen = {}

    def handler(request):
        seen[request.url.path] = parse_qs(request.content.decode())
        return httpx.Response(200, json={"id": "c1"})

    p = meta_platform(handler)
    assert p.create_campaign(CTX, SPEC, "Rye [amc-1]") == "c1"
    body = seen["/v26.0/act_9/campaigns"]
    assert body["status"] == ["PAUSED"] and body["daily_budget"] == ["1250"]
    p.create_ad_set(CTX, SPEC, "set", "c1")
    adset = seen["/v26.0/act_9/adsets"]
    assert adset["optimization_goal"] == ["LINK_CLICKS"] and adset["status"] == ["PAUSED"]
    assert json.loads(adset["targeting"][0])["geo_locations"] == {"countries": ["US"]}


def test_meta_budget_uses_currency_offsets():
    seen = {}

    def handler(request):
        seen.update(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"success": True})

    meta_platform(handler).set_daily_budget(
        AccountContext("act_9", "t", "JPY"), "c1", Decimal("1500")
    )
    assert seen["daily_budget"] == ["1500"]  # JPY has no minor unit


def test_meta_insights_parse_and_keep_missing_values():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "campaign_id": "c1",
                        "date_start": "2026-10-20",
                        "spend": "4.20",
                        "impressions": "900",
                        "clicks": "12",
                    }
                ]
            },
        )

    rows = meta_platform(handler).insights(
        CTX, since=timezone.now().date(), until=timezone.now().date()
    )
    assert rows[0].spend == Decimal("4.20") and rows[0].clicks == 12
    assert rows[0].reach is None and rows[0].cpc is None  # not reported → missing, not 0
