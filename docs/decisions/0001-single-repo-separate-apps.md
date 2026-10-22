# 0001 — One repository, independently built frontend and backend

**Status:** Accepted (2026-10-19)

## Context
The product has a Next.js frontend and a Django backend developed by a small team.
Splitting repositories early adds coordination overhead (versioning, cross-repo PRs)
without a team-boundary reason. The apps must still be deployable independently.

## Decision
- One Git repository with top-level `frontend/`, `backend/`, `infrastructure/`, `docs/`.
- Each app owns its dependencies (`package.json` / `pyproject.toml` + lockfile), tests,
  configuration, and **its own Dockerfile inside its directory**, so each build context
  is self-contained. `infrastructure/` holds deployment configuration only.
- No shared code package. The contract between apps is the HTTP API, documented in the
  committed `docs/api/openapi.yaml`.
- A root `docker-compose.yml` and `Makefile` orchestrate local development only.

## Consequences
- Atomic changes across API and UI in one PR; CI runs per-app jobs.
- The frontend cannot import backend code; contract drift is caught by the OpenAPI
  check (and, later, generated TypeScript types).
