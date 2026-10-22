import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.brand.models import BrandGuideline
from apps.content.models import Approval, ContentItem
from apps.marketing.models import Campaign

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def create(client, org, **body):
    payload = {
        "title": "Morning special",
        "platform": "instagram",
        "format": "post",
        "caption": "Fresh croissants.",
    }
    payload.update(body)
    return client.post(url(org, "content/"), payload, format="json")


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(buf, "PNG")
    return buf.getvalue()


# --- items and versions -----------------------------------------------------------


def test_create_item_with_first_version_and_checks(ready_org):
    client, org = ready_org("editor")
    response = create(client, org, hashtags=["coffee", "#Coffee", "morning rush"])
    assert response.status_code == 201, response.json()
    item = response.json()
    v = item["current_version"]
    assert v["number"] == 1 and v["source"] == "manual"
    assert v["hashtags"] == ["#coffee", "#morningrush"]  # normalized, de-duplicated
    codes = {c["code"] for c in v["checks"]}
    assert "media_required" in codes  # Instagram post without an image yet


def test_format_must_exist_on_platform(ready_org):
    client, org = ready_org("editor")
    response = create(client, org, platform="tiktok", format="post")
    assert response.status_code == 400
    assert "format" in response.json()["error"]["details"]


def test_versions_are_immutable_history_and_restorable(ready_org):
    client, org = ready_org("editor")
    item = create(client, org).json()
    client.post(
        url(org, f"content/{item['id']}/versions/"), {"caption": "Second take"}, format="json"
    )
    versions = client.get(url(org, f"content/{item['id']}/versions/")).json()
    assert [v["number"] for v in versions] == [2, 1]
    assert versions[0]["caption"] == "Second take" and versions[1]["caption"] == "Fresh croissants."
    restored = client.post(url(org, f"content/{item['id']}/versions/1/restore/")).json()
    assert restored["number"] == 3 and restored["caption"] == "Fresh croissants."


def test_restricted_claims_block_submission(ready_org):
    client, org = ready_org("editor")
    BrandGuideline.objects.update_or_create(
        organization=org, defaults={"restricted_claims": ["best coffee"]}
    )
    item = create(client, org, caption="The BEST coffee in town!").json()
    assert any(c["code"] == "restricted_claim" for c in item["current_version"]["checks"])
    response = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json")
    assert response.status_code == 409
    assert "claim you must not make" in response.json()["error"]["message"]


def test_viewer_and_analyst_cannot_edit(ready_org, org_client):
    owner, org = ready_org()
    item = create(owner, org).json()
    for role in ("viewer", "analyst"):
        client, _ = org_client(role, org=org)
        assert client.get(url(org, f"content/{item['id']}/")).status_code == 200
        assert (
            client.post(
                url(org, f"content/{item['id']}/versions/"), {"caption": "x"}, format="json"
            ).status_code
            == 403
        )
        assert create(client, org).status_code == 403


def test_delete_only_drafts(ready_org):
    client, org = ready_org("owner")
    item = create(client, org).json()
    ContentItem.objects.filter(pk=item["id"]).update(status="approved")
    assert client.delete(url(org, f"content/{item['id']}/")).status_code == 409
    ContentItem.objects.filter(pk=item["id"]).update(status="draft")
    assert client.delete(url(org, f"content/{item['id']}/")).status_code == 204


# --- AI generation ------------------------------------------------------------------


def test_generate_creates_one_item_per_target(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    targets = [
        {"platform": "instagram", "format": "carousel"},
        {"platform": "tiktok", "format": "short_video"},
    ]
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, "content/generate/"),
            {"brief": "Launch weekend brunch", "targets": targets},
            format="json",
        )
    assert response.status_code == 202
    run = client.get(url(org, f"ai/runs/{response.json()['id']}/")).json()
    assert run["status"] == "succeeded", run
    items = ContentItem.objects.filter(organization=org).order_by("platform")
    assert [(i.platform, i.format) for i in items] == [
        ("instagram", "carousel"),
        ("tiktok", "short_video"),
    ]
    for item in items:
        v = item.current_version
        assert v.source == "ai" and v.is_mock and v.ai_run_id is not None
    assert len(items[0].current_version.slides) == 2


