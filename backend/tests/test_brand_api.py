import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.brand.models import BrandAsset

pytestmark = pytest.mark.django_db


def png_bytes(size=(64, 32), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def upload(client, org, data: bytes, name="logo.png", kind="logo", content_type="image/png"):
    return client.post(
        f"/api/v1/orgs/{org.id}/brand/assets/",
        {"file": SimpleUploadedFile(name, data, content_type=content_type), "kind": kind},
        format="multipart",
    )


def test_reference_data_lists_presets(org_client):
    client, _ = org_client("viewer")
    body = client.get("/api/v1/reference-data/").json()
    keys = {i["key"] for i in body["industries"]}
    assert {"restaurant", "real_estate", "fitness", "other"} <= keys
    assert set(body["platforms"]) == {"instagram", "facebook", "tiktok"}


def test_profile_defaults_and_update(org_client):
    client, org = org_client("editor")
    initial = client.get(f"/api/v1/orgs/{org.id}/business-profile/").json()
    assert initial["business_name"] == org.name
    response = client.patch(
        f"/api/v1/orgs/{org.id}/business-profile/",
        {
            "industry": "restaurant",
            "description": "Specialty coffee and pastries.",
            "products_services": [
                {"name": "Espresso"},
                {"name": "Croissant", "description": "Baked daily"},
            ],
            "goals": ["foot_traffic", "Launch our catering service"],
            "preferred_platforms": ["instagram", "tiktok", "instagram"],
            "languages": ["en", "ar"],
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["preferred_platforms"] == ["instagram", "tiktok"]
    assert body["products_services"][0] == {"name": "Espresso", "description": ""}


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"industry": "spaceships"}, "industry"),
        ({"preferred_platforms": ["myspace"]}, "preferred_platforms"),
        ({"languages": ["english!"]}, "languages"),
        ({"website": "not a url"}, "website"),
    ],
)
def test_profile_validation(org_client, payload, field):
    client, org = org_client("editor")
    response = client.patch(f"/api/v1/orgs/{org.id}/business-profile/", payload, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_viewer_cannot_edit_brand(org_client):
    client, org = org_client("viewer")
    assert client.get(f"/api/v1/orgs/{org.id}/business-profile/").status_code == 200
    assert (
        client.patch(
            f"/api/v1/orgs/{org.id}/business-profile/", {"description": "x"}, format="json"
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/orgs/{org.id}/brand/audiences/", {"name": "x"}, format="json"
        ).status_code
        == 403
    )


def test_guideline_colors_validated_and_normalised(org_client):
    client, org = org_client("editor")
    bad = client.patch(
        f"/api/v1/orgs/{org.id}/brand/guidelines/", {"colors": ["red"]}, format="json"
    )
    assert bad.status_code == 400
    ok = client.patch(
        f"/api/v1/orgs/{org.id}/brand/guidelines/",
        {
            "colors": ["#1a2b3c"],
            "tone": ["warm"],
            "restricted_claims": ["Best coffee in the world"],
        },
        format="json",
    )
    assert ok.json()["colors"] == ["#1A2B3C"]


def test_onboarding_progress_and_completion(org_client):
    client, org = org_client("editor")
    url = f"/api/v1/orgs/{org.id}/onboarding/"
    status = client.get(url).json()
    assert status["can_complete"] is False
    assert client.post(url).status_code == 409

    client.patch(
        f"/api/v1/orgs/{org.id}/business-profile/",
        {
            "industry": "fitness",
            "description": "Boutique gym",
            "goals": ["leads"],
            "preferred_platforms": ["instagram"],
        },
        format="json",
    )
    client.post(
        f"/api/v1/orgs/{org.id}/brand/audiences/",
        {"name": "Beginners", "is_primary": True},
        format="json",
    )
    status = client.get(url).json()
    assert status["can_complete"] is True
    assert status["percent"] == 60
    done = client.post(url).json()
    assert done["completed_at"] is not None


def test_upload_valid_png_and_download(org_client):
    client, org = org_client("editor")
    response = upload(client, org, png_bytes())
    assert response.status_code == 201, response.json()
    asset = response.json()
    assert (asset["width"], asset["height"], asset["content_type"]) == (64, 32, "image/png")
    stored = BrandAsset.objects.get(id=asset["id"])
    assert "logo" not in stored.file.name  # client filename never reaches storage paths
    assert stored.file.name.startswith(f"orgs/{org.id}/brand/")

    download = client.get(asset["file_url"])
    assert download.status_code == 200
    assert download["Content-Type"] == "image/png"
    assert download["X-Content-Type-Options"] == "nosniff"
    assert b"".join(download.streaming_content).startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("data", "name", "content_type"),
    [
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "x.svg",
            "image/svg+xml",
        ),
        (b"<html><script>alert(1)</script></html>", "fake.png", "image/png"),
        (b"", "empty.png", "image/png"),
    ],
)
def test_upload_rejects_non_images(org_client, data, name, content_type):
    client, org = org_client("editor")
    response = upload(client, org, data, name=name, content_type=content_type)
    assert response.status_code == 400
    assert BrandAsset.objects.count() == 0


