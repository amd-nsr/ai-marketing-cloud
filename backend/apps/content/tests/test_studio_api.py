"""Content studio: editable documents, renders, media library, templates, AI assist."""

import io
import shutil
import subprocess

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.ai.images import reset_image_provider_cache
from apps.brand.models import BrandGuideline, TargetAudience
from apps.content import documents
from apps.content.models import ContentAsset, ContentItem, LibraryAsset, RenderJob

pytestmark = pytest.mark.django_db

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def png(w=40, h=40, color="blue") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def upload_library(client, org, data=None, name="photo.png", content_type="image/png", **extra):
    return client.post(
        url(org, "library/"),
        {"file": SimpleUploadedFile(name, data or png(), content_type=content_type), **extra},
        format="multipart",
    )


def design(image_id=None, text="Hello", kind="design", pages=1, w=400, h=400):
    def page(i):
        elements = [
            {
                "id": "t1",
                "type": "text",
                "text": text,
                "x": 10,
                "y": 10,
                "width": 300,
                "height": 80,
                "font_size": 40,
                "fill": "#111111",
            },
            {
                "id": "r1",
                "type": "rect",
                "x": 0,
                "y": 300,
                "width": 400,
                "height": 100,
                "fill": "#ff8800",
            },
        ]
        if image_id:
            elements.append(
                {
                    "id": "i1",
                    "type": "image",
                    "x": 50,
                    "y": 100,
                    "width": 200,
                    "height": 150,
                    "asset": {"source": "library", "id": str(image_id)},
                }
            )
        return {"id": f"p{i}", "background": "#ffffff", "elements": elements}

    return {"kind": kind, "width": w, "height": h, "pages": [page(i) for i in range(1, pages + 1)]}


def create(client, org, **body):
    payload = {
        "title": "Spring promo",
        "platform": "instagram",
        "format": "post",
        "caption": "Fresh.",
    }
    payload.update(body)
    return client.post(url(org, "content/"), payload, format="json")


def export(client, org, item_id, page_id="p1", w=400, h=400):
    return client.post(
        url(org, f"content/{item_id}/renders/"),
        {"page_id": page_id, "file": SimpleUploadedFile("r.png", png(w, h), "image/png")},
        format="multipart",
    )


def codes(client, org, item_id):
    item = client.get(url(org, f"content/{item_id}/")).json()
    return {c["code"] for c in item["current_version"]["checks"]}


# --- Documents ----------------------------------------------------------------------


def test_design_document_is_saved_versioned_and_restorable(ready_org):
    client, org = ready_org("editor")
    image = upload_library(client, org).json()
    item = create(client, org, document=design(image["id"])).json()
    doc = item["current_version"]["document"]
    assert doc["kind"] == "design" and doc["schema_version"] == 1
    assert [e["type"] for e in doc["pages"][0]["elements"]] == ["text", "rect", "image"]
    assert item["document_kind"] == "design"

    v2 = client.post(
        url(org, f"content/{item['id']}/versions/"),
        {"document": design(image["id"], text="Changed")},
        format="json",
    )
    assert v2.status_code == 201
    restored = client.post(url(org, f"content/{item['id']}/versions/1/restore/")).json()
    assert restored["document"]["pages"][0]["elements"][0]["text"] == "Hello"
    # Reopening the item returns the editable source exactly as saved.
    reopened = client.get(url(org, f"content/{item['id']}/")).json()
    assert reopened["current_version"]["document"] == restored["document"]


def test_invalid_documents_are_rejected(ready_org):
    client, org = ready_org("editor")
    bad_color = design()
    bad_color["pages"][0]["background"] = "red; drop"
    response = create(client, org, document=bad_color)
    assert response.status_code == 400
    # A design can't have two pages; a carousel item needs a carousel document.
    assert create(client, org, document=design(pages=2)).status_code == 400
    wrong_kind = create(client, org, format="carousel", document=design())
    assert wrong_kind.status_code == 409
    assert "carousel document" in wrong_kind.json()["error"]["message"]


def test_documents_cannot_reference_another_organizations_assets(ready_org):
    client, org = ready_org("editor")
    other_client, other_org = ready_org("editor")
    foreign = upload_library(other_client, other_org).json()
    response = create(client, org, document=design(foreign["id"]))
    assert response.status_code == 409
    assert "no longer exists" in response.json()["error"]["message"]


def test_render_hash_ignores_caption_but_tracks_design():
    doc = documents.parse_document(design())
    same = documents.parse_document(design())
    changed = documents.parse_document(design(text="Other"))
    assert documents.render_hashes(doc) == documents.render_hashes(same)
    assert documents.render_hashes(doc) != documents.render_hashes(changed)


