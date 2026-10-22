# Operations runbook

Owners and admins see per-organization status on **Operations**
(`/o/<org>/operations`, API `GET /api/v1/orgs/<org>/operations/`). Platform operators use
the health endpoints and logs (`deployment.md`).

## Background processing is not running

*Signal:* `/health/background/` returns 503, or the Operations page says "Background
processing isn't running".
1. Check that exactly one beat process and at least one worker are running.
2. Check Redis reachability (`/health/ready/`).
3. Restart worker, then beat. Work queued while they were down is safe: scheduled posts
   are dispatched from the database, and AI runs still queued after 10 minutes are
   re-submitted.

## Posts stuck in "Checking outcome" (`needs_reconciliation`)

The platform call may or may not have succeeded. The reconciler looks the post up on the
platform every minute and never re-sends on its own (ADR 0010).
- If it stays for more than 1 hour, check the platform's status and the account's
  connection. Once the outcome is confirmed on the platform, an admin can retry
  (if it wasn't posted) or leave it.

## AI failures

| Code | Meaning | Action |
| --- | --- | --- |
| `ai_unavailable`, `ai_timeout`, `ai_rate_limited` | Provider problem | Users can retry. Check provider status if widespread. |
| `timed_out` | Run exceeded `AI_RUN_TIMEOUT_MINUTES`; the worker was killed or hung | Check worker memory and logs. Users can retry. |
| `never_started` | Queued for more than `AI_RUN_QUEUE_TIMEOUT_MINUTES` | Workers were down or saturated. Fix capacity, then retry. |
| `workflow_unavailable` | Worker runs older code than the web | Finish the deploy (restart the workers). |
| `quota_exceeded` | Organization's monthly AI limit | Raise it in Django admin (*Organization quotas*) if agreed. |

## Social account needs reconnection

Shown on Operations and Social accounts. Only the organization can reconnect (OAuth
consent). Scheduled posts to that account fail with a clear error until it's reconnected.

## Stop automation for an organization

Owners or admins: **Automation → Pause** holds automated scheduled posts and actions, and
**Cancel all pending** cancels them. Switching to **Manual** stops all automated work and
cancels unsent automated posts. Operators can set the same fields in Django admin.

## Rotate the social-token encryption key

1. Generate a new Fernet key and prepend it: `SOCIAL_TOKEN_ENCRYPTION_KEYS=new,old`.
2. Deploy. New writes use the new key; old tokens still decrypt.
3. Re-encrypt existing tokens:
   `python manage.py rotate_social_tokens`.
4. Remove the old key after the next successful backup.
