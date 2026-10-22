"""Evaluation harness for marketing plan generation.

Runs representative businesses from several industries through the real pipeline
(context assembly -> provider -> normalization -> claim checks) inside a transaction
that is rolled back, then applies automated quality checks. Human review of the
generated plans is still required for subjective quality.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.ai.providers.base import AIProviderError, StructuredRequest
from apps.ai.service import generate_structured
from apps.brand.models import BrandGuideline, TargetAudience
from apps.brand.services import build_business_context, get_profile
from apps.core.claims import collect_strings, find_claim_issues
from apps.organizations.services import create_organization

from ..prompts import PLAN_SYSTEM_PROMPT, build_plan_prompt
from ..schemas import MarketingPlanOutput
from ..services import normalize_plan

CASES_PATH = Path(__file__).with_name("plan_cases.json")
HORIZON = 4


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text())
    return cases


class _Rollback(Exception):
    pass


def run_case(case: dict[str, Any]) -> CaseResult:
    result = CaseResult(case_id=case["id"], passed=False)
    try:
        with transaction.atomic():
            user = User.objects.create_user(f"eval-{case['id']}@example.invalid", None)
            org = create_organization(user=user, name=case["business"]["name"])
            profile = get_profile(org)
            profile.industry = case["industry"]
            profile.description = case["business"]["description"]
            profile.location = case["business"].get("location", "")
            profile.languages = case["business"].get("languages", ["en"])
            profile.goals = case["goals"]
            profile.preferred_platforms = case["platforms"]
            profile.save()
            for a in case["audiences"]:
                TargetAudience.objects.create(
                    organization=org, name=a["name"], pain_points=a.get("pain_points", [])
                )
            BrandGuideline.objects.update_or_create(
                organization=org, defaults={"restricted_claims": case["restricted_claims"]}
            )
            context = build_business_context(org)
            generated = generate_structured(
                org,
                StructuredRequest(
                    operation="marketing_plan.eval",
                    system=PLAN_SYSTEM_PROMPT,
                    prompt=build_plan_prompt(context, horizon_weeks=HORIZON, instructions=""),
                    schema=MarketingPlanOutput,
                ),
            )
            raw_platforms = {a.platform for a in generated.output.channel_allocation} | {
                e.platform for e in generated.output.content_calendar
            }
            output, fixes = normalize_plan(
                generated.output, allowed_platforms=case["platforms"], horizon_weeks=HORIZON
            )
            plan = output.model_dump(mode="json")
            issues = find_claim_issues(collect_strings(plan), case["restricted_claims"])
            weeks = {e.week for e in output.content_calendar}
            result.provider, result.model, result.plan = generated.provider, generated.model, plan
            result.checks = {
                "schema_valid": True,
                "platforms_respected_by_model": raw_platforms <= set(case["platforms"]),
                "calendar_covers_horizon": weeks == set(range(1, HORIZON + 1)),
                "no_restricted_or_guarantee_claims": not issues,
                "assumptions_recorded": bool(output.assumptions),
                "caveats_present": bool(output.caveats),
                "has_objectives_and_themes": bool(output.objectives and output.content_themes),
            }
            result.notes = [f"{i.kind}: {i.phrase}" for i in issues] + [f["message"] for f in fixes]
            result.passed = all(result.checks.values())
            raise _Rollback
    except _Rollback:
        pass
    except AIProviderError as exc:
        result.notes.append(f"provider error {exc.code}: {exc}")
    return result
