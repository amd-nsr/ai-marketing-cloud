from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from apps.ai import service, workflows
from apps.ai.models import AIUsageRecord, AIWorkflowRun
from apps.ai.pricing import estimate_cost
from apps.ai.providers import anthropic_provider as ap
from apps.ai.providers.base import (
    ProviderAuthError,
    ProviderBadRequest,
    ProviderOutputInvalid,
    ProviderRateLimited,
    ProviderRefused,
    ProviderTimeout,
    ProviderUnavailable,
    StructuredRequest,
    Usage,
)
from apps.ai.providers.mock import MockProvider, register_mock_fixture
from apps.core.errors import QuotaExceeded

pytestmark = pytest.mark.django_db


class Greeting(BaseModel):
    text: str


register_mock_fixture(Greeting, lambda req: Greeting(text=f"Hello from mock ({req.operation})"))
REQ = StructuredRequest(operation="test.greet", system="sys", prompt="Say hi", schema=Greeting)


@pytest.fixture(autouse=True)
def _reset_mock():
    MockProvider.next_error = None
    yield
    MockProvider.next_error = None


def test_generate_structured_records_usage(make_org):
    org = make_org()
    result = service.generate_structured(org, REQ)
    assert result.output.text.startswith("Hello from mock")
    assert result.is_mock
    record = AIUsageRecord.objects.get()
    assert (record.provider, record.model, record.operation) == ("mock", "mock-1", "test.greet")
    assert record.success and record.is_mock and record.input_tokens > 0
    assert record.estimated_cost == 0


def test_invalid_output_retried_once_then_fails(make_org):
    org = make_org()
    MockProvider.next_error = ProviderOutputInvalid("bad json")
    assert service.generate_structured(org, REQ).output  # second attempt succeeds
    assert AIUsageRecord.objects.filter(success=False, error_code="ai_invalid_output").count() == 1

    class AlwaysInvalid(MockProvider):
        def generate_structured(self, request):
            raise ProviderOutputInvalid("bad")

    from apps.ai.providers import registry

    registry.get_provider.cache_clear()
    original = registry.get_provider
    service.get_provider = lambda: AlwaysInvalid()
    try:
        with pytest.raises(ProviderOutputInvalid):
            service.generate_structured(org, REQ)
    finally:
        service.get_provider = original
    assert AIUsageRecord.objects.filter(success=False).count() == 3  # 1 + 2 attempts


def test_non_retryable_error_is_not_retried(make_org):
    org = make_org()
    MockProvider.next_error = ProviderAuthError("bad key")
    with pytest.raises(ProviderAuthError):
        service.generate_structured(org, REQ)
    assert AIUsageRecord.objects.count() == 1


def test_monthly_request_quota(make_org, settings):
    org = make_org()
    settings.USAGE_DEFAULT_LIMITS = {**settings.USAGE_DEFAULT_LIMITS, "ai_requests_per_month": 2}
    service.generate_structured(org, REQ)
    service.generate_structured(org, REQ)
    with pytest.raises(QuotaExceeded):
        service.generate_structured(org, REQ)


def test_per_org_quota_override(make_org, settings):
    from apps.usage.models import OrganizationQuota

    org = make_org()
    settings.USAGE_DEFAULT_LIMITS = {**settings.USAGE_DEFAULT_LIMITS, "ai_requests_per_month": 1}
    OrganizationQuota.objects.create(organization=org, ai_requests_per_month=5)
    org.refresh_from_db()
    for _ in range(3):
        service.generate_structured(org, REQ)


def test_cost_estimate_uses_configured_prices():
    cost = estimate_cost(
        "claude-opus-5",
        Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000),
    )
    assert cost == Decimal("8.000000")  # 5 + 2.5 + 0.5
    assert estimate_cost("unknown-model", Usage(input_tokens=10)) == 0


# --- Anthropic adapter (SDK stubbed; no network) ---------------------------------


def _response(**overrides):
    base = {
        "stop_reason": "end_turn",
        "parsed_output": Greeting(text="hi"),
        "model": "claude-opus-5",
        "usage": SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            iterations=None,
        ),
        "_request_id": "req_123",
        "stop_details": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _provider(monkeypatch, respond):
    provider = ap.AnthropicProvider(
        model="claude-opus-5", api_key="test-key", timeout_seconds=5, max_retries=0
    )
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return respond()

    monkeypatch.setattr(provider._client.beta.messages, "parse", parse)
    return provider, calls


def test_anthropic_request_shape_includes_schema_and_fallback(monkeypatch):
    provider, calls = _provider(monkeypatch, _response)
    result = provider.generate_structured(REQ)
    assert result.output.text == "hi" and result.request_id == "req_123" and not result.is_mock
    sent = calls[0]
    assert sent["model"] == "claude-opus-5"
    assert sent["output_format"] is Greeting
    assert sent["fallbacks"] == "default"
    assert sent["betas"] == [ap.FALLBACK_BETA]
    assert sent["messages"] == [{"role": "user", "content": "Say hi"}]


