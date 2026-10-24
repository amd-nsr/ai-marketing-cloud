"""Server-side rendering of video projects (documents.VideoDocument) with ffmpeg.

Runs in a Celery worker (tasks.render_video). The editable project is the version's
document; the result is a ContentAsset(source="render") MP4 (H.264/AAC, faststart).

Supported: image and video clips (cover-cropped to the output size), trimming and
duration, text overlays, timed subtitles (burned in), fade transitions, up to two audio
tracks (music and/or voiceover) with volume and start offset. Not supported (yet):
original clip audio (clips are muted), Ken Burns motion, AI voiceover or AI video.
"""

import hashlib
import logging
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit

from . import documents
from .media import probe
from .models import ContentAsset, ContentItem, LibraryAsset, RenderJob

logger = logging.getLogger(__name__)


class RenderError(Exception):
    """A render failure with a message that is safe to show the user."""

    def __init__(self, message: str, code: str = "render_failed") -> None:
        super().__init__(message)
        self.code = code


def _color(value: str) -> str:
    return "0x" + value.lstrip("#") if value.startswith("#") else "0x000000@0"


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _wrap(text: str, width: int, font_size: int) -> str:
    chars = max(int(width * 0.9 / (font_size * 0.55)), 8)
    return "\n".join(textwrap.wrap(text, chars) or [text])


@dataclass(frozen=True)
class Plan:
    """An ffmpeg invocation: input arguments, the filter graph, and the output length."""

    input_args: list[str]
    filter_graph: str
    has_audio: bool
    duration: float


def build_plan(
    doc: documents.VideoDocument,
    files: dict[str, tuple[str, str]],
    workdir: Path,
    font_file: str,
) -> Plan:
    """Build the ffmpeg inputs and filter graph.

    ``files`` maps asset id -> (local path, kind). Text goes through ``textfile=`` files
    so user text never needs filter-graph escaping.
    """
    if not doc.clips:
        raise RenderError("Add at least one clip before rendering.", "video_empty")
    w, h, fps = doc.width, doc.height, doc.fps
    args: list[str] = []
    chains: list[str] = []
    text_n = 0

    def textfile(text: str) -> str:
        nonlocal text_n
        text_n += 1
        path = workdir / f"text_{text_n}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def drawtext(text: str, size: int, color: str, y: str, box: bool, enable: str = "") -> str:
        parts = [
            f"fontfile='{font_file}'",
            f"textfile='{textfile(_wrap(text, w, size))}'",
            f"fontcolor={_color(color)}",
            f"fontsize={size}",
            "line_spacing=8",
            "x=(w-text_w)/2",
            f"y={y}",
        ]
        if box:
            parts += ["box=1", "boxcolor=0x000000@0.45", "boxborderw=24"]
        if enable:
            parts.append(f"enable='{enable}'")
        return "drawtext=" + ":".join(parts)

    for i, clip in enumerate(doc.clips):
        path, kind = files[str(clip.asset.id)]
        dur = _num(clip.duration)
        if kind == "image":
            args += ["-loop", "1", "-framerate", str(fps), "-t", dur, "-i", path]
        else:
            args += ["-ss", _num(clip.trim_start), "-t", dur, "-i", path]
        chain = (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"setsar=1,fps={fps},format=yuv420p,"
            f"tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur},"
            "setpts=PTS-STARTPTS,settb=AVTB"
        )
        if clip.overlay:
            o = clip.overlay
            y = {
                "top": "h*0.08",
                "center": "(h-text_h)/2",
                "bottom": "h*0.86-text_h",
            }[o.position]
            chain += "," + drawtext(o.text, o.font_size, o.color, y, o.background)
        chains.append(f"{chain}[c{i}]")

    current, length = "c0", doc.clips[0].duration
    for i in range(1, len(doc.clips)):
        prev, clip = doc.clips[i - 1], doc.clips[i]
        out = f"j{i}"
        if prev.transition == "fade":
            d = min(prev.transition_duration, length - 0.1, clip.duration - 0.1)
            chains.append(
                f"[{current}][c{i}]xfade=transition=fade:duration={_num(d)}:"
                f"offset={_num(length - d)}[{out}]"
            )
            length += clip.duration - d
        else:
            chains.append(f"[{current}][c{i}]concat=n=2:v=1:a=0[{out}]")
            length += clip.duration
        current = out

    video_out = current
    if doc.subtitles:
        size = max(int(min(w, h) * 0.045), 18)
        subs = [
            drawtext(
                s.text,
                size,
                "#ffffff",
                "h*0.78-text_h",
                True,
                enable=f"between(t,{_num(s.start)},{_num(s.end)})",
            )
            for s in doc.subtitles
            if s.start < length
        ]
        if subs:
            chains.append(f"[{current}]" + ",".join(subs) + "[vsub]")
            video_out = "vsub"
    chains.append(f"[{video_out}]null[vout]")

    audio_labels = []
    for j, track in enumerate(doc.audio):
        path, _ = files[str(track.asset.id)]
        index = len(doc.clips) + j
        args += ["-i", path]
        delay = int(track.start * 1000)
        chains.append(
            f"[{index}:a]aresample=44100,asetpts=PTS-STARTPTS,volume={_num(track.volume)},"
            f"adelay=delays={delay}:all=1[a{j}]"
        )
        audio_labels.append(f"[a{j}]")
    if len(audio_labels) == 2:
        chains.append(
            f"{''.join(audio_labels)}amix=inputs=2:duration=longest:dropout_transition=0,"
            f"apad,atrim=0:{_num(length)}[aout]"
        )
    elif audio_labels:
        chains.append(f"{audio_labels[0]}apad,atrim=0:{_num(length)}[aout]")
    return Plan(args, ";\n".join(chains), bool(audio_labels), round(length, 3))


