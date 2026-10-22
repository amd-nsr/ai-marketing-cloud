# Architecture decision records

Short records of significant decisions: context, decision, consequences. Add a new
numbered file for each decision; supersede rather than rewrite accepted records.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-single-repo-separate-apps.md) | One repository, independently built frontend and backend | Accepted |
| [0002](0002-modular-monolith.md) | Modular monolith on Django/DRF + Celery; Next.js frontend | Accepted |
| [0003](0003-same-origin-api-proxy.md) | Browser talks to one origin; Next.js proxies `/api/*` to Django | Accepted |
| [0004](0004-custom-user-model.md) | Custom User model (UUID pk, email login) from the first migration | Accepted |
| [0005](0005-background-jobs.md) | Celery on Redis; durable state in PostgreSQL; single beat | Accepted |
| [0006](0006-api-conventions.md) | API versioning, error envelope, committed OpenAPI contract | Accepted |
| [0007](0007-tenancy-and-authorization.md) | Organization-in-URL tenancy, scoped base views, role matrix, session auth | Accepted |
| [0008](0008-media-storage.md) | Object storage, authorized delivery, content-based upload validation | Accepted |
| [0009](0009-ai-provider-layer.md) | Provider-independent AI contract, Anthropic + labelled mock, async runs, usage/cost | Accepted |
| [0010](0010-social-publishing.md) | Adapter contract, Facebook-first, encrypted tokens, reliable publishing jobs with reconciliation | Accepted |
| [0011](0011-analytics-recommendations.md) | Metric snapshots, missing ≠ zero, per-platform aggregates, rule-based recommendations | Accepted |
| [0012](0012-autonomy-policy-engine.md) | One policy engine for manual/semi/automatic, durable actions, re-evaluation on change | Accepted |
| [0013](0013-operational-hardening.md) | Heartbeat, stuck-work sweeper, operations overview, dependency audit | Accepted |
