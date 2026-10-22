import pytest

from apps.marketing.evals.runner import load_cases, run_case
from apps.organizations.models import Organization

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_eval_pipeline_runs_for_every_industry_case(case):
    result = run_case(case)
    assert result.provider == "mock"
    assert result.passed, (result.checks, result.notes)
    # Evaluation never persists anything.
    assert not Organization.objects.filter(name=case["business"]["name"]).exists()


def test_cases_cover_multiple_industries():
    industries = {c["industry"] for c in load_cases()}
    assert len(industries) >= 5
