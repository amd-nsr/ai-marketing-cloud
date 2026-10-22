# AI output quality: how it is checked

## Marketing plans (Phase 4)

**Automatic, on every generated or edited plan** (`apps/marketing/services.py`):
- Output must validate against `MarketingPlanOutput` (provider-side structured output +
  Pydantic validation); invalid/truncated output is retried once, then fails visibly.
- Platforms not selected by the business are removed; calendar entries outside the plan
  horizon are removed; channel shares are normalized to 100%. Each fix is recorded as a
  quality warning shown in the UI.
- Text is scanned for the organization's restricted claims and for guarantee/superlative
  language ("guaranteed", "risk-free", "#1", "best in the world"); matches are shown as
  "Review before using" warnings. They are not silently rewritten.
- Every assumption and audience insight carries a basis: `user_provided`,
  `industry_guidance`, or `ai_assumption`, displayed as badges.

**Evaluation set** (`apps/marketing/evals/plan_cases.json`): six businesses across
restaurant, real estate, fitness, professional services, e-commerce, and hospitality
(including an Arabic/English business), each with tempting restricted claims.

```bash
cd backend && uv run python manage.py eval_marketing_plans --out /tmp/plan-eval.json
```

Automated checks per case: schema valid, the model respected platform choices without
correction, the calendar covers the horizon, no restricted/guarantee language, assumptions
recorded, caveats present, objectives and themes present.

**Status:** CI runs the pipeline against the mock provider (exercises plumbing only, not
AI quality). Running against a real model needs `ANTHROPIC_API_KEY` and makes one billed
request per case; it has **not** been run yet. Subjective quality (is the plan actually
good for this business?) needs human review of the `--out` file.
