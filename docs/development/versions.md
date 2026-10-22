# Dependency versions

Selected 2026-10-19. Exact versions are pinned by `backend/uv.lock` and
`frontend/package-lock.json`; this page records the intent behind the choices.

## Runtime platforms

| Component | Version | Why |
| --- | --- | --- |
| Python | 3.13 | Current stable with broad wheel support across the stack. |
| Node.js | 22 LTS | Active LTS; matches the `node:22-alpine` image. |
| PostgreSQL | 18 (`postgres:18-alpine`) | Current major. |
| Redis | 8 (`redis:8-alpine`) | Current major. |

## Backend

| Package | Version | Notes |
| --- | --- | --- |
| Django | 6.1.x (pinned `<6.2`) | Current feature release. Plan: move to **6.2 LTS** (expected April 2027) once released; 6.1 security support ends around then. |
| djangorestframework | 3.18 | API layer. |
| drf-spectacular | 0.30 | OpenAPI 3 generation. |
| celery | 5.6 | Background jobs ([ADR 0005](../decisions/0005-background-jobs.md)). |
| redis (redis-py) | 8.1 | Broker/cache client and readiness check. |
| psycopg[binary] | 3.3 | PostgreSQL driver. Consider the source build (`psycopg[c]`) for production later. |
| django-environ | 0.14 | Environment-driven settings. |
| django-stubs-ext | — | Runtime support for generic Django classes used for typing. |
| gunicorn | 26 | Production WSGI server. |
| Dev: pytest 9 + pytest-django, ruff 0.17, mypy 2.4 (strict) + django-stubs 6.1 + djangorestframework-stubs | | |

## Frontend

| Package | Version | Notes |
| --- | --- | --- |
| next | 16.4 | App Router, Turbopack, Cache Components enabled (scaffold default). |
| react / react-dom | 19.3 | |
| typescript | 5.9 | TypeScript 7 (native port) is out but `create-next-app` still selects 5.x; revisit when Next.js officially supports 7. |
| tailwindcss | 4.3 | Design tokens in `src/styles/globals.css`. |
| zod | 4.6 | Runtime validation of API responses (and forms, from Phase 1). |
| vitest | 5.0 + Testing Library | Unit/component tests (jsdom). |
| @playwright/test | 1.64 | End-to-end pilot journey (`frontend/e2e/`). |
| eslint 9 + eslint-config-next, prettier 3 | | |

**Not added yet, deliberately:** a component library (shadcn/ui or similar; decide in
Phase 1 when forms and dialogs arrive), Playwright (added with the first real user flow
in Phase 1), OpenAPI→TypeScript type generation (added when the API has more than
health endpoints), django-cors-headers (not needed; see ADR 0003).
