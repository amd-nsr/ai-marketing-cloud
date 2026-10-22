# Deployment

How to run AI Marketing Cloud in production. **Status:** the production images build in
CI and the production settings are tested; no real production deployment has been done
yet. Treat this as the reference for the pilot environment.

## Topology

| Process | Image / command | Replicas | Notes |
| --- | --- | --- | --- |
| web (API) | backend `production` target, default `gunicorn` command | 2+ | Stateless. Behind the TLS-terminating proxy. |
| worker | backend image, `celery -A config worker --loglevel=INFO` | 1+ | Runs AI workflows, publishing, metrics, automation. |
| beat | backend image, `celery -A config beat --loglevel=INFO` | **exactly 1** | Two schedulers would double every periodic task. |
| frontend | frontend `production` target (`node server.js`) | 2+ | Proxies `/api/*` to `BACKEND_INTERNAL_URL`. |
| PostgreSQL 18 | managed service | — | Source of truth, including all job and workflow state. |
| Redis 8 | managed service | — | Broker, cache, heartbeat. Losing it loses no business data (see below). |
| Object storage | S3-compatible bucket | — | Uploaded media (`STORAGE_BACKEND=s3`). |

Only the frontend is public. The browser talks to one origin, and the frontend proxies
the API (ADR 0003), so no CORS is needed. The Django admin is at `DJANGO_ADMIN_URL`
(set it to a non-default path) and should be restricted at the proxy.

## Required configuration

Production settings refuse to start without these (`config/settings/production.py`):

| Variable | Notes |
| --- | --- |
| `DJANGO_SETTINGS_MODULE=config.settings.production` | Set in the image. |
| `DJANGO_SECRET_KEY` | 50+ random characters. |
| `DJANGO_ALLOWED_HOSTS` | The API host(s) seen by Django (including the internal name the frontend uses). |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | The public frontend origin, e.g. `https://app.example.com`. |
| `SOCIAL_TOKEN_ENCRYPTION_KEYS` | Comma-separated Fernet keys; the first encrypts. **Back these up separately from the database** (see backup doc). |
| `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` | `mock` is refused in production. |
| `DATABASE_URL`, `REDIS_URL` | Managed services; use TLS URLs (`rediss://`) where offered. |
| `FRONTEND_URL` | Used in emails and OAuth redirects. |
| `EMAIL_URL`, `DEFAULT_FROM_EMAIL` | Transactional email (invitations, password reset). |
| `STORAGE_BACKEND=s3` + `S3_*` | Private bucket; files are served through signed URLs. |
| `NUM_PROXIES` | Number of trusted proxies in front of Django (for client IPs in throttling and audit). |

Platform apps (`META_*`, `TIKTOK_*`) are needed only for real social accounts. Leave
`SOCIAL_MOCK_ENABLED` unset in production so simulation accounts can't be created.
Default usage limits (`LIMIT_*`) and operational thresholds (`AI_RUN_*`,
`AUTOMATION_ACTION_STUCK_MINUTES`, `OPERATIONS_HEARTBEAT_STALE_SECONDS`) have safe
defaults. `.env.example` lists every variable.

## Release procedure

1. CI on `main` must be green, including the dependency audit and the production image builds.
2. Build and tag both images from the same commit.
3. **Back up the database** (see `backup-restore.md`).
4. Run migrations once, from a one-off backend container:
   `python manage.py migrate --noinput`. Migrations are written to be backward compatible
   with the previous release where possible. If one isn't, note it in the release notes
   and stop the workers first.
5. Roll out web and frontend. Readiness: `GET /api/v1/health/ready/` (database + Redis).
6. Restart worker and beat. Tasks are idempotent and use late acknowledgement, so a task
   interrupted by the restart is redelivered or picked up by the sweeper.
7. Check `GET /api/v1/health/background/` returns `ok` within two minutes, and that the
   Operations page shows no new failures.

## Health endpoints

| Endpoint | Use | Fails when |
| --- | --- | --- |
| `/api/v1/health/live/` | Liveness probe (web) | The process can't serve requests. |
| `/api/v1/health/ready/` | Readiness probe (web) | Database or Redis unreachable. |
| `/api/v1/health/background/` | External uptime monitor (alert, don't restart web) | No worker heartbeat for 3 minutes: beat, broker or all workers are down. |

None of them expose secrets or tenant data.

## Logs and monitoring

All processes log JSON to stdout with `request_id`. Ship stdout to the log platform and
alert on:

- `/health/background/` non-200 for more than 5 minutes;
- log records with `level=ERROR`;
- publishing jobs in `needs_reconciliation` for more than 1 hour, AI `timed_out` or
  `never_started` failures (visible per organization on the Operations page, and in logs
  as `Swept AI run`).

Error-tracking (e.g. Sentry) is not integrated yet; see `docs/product/known-limitations.md`.
