# 0008 — Media storage and delivery

**Status:** Accepted (2026-10-19)

## Decision
- Files live in Django's default storage: local filesystem in development
  (`MEDIA_ROOT`), S3-compatible object storage in production (`STORAGE_BACKEND=s3`;
  works with AWS S3, Cloudflare R2, MinIO via `S3_ENDPOINT_URL`). Metadata (type, size,
  dimensions, SHA-256, uploader) is stored in PostgreSQL; binaries never are.
- Storage paths are generated (`orgs/<org_id>/<area>/<uuid>.<ext>`); client filenames
  are kept only as metadata.
- Files are **never publicly served**. Downloads go through an organization-scoped API
  endpoint that checks membership, then streams the file (local) or redirects to a
  short-lived signed URL (S3, default 10 minutes).
- Uploads are validated by content (Pillow decode + verify), not by extension or the
  client's MIME type. MVP accepts PNG, JPEG, WebP up to 10 MB; SVG is rejected
  (script risk). Decompression bombs are bounded by a pixel limit.
- Per-organization storage quotas are enforced at upload time (`apps/usage/storage.py`).
- Uploads currently pass through the Next.js proxy. Video (Phase 5+) must use direct
  browser-to-storage uploads with presigned URLs instead.

## Consequences
- Social platforms that fetch media by URL (Instagram) need a publicly reachable URL:
  signed S3 URLs satisfy this in production; local development storage does not (the
  integration must report this clearly rather than fail mysteriously).
