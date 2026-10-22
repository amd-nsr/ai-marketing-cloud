# Architecture overview

A **modular monolith** with independently runnable processes. One repository, two
applications, four runtime process types.

```
Browser
  │  HTTPS, same origin
  ▼
Next.js server (frontend/)  ── pages, UI
  │  /api/* rewritten (proxied) to Django
  ▼
Django + DRF API (backend/, gunicorn)
  │                         │
  ▼                         ▼
PostgreSQL            Redis ── Celery broker / cache
                            │
                            ▼
               Celery worker(s) (backend/, same image)
               Celery beat (single instance, added with first periodic task)
```

| Process | Code | Scales | Notes |
| --- | --- | --- | --- |
| frontend | `frontend/` | horizontally | Stateless. Never holds AI or social-platform secrets. |
| api | `backend/` (gunicorn) | horizontally | Stateless; sessions in PostgreSQL. |
| worker | `backend/` (celery worker) | horizontally | Long-running and retryable work. |
| beat | `backend/` (celery beat) | **exactly one** | Not deployed yet; see ADR 0005. |

## Backend structure

```
backend/
  config/            settings (base/development/test/production), urls, celery app
  apps/
    core/            cross-cutting: health checks, error envelope, request IDs, JSON logging
    accounts/        custom User model (email login, UUID pk)
    <domain>/        added per phase: organizations, brand, marketing, content, social, ...
  tests/             cross-app and API tests (app-specific tests live in apps/<app>/tests)
```

Rules (from the engineering brief, enforced in review):

- Business logic lives in domain **service** modules, not views or serializers.
- External integrations (AI providers, social platforms, storage) sit behind adapters.
- Every tenant-scoped record carries its organization; every tenant-scoped query is
  filtered by an organization the caller has been authorized for (Phase 1).
- Long-running/retryable work runs in Celery; durable state lives in PostgreSQL, not in
  Celery result storage.
- Consequential workflows use explicit status fields and state transitions.

## Frontend structure

```
frontend/src/
  app/                    routes (App Router)
  components/ui/          design-system primitives (Button, Badge, ...)
  components/features/    feature components (system-status, ...)
  lib/api/                typed API client + per-resource modules (zod-validated)
  lib/                    utilities
  styles/globals.css      design tokens (light/dark)
frontend/tests/           vitest + Testing Library
```

The browser calls relative `/api/...` URLs; server-side code calls
`BACKEND_INTERNAL_URL` directly. Every API response is validated with zod before use;
backend errors arrive in one envelope and are surfaced as `ApiError`.

## Cross-cutting conventions

- **API:** versioned under `/api/v1/`, trailing slashes, JSON only in production,
  page-number pagination (25), authenticated by default. See ADR 0006.
- **Errors:** `{"error": {"code", "message", "details", "request_id"}}` for every error,
  including unknown URLs and unhandled exceptions (no stack traces or messages leak).
- **Request IDs:** `X-Request-ID` accepted (if safe) or generated, returned on every
  response, and attached to every log line.
- **Logging:** JSON lines in production, console format in development; Celery uses the
  same logging configuration as the API.
- **Health:** `/api/v1/health/live/` (process up) and `/api/v1/health/ready/`
  (PostgreSQL + Redis reachable; 503 otherwise). Both unauthenticated; responses carry
  only check names, latencies, and exception class names.

## Decisions

See [`docs/decisions/`](../decisions/).
