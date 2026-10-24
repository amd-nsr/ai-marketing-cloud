# 0015 — Content studio: editable documents, media library, rendering, image generation

**Status:** Accepted (2026-10-24)

## Context
Content Studio grew from "a form that stores AI text" into a production workspace:
writing, visual designs, carousels, short videos, and coordinated campaign creatives.
Visuals must stay editable after saving, rendered files must be what gets approved and
published, and AI image/video generation must be optional capabilities, not assumptions.
The existing content, approval, calendar and publishing subsystems must be reused, not
duplicated.

## Decision

### One content model, with an editable source document per version
- `ContentVersion.document` (JSON, `{}` = none) holds the editable source. Versions stay
  immutable, so designs get version history and restore for free, and an approval
  remains bound to the exact version (text **and** design) that was reviewed.
- The document kind follows the item's format: `post`/`story` → `design` (1 page),
  `carousel` → `carousel` (1–20 pages), `reel`/`short_video` → `video`
  (`documents.DOCUMENT_KIND_FOR_FORMAT`). Blog/email have no visual document.
- Documents are validated with Pydantic (`apps/content/documents.py`, `schema_version: 1`):
  element geometry, text styles, colors (`#RRGGBB[AA]` or `transparent`), layer order (array
  order), unique ids, page/element/clip limits, video length ≤ 180 s, even video
  dimensions. Unknown fields are rejected. The TypeScript mirror is
  `frontend/src/features/content/studio/document.ts`; the server is authoritative.
- **Asset references are tenant-checked on every save**: every `{source, id}` must be a
  `LibraryAsset` or `BrandAsset` of the same organization, of a kind valid for its use
  (images in designs; image/video clips; audio tracks).

### Rendered outputs are separate files
- Renders are `ContentAsset(source="render")` with `version`, `page_id` and
  `source_hash` (SHA-256 of the page/video source at render time). Publishing keeps
  reading `item.assets`, unchanged.
- **Stale detection:** checks compare stored hashes with the current document. A missing
  or out-of-date render is a blocking check (`render_missing`, `render_stale`), so content
  cannot be submitted for approval or published with media that doesn't match its design.
  Caption edits don't change the hashes and don't force a re-export.
- Renders may only change in `draft`/`changes_requested`, never while a reviewer is
  looking at the content or after approval.
- **Designs and carousels render in the browser** with the same Konva code that draws the
  editor (`studio/render.ts` + shared `konva-attrs.ts`), at the exact output size, then
  upload per page; the server validates the image by content and its dimensions. This
  gives exact WYSIWYG without maintaining a second renderer. Trade-off: automation can't
  render a design without a browser (a server renderer is a possible follow-up).
- **Videos render on the server** in a Celery task (`content.render_video`) with ffmpeg:
  cover-cropped image/video clips, trimming, fades (`xfade`), text overlays and burned-in
  subtitles (`drawtext` with `textfile=`, so user text is never interpolated into the
  filter graph), up to two audio tracks, H.264/AAC MP4 with faststart. Each render is a
  `RenderJob` (queued → running → succeeded/failed, attempts, error, output). A job for a
  superseded version fails instead of attaching mismatched media; stuck jobs are failed
  after the timeout when a new render is requested.

### Media library
- `LibraryAsset` is the organization-wide, reusable media store (image/video/audio;
  uploaded or AI-generated), searchable by title and tags. The brand kit
  (`BrandAsset`: logos, approved images) stays where it is and is offered alongside.
- Uploads are validated by content: Pillow for images (existing rules), **ffprobe** for
  video/audio (container, codecs, duration, resolution). Storage quotas apply.
- A library file used by a current design of live content can't be deleted.
- Files are served only through the organization-scoped endpoint (ADR 0008).

### AI capabilities
- Text: the existing AI layer (ADR 0009). New workflows: `content.assist` (rewrite,
  shorten, expand, translate, tone, alternatives, proofread, hashtags, emoji, **draft from
  scratch**, with tone/keywords/length/language), `content.storyboard` (video scene plan).
  Assist results are suggestions only; nothing is saved until the person saves a version.
- **Image generation is a separate capability** (`apps/ai/images.py`, `IMAGE_PROVIDER`):
  `none` (default, reported as *unavailable*, never as an error), `mock` (labelled
  placeholder images, dev/test). Generated images go to the library, are re-validated like
  uploads, count against the AI quota, and are recorded as `AIUsageRecord`s
  (`IMAGE_COST_PER_IMAGE_USD`). **No real vendor is integrated yet**: choosing one is a
  product/vendor decision (candidates: OpenAI Images, Google Imagen, Stability); it means
  implementing `ImageProvider` and registering it.
- AI video generation and AI voiceover are **not available** and are reported as such by
  `GET /orgs/<id>/content/capabilities/`. Videos are edited from the business's own clips.

### Channels and campaign creatives
- Content platforms gain `blog` (`article`) and `email` (`newsletter`): written, checked,
  approved and planned here, then exported (copied) to the business's own tools. They have
  no social account, so publishing refuses them; social models keep their own
  `SocialPlatform` choices.
- Campaign creatives reuse campaigns + generation: a creative set is a multi-target
  generation with the campaign's objective and key messages; variations and
  platform adaptations are `POST /content/<id>/duplicate/` (text always copied; the design
  only when the target format uses the same document kind; renders and approvals never).
  Ads remain in the ads module (ADR 0014).

### Templates
Built-in starter templates are generated in code with the organization's brand colors and
fonts; organizations can save their own (`ContentTemplate`). Applying a template copies
its document; nothing stays linked.

## Consequences
- Migration `content.0003` adds `ContentVersion.document`, render fields on
  `ContentAsset`, and the `LibraryAsset`, `ContentTemplate`, `RenderJob` tables. No data
  migration: existing content simply has no document.
- Worker images need `ffmpeg` and a font (`fonts-dejavu-core`); the backend Dockerfile
  installs both.
- Uploads still pass through the Next.js proxy (ADR 0003). Next buffers proxied bodies
  and truncates above `experimental.proxyClientMaxBodySize`, so it is raised to 105 MB
  (`MAX_PROXY_BODY_SIZE`). Direct-to-storage presigned uploads remain the scalable
  follow-up for large video.
- With S3 storage, images loaded into the canvas follow redirects to signed URLs, so the
  bucket needs a CORS rule allowing `GET` from the app origin, or the browser can't export
  designs (tainted canvas).
- Text renders with fonts available in the browser. Brand fonts not installed on the
  editor's machine fall back to sans-serif, in the editor and the export alike.
