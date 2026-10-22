# 0010 — Social integrations and the publishing engine

**Status:** Accepted (2026-10-20)

## Context
Publishing to Instagram, TikTok and Facebook must be reliable (no duplicate posts, no
silent failures), honest about each platform's real capabilities, and testable without
real accounts.

## Decision
- **One adapter contract** (`apps/social/adapters/base.py`) for authorization, publishing,
  reconciliation lookup and metrics. Each adapter declares `PlatformCapabilities`
  (formats, media rules, text-only support, metrics); services and UI consult them rather
  than assuming parity. Platform errors are normalized into `SocialError` subclasses with
  `retryable`, `needs_reauth` and `uncertain` flags.
- **Simulation adapter** for tests and local trials: accounts are flagged `is_mock` and
  labelled "Simulation" everywhere; disabled unless `SOCIAL_MOCK_ENABLED` (default on only
  in development/test). Real and simulation adapters are chosen explicitly per account,
  never swapped automatically.
- **First real platform: Facebook Pages.** Chosen after reviewing current Meta and TikTok
  documentation (2026-10-20): Pages support text, link and photo posts; development mode
  works for app role holders; Page tokens don't expire under normal conditions.
  Instagram requires JPEG media at a public URL (needs S3) and a professional account;
  TikTok restricts unaudited apps to private posts. Instagram and TikTok adapters exist
  on the same contract (Phase 8) with these constraints encoded as capabilities.
- **Credentials:** OAuth with single-use, user-bound, 15-minute `state`; PKCE where the
  platform supports it (TikTok). Tokens are encrypted at rest with MultiFernet
  (`SOCIAL_TOKEN_ENCRYPTION_KEYS`, rotation-friendly), never serialized to the API, and
  destroyed on disconnect.
- **Publishing jobs** (`apps/publishing`) with explicit states:
  scheduled → queued → publishing → published | failed | needs_reconciliation; cancelled.
  - Only approved content, and only the exact approved version, can be published.
  - Idempotency keys (`Idempotency-Key` header) plus a DB constraint against two live jobs
    for the same content and account prevent duplicates.
  - Every attempt is recorded before the network call.
  - Retryable errors back off exponentially with jitter (bounded attempts); revoked
    credentials mark the account "Reconnect required"; permanent errors fail visibly
    and notify publishers.
  - **Uncertain outcomes are never resubmitted automatically.** The job moves to
    `needs_reconciliation`; the reconciler looks for the post on the platform. If it
    can't confirm after 3 checks, the job fails as `unconfirmed` and a retry requires the
    user to confirm the post isn't there.
  - Jobs stuck in `publishing` (worker crash) move to reconciliation.
  - Celery beat (single instance) dispatches due jobs every 30s and reconciles every 60s.
- Publishing calls an automation-policy hook before creating a job; the policy engine
  (Phase 10) plugs in there.

## Consequences / status
- Code complete and tested against stubbed platform APIs and the simulation adapter.
- **No real platform call has been made** (no Meta/TikTok app credentials). Each platform
  needs app registration and, for production, platform review: see `docs/integrations/`.
- Video upload (Reels, TikTok video, Stories) is not implemented.
