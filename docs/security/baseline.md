# Security baseline (Phase 0)

What is in place **and how it was verified**. The Phase 11 review is in `review.md`.

| Control | Where | Verified by |
| --- | --- | --- |
| Production refuses weak/placeholder `DJANGO_SECRET_KEY` and empty `ALLOWED_HOSTS` | `config/settings/production.py` | `tests/test_production_settings.py`; manual run of production image |
| HTTPS redirect, HSTS (30 days, subdomains), secure + HttpOnly session cookie, secure CSRF cookie, `X-Frame-Options: DENY`, `nosniff` | production settings | Manual: production image behind simulated `X-Forwarded-Proto` |
| Host header validation | Django `ALLOWED_HOSTS` | Manual: foreign `Host` → 400 |
| No stack traces/messages leak in API errors | `apps/core/exceptions.py` | `tests/test_api_errors.py` |
| Health responses expose only check names, latency, exception class | `apps/core/health.py` | `tests/test_health.py` |
| Authenticated-by-default API | DRF `DEFAULT_PERMISSION_CLASSES` | `tests/test_api_errors.py` |
| OpenAPI schema not public; Swagger UI only in development | settings, `config/urls.py` | `tests/test_schema.py`; manual on production image |
| Request ID header sanitised (no header/log injection) | `apps/core/middleware.py` | `tests/test_request_id.py` |
| Password policy: min length 12 + Django validators | `AUTH_PASSWORD_VALIDATORS` | Configured only (no signup flow yet) |
| Containers run as non-root | both Dockerfiles | Manual `id -un` in production images |
| Secrets not committed | `.gitignore`, `.env.example` placeholders | Review |
| No CORS surface | ADR 0003 | No CORS middleware installed |

## Known gaps (to address in the named phase)
- Authentication, CSRF flow, rate limiting, account recovery — Phase 1.
- Tenant isolation and cross-tenant tests — Phase 1.
- File upload validation and object-storage access control — Phase 2.
- Integration credential encryption at rest — Phase 7.
- Dependency vulnerability scanning in CI, frontend security headers, backups — done in
  Phase 11; see `docs/security/review.md` for the review and open findings.
- `DisallowedHost` events log at ERROR with a traceback; consider rate-limited logging
  if host-header scanning gets noisy in production.
