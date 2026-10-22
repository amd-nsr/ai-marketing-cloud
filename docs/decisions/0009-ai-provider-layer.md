# 0009 — Provider-independent AI layer

**Status:** Accepted (2026-10-19)

## Context
Marketing features need structured AI output (plans, content variants) with predictable
cost and failure behaviour. The provider must be replaceable without touching business
logic, and tests must not depend on a paid external API.

## Decision
- **Contract** (`apps/ai/providers/base.py`): `StructuredRequest(operation, system, prompt,
  schema: PydanticModel, max_tokens, effort)` → `StructuredResult(output, provider, model,
  usage, latency, request_id, served_by_fallback, is_mock)`. Errors are normalized into
  `AIProviderError` subclasses with a `retryable` flag and a safe `user_message`.
  Providers declare `capabilities`; unsupported operations fail with `UnsupportedCapability`.
- **Business code calls only `apps.ai.service.generate_structured()`**, which enforces
  per-organization monthly quotas (requests and estimated cost), retries invalid/truncated
  output once (transport retries — 408/409/429/5xx/connection — are done by the vendor SDK
  with backoff; non-retryable errors such as auth or bad requests are never retried), and
  writes an `AIUsageRecord` for every attempt, successful or not.
- **Long-running generation is asynchronous:** `start_workflow()` persists an
  `AIWorkflowRun` (queued → running → succeeded/failed) and enqueues a Celery task; the
  API returns the run ID and clients poll `/orgs/<id>/ai/runs/<run_id>/`. Execution is
  idempotent (only `queued` runs execute; row-locked).
- **Initial provider: Anthropic (Claude)**, model `claude-opus-5` by default (`AI_MODEL`),
  via the official SDK's `beta.messages.parse()` with the Pydantic schema as
  `output_format` (schema-validated output). Server-side refusal fallback
  (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) is **enabled by
  default** (`AI_USE_REFUSAL_FALLBACK`): a request declined by Claude Opus 5's safety
  classifiers is re-run on Anthropic's recommended model for that category within the
  same call; such results are flagged `served_by_fallback` and recorded with the model
  that actually served them. Same vendor and data-handling terms; no silent switch to a
  different provider.
- **Mock provider** for tests and keyless local development: deterministic, flagged
  `is_mock` on every run/usage record, labelled in the UI, never contacts a network, and
  refused by production settings unless `AI_ALLOW_MOCK_IN_PRODUCTION=true`. Development
  defaults to it only when no `ANTHROPIC_API_KEY` is configured.
- **Costs** are estimates from configured list prices (`AI_MODEL_PRICING`), always
  labelled as estimates; never presented as invoice amounts.
- **Prompt-injection posture:** business context and any user/external text are passed
  as delimited data with an explicit instruction that it is not instructions; AI output
  is schema-validated and never executed; consequential actions go through the
  automation policy engine (Phase 10), not directly from model output.
- **No orchestration framework** (LangGraph etc.) yet: workflows are plain functions with
  explicit steps. Revisit when a workflow needs branching/persistent multi-step state.

## Adding a second provider
1. Implement a class with `name`, `model`, `capabilities`, `is_mock=False`, and
   `generate_structured(request)` in `apps/ai/providers/<vendor>_provider.py`, mapping the
   vendor's errors onto the normalized error classes.
2. Add a branch in `providers/registry.py` and its settings (key, model, timeouts).
3. Add its models to `AI_MODEL_PRICING`.
4. Add adapter tests with the vendor SDK stubbed (see `apps/ai/tests/test_ai_service.py`).
5. Review its data-handling terms before enabling; switching is an explicit
   configuration change, never an automatic fallback.

No marketing/content code changes: they depend only on the contract and their schemas.

## Consequences / limitations
- Real-provider behaviour is verified only by operator-run `manage.py ai_smoke_test`
  (a billed call) — not in CI. As of Phase 3 no real provider call has been made from this
  environment (no credentials configured).
- Per-organization provider configuration (`AIProviderConfiguration`) is not built; the
  provider is environment-wide.
- Stuck `running` runs (worker crash mid-call) need a periodic sweeper (Phase 11).
