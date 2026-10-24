# Security review (Phase 11)

Internal review of the pilot build on 2026-10-20 by the implementing engineer. **This is
not an independent penetration test.** One is recommended before onboarding customers
beyond the pilot.

Legend: **Verified** = automated test or reproducible manual check; **Configured** =
in place but not exercised against a real deployment.

## Controls by area

| Area | Control | Status |
| --- | --- | --- |
| Tenant isolation | Every org route resolves the organization from membership; non-members get 404 (indistinguishable from a missing org). | **Verified**: `tests/test_tenant_isolation.py` walks *every* registered org route (80 routes × GET/POST/PATCH/DELETE). |
| Tenant isolation | Related objects in request bodies are restricted to the same org (`OrgScopedRelatedField`); viewsets can't drop the org scope (base-order guard). | **Verified**: per-app tests. |
| Authorization | Role → permission matrix; every view declares read/write/action permissions; UI hides but server enforces. | **Verified**: role tests per app; `docs/security/roles.md`. |
| Authentication | Session cookies (HttpOnly, Secure, SameSite=Lax in production), CSRF on unsafe methods, password validators (min 12), throttled login/signup/reset. | **Verified** in tests; Secure flags **Configured**. |
| Automation | Automation can only publish content a person approved; the publishing engine independently refuses automation jobs without a cleared action; spending and connecting accounts are never automated. | **Verified**: policy matrix tests (ADR 0012). |
| Platform credentials | OAuth tokens encrypted at rest (MultiFernet, rotation via `rotate_social_tokens`), never serialized, logged or sent to the browser; OAuth `state` is single-use and expires. | **Verified**: tests; restore drill confirmed decryption with the configured key. |
| Uploads | Type sniffing (not extension), size limit, storage quota, private bucket with signed URLs. Video/audio are probed with ffprobe (container, codecs, duration, resolution) on a temp copy; SVG is never accepted. Generated images are re-validated like uploads. | **Verified**: upload tests. S3 path **Configured**. |
| Content studio documents | Design/video documents are schema-validated (unknown fields rejected); every asset reference must belong to the same organization and be of a valid kind; files are only served via org-scoped endpoints. Renders must match the page size and a page of the current version, and are frozen during review. ffmpeg runs with a fixed argv (no shell); user text reaches ffmpeg only via `textfile=`, never in the filter graph. | **Verified**: tests (`apps/content/tests/test_studio_api.py`). |
| AI | Prompt inputs come from the org's own data. Outputs are schema-validated, rendered as text (never HTML or executed), and never published without human approval. Provider keys are server-side only. Monthly request/cost quotas. | **Verified**: tests with the mock provider. Real provider **unverified** (no key). |
| Abuse / cost | Per-org monthly AI quota, daily publish limit, storage quota, AI and auth throttles. | **Verified**: tests. |
| Error handling | Uniform error envelope; no stack traces; request IDs on all responses and logs. | **Verified**: tests. |
| Browser hardening | Frontend: `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`, CSP `frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`. Backend production: HSTS, SSL redirect, secure cookies. | **Verified** with `curl -I` on the dev server; production values **Configured**. |
| Supply chain | Lockfiles (`uv.lock`, `package-lock.json`); CI runs `pip-audit --strict` and `npm audit --omit=dev`. | **Verified** locally 2026-10-20: 0 known vulnerabilities. |
| Meta integration | `appsecret_proof` on every Graph call; OAuth `state` single-use; tokens encrypted; callbacks (deauthorize, data deletion) verified with HMAC-signed requests; webhooks verified with `X-Hub-Signature-256`; Meta access revoked on disconnect; data-deletion purges Meta-derived data and records a confirmation code. | **Verified**: tests with stubbed Graph API. Real Meta **unverified**. |
| Ad spend | Every ad write is a policy-evaluated action; limits (per-campaign, total daily, monthly, max increase %), currency match, spend-data freshness and the kill switch are checked in code for people and automation alike; missing limits mean refusal; AI only drafts. | **Verified**: policy tests (simulation). |
| Audit trail | Security-relevant and automation actions recorded with actor, target and metadata; read-only API for admins. | **Verified**: tests. |
| Operations | Health endpoints expose no tenant data or secrets; ops overview is owner/admin-only. | **Verified**: tests. |

## Findings and follow-ups

| # | Finding | Severity | Status |
| --- | --- | --- | --- |
| 1 | CSP does not restrict `script-src`. Next.js inline bootstrap scripts need nonces, which would make every page dynamic. XSS risk is mitigated by React escaping, no `dangerouslySetInnerHTML`, and AI output rendered as text. | Medium | Open: add nonce-based CSP before general availability. |
| 2 | No MFA for owners/admins. | Medium | Open: planned post-pilot. |
| 3 | No error-tracking service; errors are visible only in logs. | Low | Open. |
| 4 | Django admin shares the API session login; the URL is configurable but not IP-restricted by the app. | Low | Mitigation: restrict `DJANGO_ADMIN_URL` at the proxy (deployment doc). |
| 5 | Audit events are append-only by convention (no update/delete API), not enforced at the database level. | Low | Open: consider DB-level revoke of UPDATE/DELETE for the app role. |
| 6 | Usage summary returned decimals as JSON numbers while the contract says strings, so the Usage page never loaded. Found during this review. | Bug (not security) | **Fixed** with a contract test. |
| 7 | Real Facebook/Instagram/TikTok and Anthropic integrations have not been exercised with real credentials. | — | Tracked in `docs/integrations/README.md`. |
| 8 | Dev-only lint tooling reports 5 high advisories (`braces` via `eslint-config-next` → `fast-glob` → `micromatch`). No patched `braces` release exists, and `npm audit fix --force` would downgrade `eslint-config-next` to 14.x. Exploiting it needs attacker-controlled glob patterns; ours come only from our lint config, and the package never ships. Install-time audit is off (`frontend/.npmrc`); audits run explicitly via `make audit` and CI. ESLint 10 was tried and reverted (plugins bundled with `eslint-config-next` don't support it yet). | Low | Accepted: re-check when `eslint-config-next` updates. |

## Out of scope for this review

Infrastructure configuration (network policies, managed-service settings, IAM), which
depends on the chosen hosting provider, and DDoS protection, which belongs at the edge.
