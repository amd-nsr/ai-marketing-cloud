# Development setup

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Docker + Compose v2 | 24+ | Runs PostgreSQL and Redis (and optionally the whole stack) |
| Python | 3.13 | Managed per-project by uv |
| uv | 0.10+ | Backend dependency and virtualenv management |
| Node.js | 22 LTS | Frontend; `engines` requires `>=22` |
| npm | 10+ | Lockfile: `frontend/package-lock.json` |
| GNU Make | any | Optional convenience wrapper |
| ffmpeg + ffprobe | 4.3+ | Content studio: validates video/audio uploads and renders videos (worker). Without it, video features report "unavailable". `apt install ffmpeg fonts-dejavu-core` |

## Configuration

All configuration is environment-driven. Copy the template once:

```bash
cp .env.example .env
```

The repository-root `.env` is read by Django (`config/settings/base.py`), by Next.js
(`next.config.ts` via `@next/env`), and by Docker Compose. Real environment variables
always override `.env`. **Never commit `.env`.**

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | backend | Required. Production rejects short or placeholder keys. |
| `DJANGO_ALLOWED_HOSTS` | backend | Comma-separated. Required in production. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | backend | Production: the public frontend origin(s). |
| `DATABASE_URL` | backend | PostgreSQL URL. |
| `REDIS_URL` | backend | Cache and (by default) Celery broker. |
| `CELERY_BROKER_URL` | backend | Optional; defaults to `REDIS_URL`. |
| `LOG_LEVEL`, `LOG_FORMAT` | backend | `LOG_FORMAT=json` (production default) or `console`. |
| `BACKEND_INTERNAL_URL` | frontend | Where Next.js proxies `/api/*`. Default `http://localhost:8000`. |
| `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT` | compose | Host ports (default 15432 / 16379). |

Settings modules: `config.settings.development` (default for `manage.py`),
`config.settings.test` (pytest), `config.settings.production` (Docker production image).

## Option A — apps native, dependencies in Docker (recommended)

Fastest feedback loop; debuggers and hot reload work normally.

```bash
make setup        # uv sync + npm ci (+ creates .env)
make dev          # everything below, in one terminal (Ctrl+C stops all)
```

`make dev` (`scripts/dev.sh`) starts PostgreSQL and Redis, applies migrations, and runs the
API, worker, beat and frontend with labelled output. If any process exits, it stops the
rest. PostgreSQL and Redis keep running until `make down`.

Or run each process in its own terminal:

```bash
make deps         # docker compose up -d --wait postgres redis
make migrate
make backend      # terminal 1: http://localhost:8000
make worker       # terminal 2: Celery worker
make beat         # terminal 3: scheduler (scheduled publishing, retries, reconciliation)
make frontend     # terminal 4: http://localhost:3000
```

Create an admin user: `cd backend && uv run python manage.py createsuperuser`
(admin at http://localhost:8000/admin/).

## Option B — everything in Docker

```bash
make up           # docker compose up --build
```

Starts postgres, redis, backend (runs migrations, then runserver), worker, and frontend
with source bind-mounted for hot reload. Frontend: http://localhost:3000.

## Useful URLs (development)

| URL | What |
| --- | --- |
| http://localhost:3000 | Frontend |
| http://localhost:8000/api/v1/health/live/ | Liveness (no dependency checks) |
| http://localhost:8000/api/v1/health/ready/ | Readiness (PostgreSQL + Redis; 503 if either fails) |
| http://localhost:8000/api/v1/docs/ | Swagger UI (development only) |
| http://localhost:8000/api/v1/schema/ | OpenAPI schema (staff-only outside development) |

## Quality checks

```bash
make check            # everything CI runs, except image builds
make check-backend    # ruff format/lint, mypy --strict, migration check, OpenAPI check, pytest
make check-frontend   # prettier, eslint, tsc, vitest
```

Backend tests need PostgreSQL running (`make deps`); they use a real database so
constraints and migrations are exercised. One test, marked `integration`, pings the real
Redis at `REDIS_URL` and is **skipped** (not passed) if Redis is unreachable.

### API contract

`docs/api/openapi.yaml` is generated from the Django code and committed. After changing
an endpoint, run `make openapi` and commit the result; CI fails if it is stale.

## Troubleshooting

**`address already in use` when starting Docker services.** Another PostgreSQL/Redis
already uses the host port. Set `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` in `.env` and
update `DATABASE_URL` / `REDIS_URL` to match. If a container started without its port
after such an error, recreate it: `docker compose up -d --force-recreate <service>`.

**Frontend shows "API unreachable".** The Django server is not running, or
`BACKEND_INTERNAL_URL` points elsewhere. `curl localhost:8000/api/v1/health/live/`.

**Readiness reports `Degraded`.** A dependency is down: `docker compose ps`, then
`make deps`.

**`DisallowedHost` / 400 from Django.** The host Django was called with is not in
`DJANGO_ALLOWED_HOSTS`. Inside Compose the frontend calls `backend:8000`; this host is
already allowed in `docker-compose.yml`.

**Unknown `/api/...` URL shows an HTML page in development.** Expected: with
`DEBUG=True` Django shows its debug 404. With `DEBUG=False` (tests, production) the API
returns the JSON error envelope.

**`DJANGO_SECRET_KEY must be a strong, unique value in production`.** The production
settings refuse placeholder keys. Generate one:
`python -c "import secrets; print(secrets.token_urlsafe(50))"`.

**Reset the local database.** `docker compose down -v` deletes the Docker volumes
(**all local data**), then `make deps && make migrate`.

## Production deployment (current state)

Production deployment is **not yet set up**; the pieces that exist are:

- `backend/Dockerfile` target `production`: non-root, gunicorn, `config.settings.production`,
  static files collected at build time. The same image runs the worker with the command
  `celery -A config worker`.
- `frontend/Dockerfile` target `production`: Next.js standalone server, non-root.
  `BACKEND_INTERNAL_URL` is a **build argument** because rewrites are compiled into the
  build output.
- Production settings enforce HTTPS redirects (health endpoints exempt for internal
  probes), HSTS, secure cookies, and require `DJANGO_ALLOWED_HOSTS` and a strong secret key.

Still to decide and document (Phase 11): hosting platform, managed PostgreSQL/Redis,
secret injection, migrations-on-deploy strategy, object storage, static file serving
(e.g. WhiteNoise or CDN), backups and restore, monitoring.

## Background worker notes

Celery workers do **not** auto-reload. After changing backend code that runs in jobs
(AI workflows, publishing, video rendering), restart `make worker`. A worker running older code fails
unknown jobs visibly (`workflow_unavailable`) rather than leaving them stuck.

## Content studio notes

- **Image generation** is off unless `IMAGE_PROVIDER` is set. Development defaults to
  `mock` (labelled placeholder images); there is no real image vendor yet (ADR 0015).
- **Video rendering** runs in the Celery worker with ffmpeg (`FFMPEG_BINARY`,
  `FFPROBE_BINARY`, `VIDEO_FONT_FILE`, `VIDEO_RENDER_TIMEOUT_SECONDS`).
- **Uploads** of video/audio are limited by `MAX_MEDIA_UPLOAD_BYTES` (100 MB) and
  `MAX_MEDIA_DURATION_SECONDS`. Keep the frontend's `MAX_PROXY_BODY_SIZE` (default
  `105mb`) above the upload limit, or proxied uploads are silently truncated.
- **S3**: allow `GET` from the app origin in the bucket's CORS rules, so the design editor
  can export images that load through signed URLs.
