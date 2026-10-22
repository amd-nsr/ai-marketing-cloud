# 0011 — Analytics and evidence-based recommendations

**Status:** Accepted (2026-10-20)

## Decision
- **Snapshots, not counters.** Each collection stores one `MetricSnapshot` per metric per
  post with platform, source (`facebook`/`instagram`/`simulation`), period and
  `retrieved_at`. History is kept; reads use the latest snapshot per post and metric.
- **Missing is not zero.** A metric the platform didn't return is stored as NULL and shown
  as "Not reported"/"n/a"; overview tiles show coverage ("4 of 6 posts").
  Integrations without metrics are marked `unsupported` rather than faking values.
- **Per platform only.** Platforms define metrics differently (e.g. Facebook "views"
  vs Instagram "views"); totals and charts are never combined across platforms.
- **Collection cadence:** first collection ≥30 minutes after publishing, then every 6
  hours for 30 days (Celery beat every 15 minutes); users can refresh manually (10-minute
  cooldown per post). Revoked credentials during collection flag the account for reconnection.
- **Recommendations are deterministic rules, not LLM output**, so every claim is backed by
  stored numbers:
  - format performance: a format's median engagement ≥1.5× or ≤0.5× the platform median,
    requiring ≥6 posts with the metric and ≥3 in the format;
  - top post: ≥2× the platform median with ≥5 posts;
  - posting gap: active plan, nothing published in 14 days and nothing scheduled;
  - operational: accounts needing reconnection, approvals waiting >3 days, failed posts.
  Each stores observation, rationale, suggested action, stated uncertainty ("correlation,
  not cause"), evidence rows (value, baseline, sample size) and whether simulated data was
  involved. Deduplicated by fingerprint; dismissed items stay quiet for 30 days; untouched
  items whose condition no longer holds are removed. Regenerated every 6 hours.

## Consequences
- Recommendations stay silent with little data, which is intended.
- LLM-written insight summaries could be added later on top of these facts, never instead
  of them.
- Real-platform metric retrieval is unverified until app credentials exist; Facebook
  metric names follow the v26 docs (`post_impressions*` are deprecated).
