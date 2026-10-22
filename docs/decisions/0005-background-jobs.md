# 0005 — Celery on Redis; durable state in PostgreSQL; single beat

**Status:** Accepted (2026-10-19)

## Context
AI generation, publishing, scheduling, sync, and analytics collection must run outside
the request cycle, be retryable, and never double-publish.

## Decision
- Celery with Redis as broker. Worker and beat run from the backend image with
  different commands.
- **No Celery result backend.** Job outcomes that matter (publishing jobs, AI workflow
  runs, automation actions) are domain records in PostgreSQL with explicit statuses;
  APIs return a resource ID and a status endpoint.
- Defaults: `acks_late`, `reject_on_worker_lost`, prefetch 1, hard/soft time limits
  (300s/270s). Tasks must therefore be **idempotent**: a task may run more than once.
- **Exactly one Celery beat instance** per environment. Not deployed until the first
  periodic task exists. Scheduled publishing will be driven by DB rows (a periodic task
  picks due jobs with row locking), not by long-ETA Celery messages, so schedules survive
  broker loss and can be cancelled.
- Workers use Django's `LOGGING` (via the `setup_logging` signal) so job logs match API
  logs.

## Consequences
- Redis loss can drop queued messages but not business state; a reconciliation sweep
  (Phase 7) re-enqueues work whose DB state says it is pending.
- Tests run tasks eagerly (`CELERY_TASK_ALWAYS_EAGER`); worker behaviour is verified
  manually or in integration environments.