def ffmpeg_command(plan: Plan, script: Path, output: Path, fps: int) -> list[str]:
    cmd = [
        settings.FFMPEG_BINARY,
        "-hide_banner",
        "-nostdin",
        "-y",
        *plan.input_args,
        "-filter_complex_script",
        str(script),
        "-map",
        "[vout]",
    ]
    cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"] if plan.has_audio else ["-an"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-t",
        _num(plan.duration),
        "-movflags",
        "+faststart",
        str(output),
    ]
    return cmd


def _fetch_assets(job: RenderJob, doc: documents.VideoDocument, workdir: Path) -> dict[str, Any]:
    refs = {str(r.id) for r in documents.asset_refs(doc) if r.source == "library"}
    assets = {
        str(a.pk): a
        for a in LibraryAsset.objects.filter(organization=job.organization, pk__in=refs)
    }
    missing = refs - set(assets)
    if missing:
        raise RenderError("A clip or audio file was deleted from the library.", "asset_missing")
    files: dict[str, tuple[str, str]] = {}
    for key, asset in assets.items():
        name = asset.file.name or ""
        target = workdir / f"in_{key}{Path(name).suffix}"
        with asset.file.storage.open(name, "rb") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        files[key] = (str(target), asset.kind)
    return files


def render(job: RenderJob) -> ContentAsset:
    """Render the job's version. Raises RenderError on any expected failure."""
    from .services import refresh_checks

    if not shutil.which(settings.FFMPEG_BINARY):
        raise RenderError("Video rendering isn't available on this server.", "ffmpeg_missing")
    doc = documents.parse_document(job.version.document)
    if not isinstance(doc, documents.VideoDocument):
        raise RenderError("This version has no video project.", "video_empty")
    expected_hash = documents.render_hashes(doc)["video"]
    with tempfile.TemporaryDirectory(prefix="amc-render-") as tmp:
        workdir = Path(tmp)
        files = _fetch_assets(job, doc, workdir)
        plan = build_plan(doc, files, workdir, settings.VIDEO_FONT_FILE)
        script = workdir / "graph.txt"
        script.write_text(plan.filter_graph, encoding="utf-8")
        output = workdir / "out.mp4"
        try:
            result = subprocess.run(  # noqa: S603
                ffmpeg_command(plan, script, output, doc.fps),
                capture_output=True,
                timeout=settings.VIDEO_RENDER_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("Rendering took too long. Try a shorter video.", "timeout") from exc
        if result.returncode != 0 or not output.exists():
            logger.error(
                "ffmpeg failed",
                extra={
                    "job_id": str(job.pk),
                    "stderr": result.stderr.decode(errors="replace")[-2000:],
                },
            )
            raise RenderError(
                "The video couldn't be rendered. Check that every clip plays, then retry."
            )
        info = probe(str(output))
        size = output.stat().st_size
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        from apps.usage.storage import check_storage_quota

        check_storage_quota(job.organization, size)
        with transaction.atomic():
            item = ContentItem.objects.select_for_update().get(pk=job.item_id)
            if item.current_version_id != job.version_id:
                raise RenderError(
                    "The video project changed while rendering. Render it again.", "superseded"
                )
            for old in item.assets.filter(source=ContentAsset.Source.RENDER):
                old.delete()
            with output.open("rb") as fh:
                asset = ContentAsset.objects.create(
                    organization=job.organization,
                    item=item,
                    file=File(fh, name="render.mp4"),
                    original_filename=f"{item.title[:200]}.mp4",
                    content_type="video/mp4",
                    size_bytes=size,
                    width=doc.width,
                    height=doc.height,
                    duration_seconds=float(info.get("format", {}).get("duration") or plan.duration),
                    sha256=digest,
                    position=0,
                    uploaded_by=job.created_by,
                    source=ContentAsset.Source.RENDER,
                    version=job.version,
                    page_id="video",
                    source_hash=expected_hash,
                )
            for position, other in enumerate(
                item.assets.filter(source=ContentAsset.Source.UPLOAD), start=1
            ):
                other.position = position
                other.save(update_fields=["position", "updated_at"])
            refresh_checks(item)
    return asset


def execute(job_id: str) -> None:
    """Run one render job. Idempotent: anything but a queued job is skipped."""
    with transaction.atomic():
        job = RenderJob.objects.select_for_update().select_related("version").get(pk=job_id)
        if job.status != RenderJob.Status.QUEUED:
            return
        job.status = RenderJob.Status.RUNNING
        job.started_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "started_at", "attempts", "updated_at"])
    try:
        asset = render(job)
    except RenderError as exc:
        _finish(job, failed=True, code=exc.code, message=str(exc))
        return
    except Exception:
        logger.exception("Video render crashed", extra={"job_id": job_id})
        _finish(
            job,
            failed=True,
            code="render_failed",
            message="Something went wrong while rendering. Please retry.",
        )
        return
    job.output = asset
    _finish(job, failed=False)


def _finish(job: RenderJob, *, failed: bool, code: str = "", message: str = "") -> None:
    job.status = RenderJob.Status.FAILED if failed else RenderJob.Status.SUCCEEDED
    job.error_code, job.error_message = code, message[:500]
    job.finished_at = timezone.now()
    job.save()
    audit.record(
        "content_render.failed" if failed else "content_render.succeeded",
        organization=job.organization,
        target=job,
        system=True,
        metadata={"item": str(job.item_id), "error_code": code}
        if failed
        else {"item": str(job.item_id)},
    )
