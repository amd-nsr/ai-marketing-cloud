# Known limitations (pilot build, 2026-10-20)

What a pilot customer and the team should know before relying on the product. Each item
says whether it is a **product gap** (not built), **unverified** (built but not proven
against the real external system), or **operational**.

## External integrations — unverified
- **Anthropic (AI)**: implemented against the official SDK and tested with the mock
  provider. No real API key has been used, so output quality, latency and the cost
  estimates are unmeasured. All AI output in development and E2E is the labelled mock.
- **Facebook Pages, Instagram, TikTok**: implemented and tested against stubbed APIs only.
  No app credentials are configured, no real account has been connected, and none of the
  apps has passed platform review (`docs/integrations/README.md`). For the pilot, start
  with Facebook Pages and budget time for Meta App Review.
- **Instagram** needs public media URLs, so `STORAGE_BACKEND=s3` is required.
- **Email** (invitations, password reset) has been verified only with the console/locmem
  backends.

## Product gaps
- Formats: no video, Reels, Stories or TikTok video; images only where supported.
- No paid advertising, budgets or spend of any kind (by design for the MVP).
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
