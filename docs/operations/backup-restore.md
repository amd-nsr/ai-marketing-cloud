# Backup and restore

## What must be backed up

| Data | Where | Backup |
| --- | --- | --- |
| All business data: organizations, content, approvals, jobs, audit log, metrics | PostgreSQL | Managed-service point-in-time recovery (PITR), **plus** a daily logical dump kept 30 days. |
| Uploaded media | S3 bucket | Bucket versioning + lifecycle retention (30 days of non-current versions). |
| `SOCIAL_TOKEN_ENCRYPTION_KEYS`, `DJANGO_SECRET_KEY` | Secret manager | Stored separately from database backups. Without the token keys, restored social tokens are unreadable and every account must be reconnected. |
| Redis | — | **Not backed up.** It holds the Celery queue, cache and heartbeat only. Every job and workflow is a database row, and the periodic tasks and sweeper re-dispatch work that was queued but lost. |

## Logical backup

```bash
pg_dump "$DATABASE_URL" --format=custom --no-owner --file "amc-$(date -u +%Y%m%dT%H%MZ).dump"
```

Store dumps encrypted in a separate account or bucket from production.

## Restore

1. Stop beat and the workers so nothing publishes while data is being restored.
2. Restore into a **new** database:
   ```bash
   createdb "$NEW_DB"
   pg_restore --dbname "$NEW_DB" --no-owner --exit-on-error amc-YYYYMMDDTHHMMZ.dump
   ```
3. Point a one-off backend container at it and check:
   `python manage.py migrate --check`, and that a connected social account's token
   decrypts (`SocialAccount.objects.first().access_token is not None` in `manage.py shell`).
4. Switch `DATABASE_URL`, start web, then worker and beat.
5. Review the Operations page. Posts that were `publishing` or `needs_reconciliation` at
   backup time are reconciled against the platform, never blindly re-sent (ADR 0010).
   Check scheduled posts whose time passed during the outage before resuming automation.

## Drill record

| Date | Environment | Result |
| --- | --- | --- |
| 2026-10-20 | Local Compose PostgreSQL 18 | `pg_dump -Fc` → `pg_restore` into a fresh database. Row counts matched (content, jobs, accounts, migrations), `migrate --check` clean, social token decrypted with the configured key. |

Run the drill against the real managed service before the pilot starts, and quarterly after.
Recovery objectives for the pilot: RPO ≤ 24h (logical dumps) or ≤ 5 min (PITR); RTO ≤ 4h.