# --- Renders ------------------------------------------------------------------------


def test_export_flow_missing_then_current_then_stale(ready_org):
    client, org = ready_org("editor")
    item = create(client, org, document=design()).json()
    assert "render_missing" in codes(client, org, item["id"])
    # The export must match the design's output size.
    wrong = export(client, org, item["id"], w=200, h=200)
    assert wrong.status_code == 409 and "400x400" in wrong.json()["error"]["message"]
    ok = export(client, org, item["id"])
    assert ok.status_code == 201, ok.json()
    assert ok.json()["source"] == "render" and ok.json()["page_id"] == "p1"
    current = codes(client, org, item["id"])
    assert not current & {"render_missing", "render_stale", "media_required"}

    # A caption edit keeps the export valid; a design edit makes it stale.
    client.post(url(org, f"content/{item['id']}/versions/"), {"caption": "New"}, format="json")
    assert "render_stale" not in codes(client, org, item["id"])
    client.post(
        url(org, f"content/{item['id']}/versions/"),
        {"document": design(text="Moved")},
        format="json",
    )
    assert "render_stale" in codes(client, org, item["id"])
    # Stale exports block submission for approval.
    blocked = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json")
    assert blocked.status_code == 409
    export(client, org, item["id"])
    assert ContentAsset.objects.filter(item_id=item["id"], source="render").count() == 1
    submitted = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json")
    assert submitted.status_code == 201, submitted.json()
    # While in review the export is frozen.
    assert export(client, org, item["id"]).status_code == 409


def test_carousel_pages_are_exported_in_order(ready_org):
    client, org = ready_org("editor")
    # Designed slides count as carousel slides even without slide copy or exports.
    designed = create(client, org, format="carousel", document=design(kind="carousel", pages=3))
    assert "carousel_needs_slides" not in {
        c["code"] for c in designed.json()["current_version"]["checks"]
    }
    item = create(client, org, format="carousel", document=design(kind="carousel", pages=3)).json()
    for page in ["p3", "p1", "p2"]:
        assert export(client, org, item["id"], page_id=page).status_code == 201
    assets = client.get(url(org, f"content/{item['id']}/assets/")).json()
    assert [a["page_id"] for a in assets] == ["p1", "p2", "p3"]
    assert not codes(client, org, item["id"]) & {"render_missing", "carousel_needs_slides"}
    # Removing a page drops its export on the next export.
    client.post(
        url(org, f"content/{item['id']}/versions/"),
        {"document": design(kind="carousel", pages=2)},
        format="json",
    )
    export(client, org, item["id"], page_id="p1")
    assets = client.get(url(org, f"content/{item['id']}/assets/")).json()
    assert [a["page_id"] for a in assets] == ["p1", "p2"]
    assert export(client, org, item["id"], page_id="p9").status_code == 409


# --- Library ------------------------------------------------------------------------


def test_library_upload_search_and_tenant_isolation(ready_org):
    client, org = ready_org("editor")
    other_client, other_org = ready_org("editor")
    created = upload_library(client, org, title="Croissant hero", tags=["Bakery", "hero"])
    assert created.status_code == 201, created.json()
    asset = created.json()
    assert asset["kind"] == "image" and asset["tags"] == ["bakery", "hero"]
    upload_library(client, org, name="other.png")
    assert client.get(url(org, "library/?q=croissant")).json()["count"] == 1
    assert client.get(url(org, "library/?tag=bakery")).json()["count"] == 1
    assert client.get(url(org, "library/?kind=video")).json()["count"] == 0
    file = client.get(url(org, f"library/{asset['id']}/file/"))
    assert file.status_code == 200 and file["Content-Type"] == "image/png"
    # Another organization can't see, download, or delete it.
    assert other_client.get(url(org, f"library/{asset['id']}/")).status_code == 404
    assert other_client.get(url(other_org, f"library/{asset['id']}/")).status_code == 404
    assert other_client.delete(url(other_org, f"library/{asset['id']}/")).status_code == 404


def test_library_rejects_fake_files_and_viewers(ready_org):
    client, org = ready_org("editor")
    fake = upload_library(client, org, data=b"<svg onload=alert(1)>", name="x.png")
    assert fake.status_code == 400
    viewer, viewer_org = ready_org("viewer")
    assert upload_library(viewer, viewer_org).status_code == 403
    assert viewer.get(url(viewer_org, "library/")).status_code == 200


