# AI Marketing Cloud

A multi-tenant SaaS platform that helps businesses plan, create, publish, measure, and
improve their marketing from one workspace.

> **Status: in active development.** See the roadmap table below for what is implemented.

## Repository layout

```
frontend/        Next.js + TypeScript web app (own package.json, tests, Dockerfile)
backend/         Django + DRF API and Celery workers (own pyproject.toml, tests, Dockerfile)
infrastructure/  Deployment and infrastructure configuration (added as needed)
docs/            Architecture, ADRs, API contract, security, development guides
.github/         CI workflows
docker-compose.yml   Local development stack
Makefile             Developer entry points (`make help`)
```

The frontend talks to the backend **only** over the documented HTTP API
([`docs/api/openapi.yaml`](docs/api/openapi.yaml)). The browser calls same-origin
`/api/*` paths, which Next.js proxies to Django
([ADR 0003](docs/decisions/0003-same-origin-api-proxy.md)).

## Quick start

Prerequisites: Docker with Compose v2, Python 3.13 + [uv](https://docs.astral.sh/uv/),
Node.js 22 + npm.

```bash
make setup     # install deps, create .env from .env.example
make dev       # run the whole project in one terminal
```

`make dev` starts PostgreSQL (:15432) and Redis (:16379) in Docker, applies migrations,
seeds the [demo users](#demo-users-local-development-only), then runs the Django API
(http://localhost:8000), Celery worker, Celery beat and the Next.js app
(http://localhost:3000) with labelled output. Ctrl+C stops them all;
PostgreSQL and Redis keep running until `make down`.

To run the processes in separate terminals instead (after `make deps` and `make migrate`):

```bash
make backend   # Django API      → http://localhost:8000/api/v1/health/ready/
make worker    # Celery worker
make beat      # Celery beat (scheduled posts, metrics, automation)
make frontend  # Next.js         → http://localhost:3000
```

Or run everything in containers with `make up`.

Open http://localhost:3000. The **System status** panel calls the API through the
proxy and shows PostgreSQL and Redis health.

Full instructions, troubleshooting, and production notes:
[docs/development/setup.md](docs/development/setup.md).

## Common commands

| Command | What it does |
| --- | --- |
| `make dev` | Run the whole project natively in one terminal |
| `make up` / `make down` | Run / stop the whole stack in Docker |
| `make seed` | Create the demo users and organization (safe to re-run) |
| `make check` | Every lint, format check, type check, migration check, contract check, and test |
| `make test` | Backend and frontend tests only |
| `make format` | Auto-format both apps |
| `make migrations` | Create Django migrations |
| `make openapi` | Regenerate the committed OpenAPI contract |
| `make e2e` | Playwright pilot journey against the running stack |
| `make audit` | Check dependencies for known vulnerabilities |

## Documentation

- [Architecture overview](docs/architecture/overview.md)
- [Architecture decision records](docs/decisions/)
- [Development setup](docs/development/setup.md) · [Dependency versions](docs/development/versions.md) · [E2E tests](docs/development/e2e.md)
- [Implementation checklist](docs/implementation-checklist.md)
- Pilot: [Known limitations](docs/product/known-limitations.md) · [Pilot checklist](docs/product/pilot-checklist.md)
- [Security baseline](docs/security/baseline.md) · [Security review](docs/security/review.md)
- Operations: [Deployment](docs/operations/deployment.md) · [Backup and restore](docs/operations/backup-restore.md) · [Runbook](docs/operations/runbook.md)
- [API contract](docs/api/openapi.yaml)

## Roadmap status

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repository and architecture foundation | **Done** |
| 1 | Authentication and multi-tenancy | **Done** (no email verification yet) |
| 2 | Business onboarding and brand context | **Done** |
| 3 | AI provider abstraction | **Done** (real provider not yet verified: no credentials) |
| 4 | Marketing strategy | **Done** (quality checked with mock; real-model eval pending credentials) |
| 5 | Content studio | **Done**, upgraded below |
| 6 | Campaigns, calendar, approvals | **Done** |
| 7 | Social integration foundation + Facebook Pages | **Done in code** (real API unverified: no Meta app credentials) |
| 8 | Instagram + TikTok | **Done in code** (photo posts; real APIs unverified) |
| 9 | Analytics and recommendations | **Done** (real-platform metrics unverified) |
| 10 | Autonomy modes and policy engine | **Done** |
| 11 | Usage controls and operational hardening | **Done** |
| 12 | Pilot readiness (E2E, limitations, checklist) | **Done**, external setup pending ([checklist](docs/product/pilot-checklist.md)) |
| + | Meta integration: Facebook Pages selection + Facebook Ads under spend limits ([ADR 0014](docs/decisions/0014-meta-integration-and-ads.md)) | **Done in code** (real Meta APIs unverified: no Meta app, App Review or business verification) |
| + | Content studio upgrade: writing assistant, design and carousel editor, media library, video projects with server rendering, campaign creatives, blog/email ([ADR 0015](docs/decisions/0015-content-studio-documents-and-rendering.md)) | **Done** (real AI text unverified; no real image-generation vendor; video/reel *publishing* not supported by the social adapters yet) |

## Demo users (local development only)

`make dev` creates these automatically (or run `make seed`). All belong to the
organization **Demo Coffee Roasters**, which is already onboarded, so each one lands on the
dashboard and sees the app as that role allows (see [roles](docs/security/roles.md)).

| Role | Email | Password |
| --- | --- | --- |
| Owner | `demo.owner@example.com` | `demo-local-only-passphrase` |
| Admin | `demo.admin@example.com` | `demo-local-only-passphrase` |
| Editor | `demo.editor@example.com` | `demo-local-only-passphrase` |
| Analyst | `demo.analyst@example.com` | `demo-local-only-passphrase` |
| Viewer | `demo.viewer@example.com` | `demo-local-only-passphrase` |

These are local test credentials, published on purpose. The seeder refuses to run unless
`DEBUG=True`, so they can't be created in production. Never reuse this password anywhere
real. AI output is the labelled mock unless `ANTHROPIC_API_KEY` is set. To try publishing,
add a **simulation** account under *Social accounts* (it never posts anywhere).
