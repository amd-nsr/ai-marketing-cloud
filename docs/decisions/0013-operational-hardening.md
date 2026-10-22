# 0013 — Operational hardening: heartbeat, sweeper, operations overview

**Status:** Accepted (2026-10-20)

## Context
Every long-running thing (publishing jobs, AI runs, automation actions) is a database row
with a status. Workers can die mid-task, brokers can lose messages, and beat can stop. The
user must never see something "running" forever, and operators must know when background
processing is down.

## Decision
- **Heartbeat.** Beat enqueues `operations.heartbeat` every minute and a worker writes
  the time to the cache. `GET /api/v1/health/background/` is 200 when the last heartbeat
  is under 3 minutes old, else 503. It is separate from readiness, so a broken worker
  doesn't take the API out of rotation.
- **Sweeper** (`operations.sweep`, every 5 minutes) resolves stuck work from facts:
  - AI run queued more than 10 minutes → re-submitted (execution is idempotent);
  - queued more than 60 minutes → failed `never_started`;
  - running more than 20 minutes → failed `timed_out`. Celery soft and hard time limits
    sit just below this. A late real result still wins over the timeout; a late failure
    doesn't overwrite it.
  - Automation actions stuck in `executing` → succeeded if their publishing job exists
    (idempotency key), else failed as interrupted.
  - Publishing jobs are **not** swept here. The publishing engine already moves them to
    `needs_reconciliation`, and they are never re-sent blindly (ADR 0010).
- **Operations overview** (`GET /orgs/<id>/operations/`, owner/admin): background status,
  live and recent counts, recent failures with error codes (and simulation flags),
  automation queue, accounts needing reconnection, metrics-collection outcomes.
- **Usage** adds publishes in the last 24 hours against the daily limit, plus AI requests
  and cost by operation. Decimal amounts are strings in the API.
- **Supply chain:** `pip-audit` and `npm audit` in CI (`make audit` locally).
- **Isolation guard:** a test enumerates every org-scoped route and asserts that a
  non-member gets 404 for every method, so new endpoints are covered automatically.

## Consequences
- An operator needs only three probes plus logs to know the system is healthy.
- Thresholds are settings (`AI_RUN_*`, `AUTOMATION_ACTION_STUCK_MINUTES`,
  `OPERATIONS_HEARTBEAT_STALE_SECONDS`).
- No cross-organization (platform-operator) dashboard yet; operators use logs and Django admin.