def test_library_asset_in_use_cannot_be_deleted(ready_org):
    client, org = ready_org("editor")
    image = upload_library(client, org).json()
    item = create(client, org, document=design(image["id"])).json()
    blocked = client.delete(url(org, f"library/{image['id']}/"))
    assert blocked.status_code == 409 and "used by 1 design" in blocked.json()["error"]["message"]
    client.post(url(org, f"content/{item['id']}/archive/"))
    assert client.delete(url(org, f"library/{image['id']}/")).status_code == 204


def test_brand_kit_assets_can_be_used_in_designs(ready_org):
    client, org = ready_org("editor")
    logo = client.post(
        url(org, "brand/assets/"),
        {"file": SimpleUploadedFile("logo.png", png(), "image/png"), "kind": "logo"},
        format="multipart",
    ).json()
    doc = design()
    doc["pages"][0]["elements"].append(
        {
            "id": "logo",
            "type": "image",
            "x": 0,
            "y": 0,
            "width": 50,
            "height": 50,
            "asset": {"source": "brand", "id": logo["id"]},
        }
    )
    assert create(client, org, document=doc).status_code == 201


# --- Duplicating, templates ---------------------------------------------------------


def test_duplicate_and_adapt_to_another_platform(ready_org):
    client, org = ready_org("editor")
    item = create(
        client,
        org,
        format="carousel",
        document=design(kind="carousel", pages=2),
        hashtags=["coffee"],
    ).json()
    export(client, org, item["id"], page_id="p1")
    same = client.post(url(org, f"content/{item['id']}/duplicate/"), {}, format="json").json()
    assert same["title"] == "Spring promo (copy)" and same["format"] == "carousel"
    assert same["current_version"]["document"]["kind"] == "carousel"
    assert same["asset_count"] == 0  # exports are never copied
    tiktok = client.post(
        url(org, f"content/{item['id']}/duplicate/"),
        {"platform": "tiktok", "format": "carousel"},
        format="json",
    ).json()
    assert tiktok["platform"] == "tiktok"
    post = client.post(
        url(org, f"content/{item['id']}/duplicate/"), {"format": "post"}, format="json"
    ).json()
    assert post["current_version"]["document"] == {}  # a post edits a design, not a carousel
    blog = client.post(
        url(org, f"content/{item['id']}/duplicate/"),
        {"platform": "blog", "format": "article"},
        format="json",
    ).json()
    assert blog["current_version"]["hashtags"] == []
    bad = client.post(
        url(org, f"content/{item['id']}/duplicate/"),
        {"platform": "tiktok", "format": "post"},
        format="json",
    )
    assert bad.status_code == 400


def test_templates_use_brand_colors_and_can_be_saved(ready_org):
    client, org = ready_org("editor")
    BrandGuideline.objects.update_or_create(
        organization=org, defaults={"colors": ["#123456", "#abcdef"], "fonts": ["Poppins"]}
    )
    templates = client.get(url(org, "content-templates/")).json()
    announcement = next(t for t in templates if t["id"] == "builtin-announcement")
    page = announcement["document"]["pages"][0]
    assert page["background"] == "#123456"
    assert page["elements"][1]["font_family"] == "Poppins"
    for t in templates:  # every built-in template is a valid document
        assert documents.parse_document(t["document"]) is not None
    item = create(client, org, document=announcement["document"])
    assert item.status_code == 201, item.json()

    saved = client.post(
        url(org, "content-templates/"),
        {"name": "Our promo", "document": design()},
        format="json",
    )
    assert saved.status_code == 201 and saved.json()["kind"] == "design"
    only_carousels = client.get(url(org, "content-templates/?kind=carousel")).json()
    assert {t["kind"] for t in only_carousels} == {"carousel"}
    assert client.delete(url(org, f"content-templates/{saved.json()['id']}/")).status_code == 204


# --- Blog and email -----------------------------------------------------------------


def test_blog_and_email_rules(ready_org):
    client, org = ready_org("editor")
    email = create(client, org, platform="email", format="newsletter", caption="Hi all").json()
    assert "subject_missing" in {c["code"] for c in email["current_version"]["checks"]}
    blog = create(
        client, org, platform="blog", format="article", caption="Body", hashtags=["x"]
    ).json()
    assert "too_many_hashtags" in {c["code"] for c in blog["current_version"]["checks"]}
    assert create(client, org, platform="blog", format="post").status_code == 400


# --- AI -----------------------------------------------------------------------------


def run_result(client, org, response):
    assert response.status_code == 202, response.json()
    return client.get(url(org, f"ai/runs/{response.json()['id']}/")).json()


