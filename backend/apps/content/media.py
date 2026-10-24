"""Validation of uploaded video and audio, by inspecting the content with ffprobe.

Like images (apps/core/uploads.py), client filenames and MIME types are not trusted:
the container and codecs are probed, and only a small set of formats is accepted.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework.exceptions import ValidationError

from apps.core.errors import ServiceUnavailable

VIDEO_CODECS = frozenset({"h264", "hevc", "vp8", "vp9", "av1", "mpeg4"})
AUDIO_CODECS = frozenset({"aac", "mp3", "opus", "vorbis", "pcm_s16le", "pcm_s24le", "flac"})
MAX_DIMENSION = 4096


@dataclass(frozen=True)
class MediaInfo:
    kind: str  # "video" | "audio"
    content_type: str
    extension: str
    size_bytes: int
    duration_seconds: float
    sha256: str
    width: int | None = None
    height: int | None = None


def ffmpeg_available() -> bool:
    return bool(shutil.which(settings.FFPROBE_BINARY) and shutil.which(settings.FFMPEG_BINARY))


def probe(path: str) -> dict[str, Any]:
    if not shutil.which(settings.FFPROBE_BINARY):
        raise ServiceUnavailable("Video and audio processing isn't available on this server.")
    try:
        result = subprocess.run(  # noqa: S603
            [
                settings.FFPROBE_BINARY,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValidationError({"file": "The file could not be read in time."}) from exc
    if result.returncode != 0:
        raise ValidationError({"file": "The file is not a readable video or audio file."})
    data: dict[str, Any] = json.loads(result.stdout or b"{}")
    return data


def _container(fmt: str, kind: str) -> tuple[str, str]:
    names = set(fmt.split(","))
    if kind == "video":
        if names & {"mp4", "mov", "m4a", "3gp"}:
            return ("video/mp4", ".mp4") if "mp4" in names else ("video/quicktime", ".mov")
        if names & {"webm", "matroska"}:
            return "video/webm", ".webm"
        raise ValidationError({"file": "Only MP4, MOV, and WebM videos are supported."})
    if "mp3" in names:
        return "audio/mpeg", ".mp3"
    if "wav" in names:
        return "audio/wav", ".wav"
    if "ogg" in names:
        return "audio/ogg", ".ogg"
    if names & {"mp4", "mov", "m4a"}:
        return "audio/mp4", ".m4a"
    raise ValidationError({"file": "Only MP3, M4A, WAV, and OGG audio is supported."})


def validate_media(upload: UploadedFile[Any]) -> MediaInfo:
    """Validate a video or audio upload; the kind is decided by the streams it contains."""
    max_bytes: int = settings.MAX_MEDIA_UPLOAD_BYTES
    if not upload.size:
        raise ValidationError({"file": "The file is empty."})
    if upload.size > max_bytes:
        raise ValidationError(
            {"file": f"Videos and audio must be {max_bytes // (1024 * 1024)} MB or smaller."}
        )
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(suffix=".upload") as tmp:
        upload.seek(0)
        for chunk in upload.chunks():
            digest.update(chunk)
            tmp.write(chunk)
        tmp.flush()
        upload.seek(0)
        data = probe(tmp.name)
    streams = data.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    kind = "video" if video else "audio" if audio else ""
    if not kind:
        raise ValidationError({"file": "The file contains no video or audio."})
    if video and video.get("codec_name") not in VIDEO_CODECS:
        raise ValidationError({"file": "This video codec isn't supported. Use H.264 MP4."})
    if not video and audio and audio.get("codec_name") not in AUDIO_CODECS:
        raise ValidationError({"file": "This audio codec isn't supported. Use MP3 or AAC."})
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    if duration <= 0:
        raise ValidationError({"file": "The file has no playable duration."})
    if duration > settings.MAX_MEDIA_DURATION_SECONDS:
        minutes = settings.MAX_MEDIA_DURATION_SECONDS // 60
        raise ValidationError({"file": f"Media must be {minutes} minutes or shorter."})
    width = int(video["width"]) if video and video.get("width") else None
    height = int(video["height"]) if video and video.get("height") else None
    if width and height and max(width, height) > MAX_DIMENSION:
        raise ValidationError({"file": "The video resolution is too large (max 4096 px)."})
    content_type, ext = _container(str(data.get("format", {}).get("format_name", "")), kind)
    return MediaInfo(
        kind=kind,
        content_type=content_type,
        extension=ext,
        size_bytes=upload.size,
        duration_seconds=round(duration, 3),
        sha256=digest.hexdigest(),
        width=width,
        height=height,
    )
