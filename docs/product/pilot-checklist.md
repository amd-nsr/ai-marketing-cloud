# Pilot readiness checklist

Tick each item before inviting the first pilot customer. "Done" items were completed in
the build; unchecked items need real accounts, credentials or infrastructure.

## Built and verified in development
- [x] Full journey works through the UI with the mock AI and simulation accounts
      (Playwright `e2e/pilot-journey.spec.ts`, dev server and production build).
- [x] Tenant isolation: every org-scoped route returns 404 to non-members (automated sweep).
- [x] Roles and permissions enforced server-side; manual mode is the default.
- [x] Publishing is idempotent; uncertain outcomes are reconciled, never re-sent.
- [x] Stuck work is resolved by the sweeper; background liveness is monitored.
- [x] Usage limits (AI requests/cost, publishes/day, storage) are enforced and visible.
- [x] Backup → restore drill (local), including token decryption.
- [x] Dependency audit clean for production dependencies.

## Before the pilot (needs external setup)
- [ ] Production environment provisioned per `docs/operations/deployment.md`
      (managed Postgres with PITR, Redis, private S3 bucket, secrets manager, TLS).
- [ ] `DJANGO_ADMIN_URL` set to a non-default path and restricted at the proxy.
- [ ] Anthropic API key configured; run the AI quality checks in `docs/product/ai-quality.md`
      on 10+ real briefs; review cost per workflow on the Usage page.
- [ ] Meta app created; Facebook Page connected and a real post published and verified
      (`docs/integrations/README.md`, step 6). Submit App Review if the pilot customer's page
      isn't on the app's roles.
- [ ] Transactional email provider configured; invitation and password-reset emails received.
- [ ] Restore drill repeated against the managed database; RPO/RTO confirmed.
- [ ] Uptime monitor on `/api/v1/health/ready/` and `/api/v1/health/background/`; log alerts
      as listed in the deployment doc.
- [ ] CI green on GitHub, including `e2e` and `dependency-audit`.
- [ ] Pilot organization's limits set in Django admin (AI cost/month, publishes/day).
- [ ] Pilot customer briefed on known limitations (`known-limitations.md`), and that
      automation starts in **manual** mode.

## During the pilot
- [ ] Weekly review of the Operations page per organization (failures, reconnections).
- [ ] Weekly review of AI cost against the limit; adjust limits if needed.
- [ ] Collect feedback on AI output quality and edits per draft (version history shows
      how much people change).
- [ ] Only enable semi-automatic or automatic mode after the customer has approved several
      posts manually and asked for it.