def test_assist_returns_suggestions_without_saving(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    item = create(client, org).json()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, f"content/{item['id']}/assist/"),
            {"operation": "alternatives", "field": "hook", "text": "Fresh coffee daily"},
            format="json",
        )
    run = run_result(client, org, response)
    assert run["status"] == "succeeded", run
    assert len(run["output"]["options"]) == 4 and run["is_mock"]
    assert ContentItem.objects.get(pk=item["id"]).versions.count() == 1  # nothing saved
    missing_language = client.post(
        url(org, f"content/{item['id']}/assist/"),
        {"operation": "translate", "field": "caption", "text": "Hello"},
        format="json",
    )
    assert missing_language.status_code == 400


def test_generate_accepts_creative_direction(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    audience = {"id": str(TargetAudience.objects.get(organization=org).pk)}
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, "content/generate/"),
            {
                "brief": "Spring menu launch",
                "targets": [{"platform": "email", "format": "newsletter"}],
                "objective": "Drive weekday visits",
                "audience": audience["id"],
                "tone": "playful",
                "language": "Arabic",
                "length": "long",
            },
            format="json",
        )
    run = run_result(client, org, response)
    assert run["status"] == "succeeded", run
    item = ContentItem.objects.get(organization=org)
    assert item.platform == "email" and item.current_version.hashtags == []


def test_storyboard_suggestion(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    item = create(client, org, format="reel").json()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url(org, f"content/{item['id']}/storyboard/"), {}, format="json")
    run = run_result(client, org, response)
    assert run["status"] == "succeeded" and len(run["output"]["scenes"]) == 3


def test_image_generation_mock_and_unavailable(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    caps = client.get(url(org, "content/capabilities/")).json()
    assert caps["image_generation"]["available"] and caps["image_generation"]["is_mock"]
    assert caps["ai_video_generation"]["available"] is False
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, "library/generate/"),
            {"prompt": "Latte art on a wooden table", "width": 512, "height": 512},
            format="json",
        )
    run = run_result(client, org, response)
    assert run["status"] == "succeeded", run
    asset = LibraryAsset.objects.get(pk=run["output"]["asset_id"])
    assert asset.source == "ai_generated" and asset.is_mock and asset.width == 512
    assert asset.generation["prompt"].startswith("Latte art")

    with override_settings(IMAGE_PROVIDER="none"):
        reset_image_provider_cache()
        try:
            off = client.post(url(org, "library/generate/"), {"prompt": "Latte art"}, format="json")
            caps = client.get(url(org, "content/capabilities/")).json()
        finally:
            reset_image_provider_cache()
    assert off.status_code == 503 and off.json()["error"]["code"] == "capability_unavailable"
    assert caps["image_generation"]["available"] is False


# --- Video --------------------------------------------------------------------------


def video_doc(clips, **extra):
    return {"kind": "video", "width": 240, "height": 426, "fps": 24, "clips": clips, **extra}


def test_video_document_rules(ready_org):
    client, org = ready_org("editor")
    audio_like = upload_library(client, org).json()  # an image can't be a soundtrack
    clip = {"id": "c1", "asset": {"source": "library", "id": audio_like["id"]}, "duration": 2}
    ok = create(client, org, format="reel", document=video_doc([clip]))
    assert ok.status_code == 201, ok.json()
    bad_audio = create(
        client,
        org,
        format="reel",
        document=video_doc(
            [clip], audio=[{"asset": {"source": "library", "id": audio_like["id"]}}]
        ),
    )
    assert bad_audio.status_code == 409
    odd = create(client, org, format="reel", document={**video_doc([clip]), "width": 241})
    assert odd.status_code == 400
    too_long = video_doc([{**clip, "id": f"c{i}", "duration": 60} for i in range(4)])
    assert create(client, org, format="reel", document=too_long).status_code == 400