def test_generate_validates_targets(ready_org):
    client, org = ready_org("editor")
    bad = client.post(
        url(org, "content/generate/"),
        {"brief": "x", "targets": [{"platform": "tiktok", "format": "story"}]},
        format="json",
    )
    assert bad.status_code == 400


def test_regenerate_adds_ai_version_and_keeps_history(
    ready_org, django_capture_on_commit_callbacks
):
    client, org = ready_org("editor")
    item = create(client, org).json()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, f"content/{item['id']}/regenerate/"),
            {"instructions": "Shorter"},
            format="json",
        )
    assert response.status_code == 202
    versions = client.get(url(org, f"content/{item['id']}/versions/")).json()
    assert [v["source"] for v in versions] == ["ai", "manual"]
    assert versions[1]["caption"] == "Fresh croissants."


# --- approvals ----------------------------------------------------------------------


def test_approval_flow(ready_org, org_client):
    editor, org = ready_org("editor")
    owner, _ = org_client("owner", org=org)
    item = create(editor, org).json()

    submitted = editor.post(
        url(org, f"content/{item['id']}/submit/"), {"note": "Please check"}, format="json"
    )
    assert submitted.status_code == 201
    approval_id = submitted.json()["id"]
    assert (
        editor.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").status_code == 409
    )

    # Editors cannot approve; owners can.
    assert (
        editor.post(url(org, f"approvals/{approval_id}/approve/"), {}, format="json").status_code
        == 403
    )
    queue = owner.get(url(org, "approvals/?status=pending")).json()["results"]
    assert [a["id"] for a in queue] == [approval_id]
    assert (
        owner.post(
            url(org, f"approvals/{approval_id}/approve/"), {"comment": "Nice"}, format="json"
        ).status_code
        == 200
    )
    assert ContentItem.objects.get(pk=item["id"]).status == "approved"


def test_reject_requires_comment_and_returns_to_author(ready_org, org_client):
    editor, org = ready_org("editor")
    owner, _ = org_client("owner", org=org)
    item = create(editor, org).json()
    approval_id = editor.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()[
        "id"
    ]
    assert (
        owner.post(url(org, f"approvals/{approval_id}/reject/"), {}, format="json").status_code
        == 409
    )
    response = owner.post(
        url(org, f"approvals/{approval_id}/reject/"), {"comment": "Mention the date"}, format="json"
    )
    assert response.status_code == 200
    assert ContentItem.objects.get(pk=item["id"]).status == "changes_requested"
    # Author edits and resubmits.
    editor.post(
        url(org, f"content/{item['id']}/versions/"), {"caption": "Saturday 9am!"}, format="json"
    )
    assert ContentItem.objects.get(pk=item["id"]).status == "draft"
    assert (
        editor.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").status_code == 201
    )


def test_editing_during_review_cancels_pending_approval(ready_org, org_client):
    editor, org = ready_org("editor")
    owner, _ = org_client("owner", org=org)
    item = create(editor, org).json()
    approval_id = editor.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()[
        "id"
    ]
    editor.post(
        url(org, f"content/{item['id']}/versions/"),
        {"caption": "Changed after submit"},
        format="json",
    )
    assert Approval.objects.get(pk=approval_id).status == "cancelled"
    assert ContentItem.objects.get(pk=item["id"]).status == "draft"
    # The stale request can no longer be approved.
    assert (
        owner.post(url(org, f"approvals/{approval_id}/approve/"), {}, format="json").status_code
        == 409
    )


def test_editing_approved_content_requires_new_approval(ready_org):
    owner, org = ready_org("owner")
    item = create(owner, org).json()
    approval_id = owner.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()[
        "id"
    ]
    owner.post(url(org, f"approvals/{approval_id}/approve/"), {}, format="json")
    owner.post(
        url(org, f"content/{item['id']}/versions/"),
        {"caption": "Post-approval edit"},
        format="json",
    )
    assert ContentItem.objects.get(pk=item["id"]).status == "draft"


