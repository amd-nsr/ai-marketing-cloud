# Implementation checklist

What has been built, tracked against the MVP scope in `docs/master-plan.md`.
Last updated: 2026-10-24.

**How to read it**
- 🟢 Implemented and verified locally (automated tests and/or a live browser check).
- 🟡 Implemented, but not yet proven against the real external service or environment.
- 🔴 Not implemented yet.

Totals: 🟢 86 · 🟡 8 · 🔴 22 (🔴 includes 8 external pilot-setup steps).

Status at a glance: Phases 0–12 and the Meta integration (Pages + Ads) are done in code.
Backend, frontend and the Playwright pilot journey pass locally; real Meta APIs are
unverified.

---

## Phase 0 — Repository and architecture foundation
- 🟢 Monorepo: `backend/` (Django 6.1, DRF, Celery), `frontend/` (Next.js 16), `docs/`, `infrastructure/`
- 🟢 Docker Compose dev stack (Postgres 18, Redis 8, backend, worker, beat, frontend)
- 🟢 Makefile targets: setup, up, check, test, format, openapi, audit, e2e
- 🟢 Settings split (base, development, test, production); production refuses unsafe config
- 🟢 API conventions: `/api/v1`, error envelope, `X-Request-ID`, JSON logs
- 🟢 OpenAPI contract committed (`docs/api/openapi.yaml`) and checked in CI
- 🟢 Health endpoints: live, ready
- 🟢 CI workflow: lint, types, tests, migrations, OpenAPI, image builds
- 🟢 Architecture decision records 0001–0013

## Phase 1 — Authentication and multi-tenancy
- 🟢 Registration, login, logout (session cookies + CSRF via a same-origin proxy)
- 🟢 Password reset (forgot/reset flow)
- 🔴 Email verification
- 🔴 MFA / SSO
- 🟢 Organization creation; self-serve signup
- 🟢 Invitations (send, accept) and membership management
- 🟢 Roles: owner, admin, editor, analyst, viewer (permission matrix in `docs/security/roles.md`)
- 🟢 Organization switcher for users in several organizations
- 🟢 Tenant isolation: every org route returns 404 to non-members (automated sweep of 80 routes × 4 methods)
- 🟢 Throttling on auth endpoints; audit log of security-relevant actions

## Phase 2 — Business onboarding and brand context
- 🟢 Onboarding wizard (business, audience, goals and platforms, brand voice, assets)
- 🟢 Business profile with industry presets and compliance notes
- 🟢 Target audiences
- 🟢 Goals, services, preferred platforms, content languages
- 🟢 Brand voice and "never claim" guidelines
- 🟢 Logo and brand asset upload (type sniffing, size limit, storage quota)
- 🟢 Editable business context page

## Phase 3 — AI provider abstraction
- 🟢 Provider contract (one interface for every AI provider)
- 🟡 Anthropic provider (structured output) — unverified (no API key)
- 🟢 Clearly labelled mock provider (UI shows "Mock AI output")
- 🟢 Durable workflow runs (queued, running, succeeded, failed) via Celery
- 🟢 Usage records with token counts and estimated cost
- 🟢 Monthly AI request and cost quotas per organization

## Phase 4 — Marketing strategy
- 🟢 Generate a marketing plan (objectives, themes, channel allocation, campaign ideas, calendar)
- 🟢 Edit, regenerate, version history, make active
- 🟢 Quality checks with the mock (`docs/product/ai-quality.md`)
- 🔴 Quality evaluation with the real model (needs an API key)

## Phase 5 — Content studio
- 🟢 AI generation of captions, copy, platform-specific variants
- 🟢 Manual content creation
- 🟢 Editing with version history and restore
- 🟢 Organization by campaign and platform; required-field validation
- 🟢 Image attachments (upload)
- 🔴 AI image generation (optional per brief; not built)
- 🔴 Video, Reels, Stories

## Phase 6 — Campaigns, calendar, approvals
- 🟢 Campaigns, with content linked to them
- 🟢 Calendar view (planned dates)
- 🟢 Content status tracking
- 🟢 Submit for approval; approve, request changes, cancel

## Phase 7 — Social integration foundation + Facebook Pages
- 🟢 Adapter contract with capabilities checks (formats, media types, public URL requirement)
- 🟢 OAuth connect flow with single-use, expiring state
- 🟢 Tokens encrypted at rest (MultiFernet), never sent to the browser; rotation command
- 🟢 Simulation (mock) adapter, labelled in the UI, never posts anywhere
- 🟢 Publishing engine: schedule or publish now, idempotency keys, retries with backoff and jitter
- 🟢 Uncertain outcomes reconciled against the platform, never blindly re-sent
- 🟢 Notifications for failures and reconnection needs
- 🟡 Facebook Pages adapter — unverified (no Meta app credentials, no App Review)

