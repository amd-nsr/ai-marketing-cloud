"""Validation for user-uploaded files. Content is inspected; client claims are not trusted."""

import hashlib
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

# Pillow format -> (content type, extension). SVG is deliberately excluded (script risk).
ALLOWED_IMAGE_FORMATS: dict[str, tuple[str, str]] = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}
MAX_IMAGE_PIXELS = 40_000_000  # ~40 MP; guards against decompression bombs


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    extension: str
    width: int
    height: int
    size_bytes: int
    sha256: str


def _sha256(upload: UploadedFile[Any]) -> str:
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def validate_image(upload: UploadedFile[Any]) -> ImageInfo:
    max_bytes: int = settings.MAX_IMAGE_UPLOAD_BYTES
    if upload.size is None or upload.size == 0:
        raise ValidationError({"file": "The file is empty."})
    if upload.size > max_bytes:
        raise ValidationError(
            {"file": f"Images must be {max_bytes // (1024 * 1024)} MB or smaller."}
        )
    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt = img.format or ""
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValidationError({"file": "The image dimensions are too large."})
            img.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(
            {"file": "The file is not a valid PNG, JPEG, or WebP image."}
        ) from exc
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError({"file": "Only PNG, JPEG, and WebP images are supported."})
    content_type, ext = ALLOWED_IMAGE_FORMATS[fmt]
    return ImageInfo(content_type, ext, width, height, upload.size, _sha256(upload))
