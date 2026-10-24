# Known limitations (pilot build, 2026-10-20)

What a pilot customer and the team should know before relying on the product. Each item
says whether it is a **product gap** (not built), **unverified** (built but not proven
against the real external system), or **operational**.

## External integrations — unverified
- **Anthropic (AI)**: implemented against the official SDK and tested with the mock
  provider. No real API key has been used, so output quality, latency and the cost
  estimates are unmeasured. All AI output in development and E2E is the labelled mock.
- **Facebook Pages, Facebook Ads, Instagram, TikTok**: implemented and tested against
  stubbed APIs and labelled simulations only. No app credentials are configured, no real
  account has been connected, no real post or campaign has been created, and none of the
  apps has passed platform review (`docs/integrations/README.md`, which includes a
  real-account validation checklist). For the pilot, start with Facebook Pages; Ads
  additionally needs Meta business verification and Advanced Access for `ads_management`.
- **Instagram** needs public media URLs, so `STORAGE_BACKEND=s3` is required.
- **Email** (invitations, password reset) has been verified only with the console/locmem
  backends.

## Product gaps
- Formats: video, Reels and TikTok videos can be **created and rendered** (MP4) in the
  Content studio and downloaded, but the social adapters still **publish images only**;
  publishing a rendered video is not supported yet. Stories are created as designs.
- Content studio (ADR 0015):
  - **Image generation**: no real vendor is integrated; development uses labelled mock
    images and production reports the capability as unavailable. AI video generation and
    AI voiceover are not available (videos are edited from the business's own media).
  - **Video**: original clip sound is muted (music/voiceover tracks only); transitions are
    cuts and fades; no Ken Burns motion, no automatic captions from speech; one render at
    a time per item; max 180 s per video.
  - **Designs** export in the browser at full size. Fonts must be available in the
    editor's browser (brand fonts that aren't installed fall back to sans-serif). There is
    no server-side design renderer, so automation can't re-export designs by itself.
  - **Uploads** pass through the web proxy (up to `MAX_MEDIA_UPLOAD_BYTES`, 100 MB);
    resumable/direct-to-storage uploads are not built.
  - Blog and email content is written, approved and planned here but not sent or posted:
    it is copied out to the business's own tools.
  - No folders/projects inside the studio; campaigns and filters organize content.
- Facebook Ads (added after the MVP brief, ADR 0014):
  - objectives: Traffic, Awareness and Engagement;
  - targeting: countries and age only;
  - creatives: link ads with an optional image; no video or carousel ads;
  - budgets: campaign daily budget (CBO) only;
  - insights: daily at campaign level, read synchronously.
  Spend limits rely on synced spend, so they are as current as the last sync (at most
  `ADS_SPEND_DATA_MAX_AGE_HOURS`); Meta's own account spend cap is not read or set.
- Instagram still connects through its own login flow (not the shared Meta connection).
- Analytics: metrics come only from platforms that report them (missing values stay
  "not available"). Recommendations are deterministic rules, not AI, and no attribution
  to sales or foot traffic is attempted.
- Automation: one policy per organization; no per-campaign or per-workflow policies. No
  auto-approval of AI content. Automation never publishes content a person didn't approve.
- No MFA, SSO, or billing/subscriptions. Usage limits are set per organization in Django admin.
- Languages: UI is English only; content can be generated in the configured content languages.
- No cross-organization (platform-operator) dashboard; operators use logs, health
  endpoints and Django admin.

## Security follow-ups (from `docs/security/review.md`)
- CSP does not restrict `script-src` yet (nonce-based CSP is planned).
- Audit log is append-only by convention, not enforced at the database level.
- No error-tracking service integrated.
- Dev-only npm dependencies (`eslint-config-next` toolchain) report advisories. Production
  dependencies audit clean.

## Operational
- No real production deployment has been done. The deployment, backup and runbook docs are
  written and the restore drill passed locally, but not against a managed database.
- CI, including the new E2E and dependency-audit jobs, has not run on GitHub yet: there are
  no commits or remote.
- Next.js dev server logs "Could not validate … instant navigation" warnings for org pages
  (they wait for client-side membership data). Development only; no user impact.
- Beat must run as exactly one process. Nothing enforces this beyond the deployment config.
