# 0002 — Modular monolith on Django/DRF + Celery; Next.js frontend

**Status:** Accepted (2026-10-19)

## Context
The MVP spans identity, onboarding, AI generation, content, publishing, analytics, and
automation. These domains share data heavily (organization, content, accounts) and need
transactional consistency. The team is small, and the product owner is experienced with
Django, PostgreSQL, Redis, and Celery.

## Decision
- One Django project with one app per domain under `backend/apps/`, added only when a
  phase needs it. Domain logic in service modules; views/serializers stay thin.
- Separate runtime processes from the same backend code: API (gunicorn), Celery worker,
  and (later) a single Celery beat.
- PostgreSQL as the system of record; Redis for broker/cache/short-lived coordination.
- Next.js (App Router, TypeScript) for the web app.
- No microservices, Kafka, or Kubernetes until a demonstrated need exists.

## Consequences
- Simple deployment and local development; cross-domain transactions are ordinary DB
  transactions.
- Module boundaries are enforced by convention and review, not by process isolation.
  Domain apps should depend on each other through service functions, not each other's
  internals, to keep later extraction possible.