## Phase 8 — Instagram + TikTok
- 🟡 Instagram adapter (photo and carousel; needs S3 public URLs) — unverified
- 🟡 TikTok adapter (photo posts) — unverified

## Phase 9 — Analytics and recommendations
- 🟢 Time-stamped metric snapshots; missing values stored as NULL, never 0
- 🟢 Per-platform aggregates and trends; source and retrieval time shown
- 🟢 Periodic metric collection (every 15 min), with a collection status per post
- 🟢 Rule-based recommendations with evidence (accept/dismiss)
- 🟡 Real-platform metrics — unverified

## Phase 10 — Autonomy modes and policy engine
- 🟢 Manual (default), semi-automatic, automatic modes
- 🟢 Single policy engine checked before every automated action, with readable reasons
- 🟢 Automatic-mode limits: allowed accounts, weekday/hour window, daily cap, on/off switch
- 🟢 Automation only publishes content a person approved; spending and connecting accounts never automated
- 🟢 Durable automation actions with approval queue, action history, idempotency
- 🟢 Pause, resume, cancel all pending; policy changes re-evaluate pending work
- 🟢 Calendar auto-publish and plan-drafting workflows
- 🔴 Per-campaign or per-workflow policies

## Phase 11 — Usage controls and operational hardening
- 🟢 Usage page: AI requests and cost (by operation), daily publishes, storage, against limits
- 🟢 Per-organization limit overrides (Django admin)
- 🟢 Background heartbeat and `/api/v1/health/background/`
- 🟢 Sweeper for stuck AI runs and automation actions; Celery time limits
- 🟢 Operations page: failures with error codes, queues, accounts needing reconnection
- 🟢 Frontend security headers; production backend hardening (HSTS, secure cookies)
- 🟢 Dependency audit (pip-audit, npm audit) in CI and `make audit`
- 🟢 Backup/restore drill (local), deployment guide, runbook, security review
- 🔴 Error-tracking service (e.g. Sentry)
- 🔴 Nonce-based CSP restricting scripts
- 🔴 Database-enforced append-only audit log
- 🔴 Platform-operator (cross-organization) dashboard

## Phase 12 — Pilot readiness
- 🟢 Playwright E2E of the full pilot journey (passes against the dev server and the production build)
- 🟢 E2E job in CI — passed on GitHub (first run, 2026-10-22)
- 🟢 Known limitations (`docs/product/known-limitations.md`)
- 🟢 Pilot checklist (`docs/product/pilot-checklist.md`)

## Meta integration — Facebook Pages and Facebook Ads (ADR 0014)
- 🟢 Shared Graph client: version pinning, `appsecret_proof`, pagination, usage-header throttling, error mapping
- 🟢 Meta login record: encrypted user token, granted vs declined permissions, discovered Pages and ad accounts
- 🟢 Page and ad-account selection (nothing connected automatically); read-only Pages refused
- 🟢 Disconnect revokes access on Meta; token-expiry warnings; permission-removal handling
- 🟢 Deauthorize and data-deletion callbacks (signed requests) with public status page
- 🟢 Webhooks with signature verification (ad account changes → sync; permission changes → refresh)
- 🟢 Ad account sync: campaigns, ad sets, ads, daily insights (missing ≠ 0), partial-failure tracking
- 🟢 Campaign drafts (manual and AI), deterministic validation, approval per revision
- 🟢 Create on Meta (all paused), activate, pause, budget change — only via the policy engine
- 🟢 Resumable creation (no duplicates after partial failure); lost responses recovered by name tag
- 🟢 Hard spend limits, currency match, spend-data freshness, budget-increase cap, ads kill switch
- 🟢 Automation for ads: separate switches, approval in semi-automatic, never creates campaigns
- 🟢 Deterministic ad recommendations (spend guard, no-click pause, budget-limited winner)
- 🟢 UI: Meta logins, selection page, Ads overview, campaign page, advertising limits, action queue
- 🟡 Real Graph/Marketing API behaviour — unverified (no Meta app, no App Review, no business verification)
- 🔴 Video, carousel ads, interest targeting, lifetime budgets, ad-set budgets
- 🔴 Instagram on the shared Meta connection

---

## Remaining before the pilot (external setup)
Details in `docs/product/pilot-checklist.md`.
- 🟡 Pushed to GitHub; CI green except the dependency-audit and image-build jobs (not investigated yet)
- 🔴 Production environment provisioned (managed Postgres with PITR, Redis, S3, secrets, TLS)
- 🔴 Anthropic API key configured; real-model quality and cost check
- 🔴 Meta app created; a real Facebook Page post published and verified
- 🔴 Meta App Review, business verification and Advanced Access for ads permissions; real ads validation checklist run
- 🔴 Transactional email provider configured and tested
- 🔴 Restore drill on the managed database
- 🔴 Uptime monitoring and log alerts
- 🔴 Pilot organization limits set; customer briefed on limitations