def test_upload_rejects_oversized(org_client, settings):
    settings.MAX_IMAGE_UPLOAD_BYTES = 100
    client, org = org_client("editor")
    assert upload(client, org, png_bytes((200, 200))).status_code == 400


def test_upload_enforces_storage_quota(org_client, settings):
    client, org = org_client("editor")
    data = png_bytes()
    settings.USAGE_DEFAULT_LIMITS = {
        **settings.USAGE_DEFAULT_LIMITS,
        "storage_bytes": len(data) + 10,
    }
    assert upload(client, org, data).status_code == 201
    over = upload(client, org, data)
    assert over.status_code == 429
    assert over.json()["error"]["code"] == "quota_exceeded"


def test_assets_are_tenant_isolated(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    asset = upload(client_b, org_b, png_bytes()).json()
    # Direct file URL of another tenant's asset.
    assert client_a.get(asset["file_url"]).status_code == 404
    # Another tenant's asset ID through one's own org URL.
    assert (
        client_a.get(f"/api/v1/orgs/{org_a.id}/brand/assets/{asset['id']}/file/").status_code == 404
    )
    assert (
        client_a.delete(f"/api/v1/orgs/{org_a.id}/brand/assets/{asset['id']}/").status_code == 404
    )
    assert BrandAsset.objects.filter(id=asset["id"]).exists()


def test_audiences_are_tenant_isolated(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    audience = client_b.post(
        f"/api/v1/orgs/{org_b.id}/brand/audiences/", {"name": "Secret segment"}, format="json"
    ).json()
    assert client_a.get(f"/api/v1/orgs/{org_a.id}/brand/audiences/").json()["count"] == 0
    assert (
        client_a.patch(
            f"/api/v1/orgs/{org_a.id}/brand/audiences/{audience['id']}/",
            {"name": "pwned"},
            format="json",
        ).status_code
        == 404
    )


def test_business_context_contains_only_this_orgs_user_facts(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    client_a.patch(
        f"/api/v1/orgs/{org_a.id}/business-profile/",
        {"industry": "real_estate", "description": "Boutique agency", "goals": ["leads"]},
        format="json",
    )
    client_a.patch(
        f"/api/v1/orgs/{org_a.id}/brand/guidelines/",
        {"restricted_claims": ["Guaranteed sale in 30 days"]},
        format="json",
    )
    client_b.post(
        f"/api/v1/orgs/{org_b.id}/brand/audiences/", {"name": "Org B audience"}, format="json"
    )

    context = client_a.get(f"/api/v1/orgs/{org_a.id}/business-context/").json()
    assert context["business"]["source"] == "user"
    assert context["business"]["description"] == "Boutique agency"
    assert context["goals"]["items"] == ["Generate leads or enquiries"]
    assert context["restrictions"]["claims_to_avoid"] == ["Guaranteed sale in 30 days"]
    assert context["industry_guidance"]["source"] == "industry_preset"
    assert context["audiences"]["items"] == []
    assert "Org B audience" not in str(context)