def test_anthropic_reports_fallback_service(monkeypatch):
    usage = SimpleNamespace(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        iterations=[SimpleNamespace(type="message"), SimpleNamespace(type="fallback_message")],
    )
    provider, _ = _provider(monkeypatch, lambda: _response(usage=usage, model="claude-opus-4-8"))
    result = provider.generate_structured(REQ)
    assert result.served_by_fallback and result.model == "claude-opus-4-8"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        (
            {
                "stop_reason": "refusal",
                "parsed_output": None,
                "stop_details": SimpleNamespace(category="cyber"),
            },
            ProviderRefused,
        ),
        ({"stop_reason": "max_tokens"}, ProviderOutputInvalid),
        ({"parsed_output": None}, ProviderOutputInvalid),
    ],
)
def test_anthropic_stop_reasons(monkeypatch, overrides, error):
    provider, _ = _provider(monkeypatch, lambda: _response(**overrides))
    with pytest.raises(error):
        provider.generate_structured(REQ)


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request, headers={"request-id": "req_err"})
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    ("make_exc", "expected", "retryable"),
    [
        (lambda: _status_error(anthropic.RateLimitError, 429), ProviderRateLimited, True),
        (lambda: _status_error(anthropic.AuthenticationError, 401), ProviderAuthError, False),
        (lambda: _status_error(anthropic.BadRequestError, 400), ProviderBadRequest, False),
        (lambda: _status_error(anthropic.InternalServerError, 500), ProviderUnavailable, True),
        (
            lambda: anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")),
            ProviderTimeout,
            True,
        ),
        (
            lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
            ProviderUnavailable,
            True,
        ),
    ],
)
def test_anthropic_error_normalization(monkeypatch, make_exc, expected, retryable):
    def boom():
        raise make_exc()

    provider, _ = _provider(monkeypatch, boom)
    with pytest.raises(expected) as info:
        provider.generate_structured(REQ)
    assert info.value.retryable is retryable


def test_anthropic_requires_key():
    from apps.ai.providers.base import ProviderNotConfigured

    with pytest.raises(ProviderNotConfigured):
        ap.AnthropicProvider(model="claude-opus-5", api_key=None, timeout_seconds=5, max_retries=0)


# --- Workflows -------------------------------------------------------------------


@workflows.register_workflow("test.greet")
def _greet_workflow(run):
    from apps.ai.service import generate_structured

    result = generate_structured(run.organization, REQ, run=run)
    if run.input.get("explode"):
        raise RuntimeError("handler bug")
    return "greeting", "g-1", {"text": result.output.text}


def test_workflow_runs_to_success(make_org, make_user, django_capture_on_commit_callbacks):
    org = make_org()
    user = make_user()
    with django_capture_on_commit_callbacks(execute=True):
        run = workflows.start_workflow(org, "test.greet", user=user, payload={})
    run.refresh_from_db()
    assert run.status == "succeeded" and run.is_mock and run.output["text"].startswith("Hello")
    assert run.usage_records.count() == 1
    # Re-executing a finished run is a no-op (idempotent).
    workflows.execute(str(run.id))
    assert run.usage_records.count() == 1


def test_workflow_failure_is_recorded_without_leaking_details(
    make_org, make_user, django_capture_on_commit_callbacks
):
    org = make_org()
    with django_capture_on_commit_callbacks(execute=True):
        run = workflows.start_workflow(
            org, "test.greet", user=make_user(), payload={"explode": True}
        )
    run.refresh_from_db()
    assert run.status == "failed"
    assert "handler bug" not in run.error_message


def test_workflow_provider_error_is_user_friendly(
    make_org, make_user, django_capture_on_commit_callbacks
):
    org = make_org()
    MockProvider.next_error = ProviderRateLimited("429 upstream")
    with django_capture_on_commit_callbacks(execute=True):
        run = workflows.start_workflow(org, "test.greet", user=make_user(), payload={})
    run.refresh_from_db()
    assert run.status == "failed" and run.error_code == "ai_rate_limited"
    assert "429" not in run.error_message


def test_runs_and_usage_are_tenant_scoped(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    run_b = AIWorkflowRun.objects.create(organization=org_b, workflow="test.greet")
    assert client_a.get(f"/api/v1/orgs/{org_a.id}/ai/runs/{run_b.id}/").status_code == 404
    assert client_b.get(f"/api/v1/orgs/{org_b.id}/ai/runs/{run_b.id}/").status_code == 200
    usage = client_a.get(f"/api/v1/orgs/{org_a.id}/usage/").json()
    assert usage["ai_requests"] == 0 and usage["cost_is_estimate"] is True


def test_viewer_cannot_see_usage(org_client):
    client, org = org_client("viewer")
    assert client.get(f"/api/v1/orgs/{org.id}/usage/").status_code == 403


def test_unknown_workflow_fails_instead_of_hanging(make_org):
    run = AIWorkflowRun.objects.create(organization=make_org(), workflow="not.registered")
    workflows.execute(str(run.id))
    run.refresh_from_db()
    assert run.status == "failed" and run.error_code == "workflow_unavailable"
