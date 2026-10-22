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
make deps      # start PostgreSQL (:15432) and Redis (:16379) in Docker
make migrate
```

Then in three terminals:

```bash
make backend   # Django API      → http://localhost:8000/api/v1/health/ready/
make worker    # Celery worker
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
| `make check` | Every lint, format check, type check, migration check, contract check, and test |
| `make test` | Backend and frontend tests only |
| `make format` | Auto-format both apps |
| `make migrations` | Create Django migrations |
| `make openapi` | Regenerate the committed OpenAPI contract |

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
| 5 | Content studio | **Done** (images only; no image generation) |
| 6 | Campaigns, calendar, approvals | **Done** |
| 7 | Social integration foundation + Facebook Pages | **Done in code** (real API unverified: no Meta app credentials) |
| 8 | Instagram + TikTok | **Done in code** (photo posts; real APIs unverified) |
| 9 | Analytics and recommendations | **Done** (real-platform metrics unverified) |
| 10 | Autonomy modes and policy engine | **Done** |
| 11 | Usage controls and operational hardening | **Done** |
| 12 | Pilot readiness (E2E, limitations, checklist) | **Done**, external setup pending ([checklist](docs/product/pilot-checklist.md)) |