def test_video_plan_builds_transitions_overlays_and_subtitles(tmp_path):
    doc = documents.parse_document(
        video_doc(
            [
                {
                    "id": "a",
                    "asset": {"source": "library", "id": "00000000-0000-0000-0000-000000000001"},
                    "duration": 3,
                    "transition": "fade",
                    "transition_duration": 1,
                    "overlay": {"text": "It's 50% off: today"},
                },
                {
                    "id": "b",
                    "asset": {"source": "library", "id": "00000000-0000-0000-0000-000000000002"},
                    "duration": 2,
                    "trim_start": 1.5,
                },
            ],
            subtitles=[{"start": 0, "end": 2, "text": "Hello, world"}],
        )
    )
    from apps.content.video import build_plan

    plan = build_plan(
        doc,
        {
            "00000000-0000-0000-0000-000000000001": ("/in/a.png", "image"),
            "00000000-0000-0000-0000-000000000002": ("/in/b.mp4", "video"),
        },
        tmp_path,
        "/font.ttf",
    )
    assert plan.duration == 4.0  # 3 + 2 - 1s fade
    assert "xfade=transition=fade:duration=1:offset=2" in plan.filter_graph
    assert "-loop" in plan.input_args and "1.5" in plan.input_args
    # User text never appears in the filter graph itself (no escaping problems).
    assert "50%" not in plan.filter_graph and "Hello, world" not in plan.filter_graph
    assert "between(t,0,2)" in plan.filter_graph
    assert not plan.has_audio


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
def test_video_upload_and_render_end_to_end(
    ready_org, django_capture_on_commit_callbacks, tmp_path
):
    client, org = ready_org("editor")
    clip_path = tmp_path / "clip.mp4"
    subprocess.run(  # noqa: S603
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=24",
            "-t",
            "2",
            "-pix_fmt",
            "yuv420p",
            str(clip_path),
        ],
        check=True,
    )
    video = upload_library(
        client, org, data=clip_path.read_bytes(), name="clip.mp4", content_type="video/mp4"
    )
    assert video.status_code == 201, video.json()
    assert video.json()["kind"] == "video" and video.json()["duration_seconds"] == pytest.approx(
        2, 0.1
    )
    image = upload_library(client, org, data=png(300, 300, "red")).json()
    doc = video_doc(
        [
            {
                "id": "c1",
                "asset": {"source": "library", "id": image["id"]},
                "duration": 1,
                "transition": "fade",
                "overlay": {"text": "New menu"},
            },
            {"id": "c2", "asset": {"source": "library", "id": video.json()["id"]}, "duration": 1.5},
        ],
        subtitles=[{"start": 0.2, "end": 1.2, "text": "Come by today"}],
    )
    item = create(client, org, format="reel", script="Shot list", document=doc).json()
    assert "render_missing" in codes(client, org, item["id"])
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url(org, f"content/{item['id']}/render-video/"))
    assert response.status_code == 202, response.json()
    job = client.get(url(org, f"render-jobs/{response.json()['id']}/")).json()
    assert job["status"] == "succeeded", job
    assert job["output"]["content_type"] == "video/mp4"
    assert job["output"]["duration_seconds"] == pytest.approx(2.0, abs=0.2)
    assert "render_missing" not in codes(client, org, item["id"])
    listed = client.get(url(org, f"content/{item['id']}/render-jobs/")).json()
    assert listed[0]["id"] == job["id"]


def test_render_failure_is_recorded_and_retryable(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    image = upload_library(client, org).json()
    clip = {"id": "c1", "asset": {"source": "library", "id": image["id"]}, "duration": 1}
    item = create(client, org, format="reel", document=video_doc([clip])).json()
    with override_settings(FFMPEG_BINARY="ffmpeg-that-does-not-exist"):
        response = client.post(url(org, f"content/{item['id']}/render-video/"))
    assert response.status_code == 503  # unavailable here, reported as such
    if not HAS_FFMPEG:
        return
    LibraryAsset.objects.filter(pk=image["id"]).update(kind="image")
    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(url(org, f"content/{item['id']}/render-video/"))
    assert first.status_code == 202
    # Simulate a deleted source file between save and render.
    job = RenderJob.objects.get(pk=first.json()["id"])
    assert job.status in {"succeeded", "failed"}
    RenderJob.objects.filter(pk=job.pk).update(status="failed", error_code="render_failed")
    with django_capture_on_commit_callbacks(execute=True):
        retry = client.post(url(org, f"content/{item['id']}/render-video/"))
    assert retry.status_code == 202
    assert RenderJob.objects.filter(item_id=item["id"]).count() == 2


def test_assist_drafts_from_scratch_with_keywords(ready_org, django_capture_on_commit_callbacks):
    client, org = ready_org("editor")
    item = create(client, org, caption="").json()
    empty = client.post(
        url(org, f"content/{item['id']}/assist/"),
        {"operation": "rewrite", "field": "caption", "text": ""},
        format="json",
    )
    assert empty.status_code == 400  # only "draft" works without text
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url(org, f"content/{item['id']}/assist/"),
            {
                "operation": "draft",
                "field": "caption",
                "text": "",
                "tone": "Friendly",
                "keywords": ["autumn", "latte"],
                "length": "short",
            },
            format="json",
        )
    run = run_result(client, org, response)
    assert run["status"] == "succeeded" and len(run["output"]["options"]) == 3