def test_scheduled_and_published_content_is_locked(ready_org):
    client, org = ready_org("owner")
    item = create(client, org).json()
    for locked in ("scheduled", "published"):
        ContentItem.objects.filter(pk=item["id"]).update(status=locked)
        response = client.post(
            url(org, f"content/{item['id']}/versions/"), {"caption": "x"}, format="json"
        )
        assert response.status_code == 409


def test_archive_cancels_pending_approval(ready_org):
    client, org = ready_org("owner")
    item = create(client, org).json()
    approval_id = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()[
        "id"
    ]
    assert client.post(url(org, f"content/{item['id']}/archive/")).status_code == 200
    assert Approval.objects.get(pk=approval_id).status == "cancelled"
    assert client.get(url(org, "content/")).json()["count"] == 0  # archived hidden by default
    assert client.get(url(org, "content/?status=archived")).json()["count"] == 1


# --- media --------------------------------------------------------------------------


def test_media_upload_updates_checks_and_is_downloadable(ready_org):
    client, org = ready_org("editor")
    item = create(client, org).json()
    upload = client.post(
        url(org, f"content/{item['id']}/assets/"),
        {"file": SimpleUploadedFile("p.png", png(), content_type="image/png")},
        format="multipart",
    )
    assert upload.status_code == 201, upload.json()
    refreshed = client.get(url(org, f"content/{item['id']}/")).json()
    codes = {c["code"] for c in refreshed["current_version"]["checks"]}
    assert "media_required" not in codes and "alt_text_missing" in codes
    download = client.get(upload.json()["file_url"])
    assert download.status_code == 200 and download["Content-Type"] == "image/png"


# --- campaigns ------------------------------------------------------------------------


def test_campaign_crud_and_validation(ready_org):
    client, org = ready_org("editor")
    bad = client.post(
        url(org, "campaigns/"),
        {"name": "Spring", "start_date": "2026-05-10", "end_date": "2026-05-01"},
        format="json",
    )
    assert bad.status_code == 400
    campaign = client.post(
        url(org, "campaigns/"),
        {
            "name": "Spring",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "platforms": ["instagram"],
        },
        format="json",
    ).json()
    item = create(client, org, campaign=campaign["id"]).json()
    assert item["campaign_name"] == "Spring"
    listed = client.get(url(org, f"content/?campaign={campaign['id']}")).json()
    assert listed["count"] == 1
    assert client.get(url(org, f"campaigns/{campaign['id']}/")).json()["content_count"] == 1
    assert client.delete(url(org, f"campaigns/{campaign['id']}/")).status_code == 409


# --- tenant isolation -------------------------------------------------------------------


def test_content_and_approvals_are_tenant_isolated(ready_org):
    client_a, org_a = ready_org("owner")
    client_b, org_b = ready_org("owner")
    item_b = create(client_b, org_b).json()
    approval_b = client_b.post(
        url(org_b, f"content/{item_b['id']}/submit/"), {}, format="json"
    ).json()["id"]
    campaign_b = Campaign.objects.create(organization=org_b, name="B only")

    assert client_a.get(url(org_a, f"content/{item_b['id']}/")).status_code == 404
    assert (
        client_a.post(
            url(org_a, f"content/{item_b['id']}/versions/"), {"caption": "x"}, format="json"
        ).status_code
        == 404
    )
    assert (
        client_a.post(url(org_a, f"approvals/{approval_b}/approve/"), {}, format="json").status_code
        == 404
    )
    assert client_a.get(url(org_a, "approvals/")).json()["count"] == 0
    # Cannot reference another tenant's campaign.
    response = create(client_a, org_a, campaign=str(campaign_b.pk))
    assert response.status_code == 400
    assert "campaign" in response.json()["error"]["details"]
