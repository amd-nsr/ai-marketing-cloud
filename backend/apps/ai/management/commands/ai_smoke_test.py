"""Verify the configured AI provider with one tiny structured request.

    uv run python manage.py ai_smoke_test --org <org-id>

This makes a real, billed provider call when AI_PROVIDER is a real provider. It is
operator-initiated only; nothing in the application runs it automatically.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from pydantic import BaseModel

from apps.ai.providers.base import AIProviderError, StructuredRequest
from apps.ai.providers.mock import register_mock_fixture
from apps.ai.service import generate_structured
from apps.organizations.models import Organization


class SmokeTestOutput(BaseModel):
    status: str
    sample_headline: str


register_mock_fixture(
    SmokeTestOutput, lambda _r: SmokeTestOutput(status="ok", sample_headline="Mock headline")
)


class Command(BaseCommand):
    help = "Make one small structured AI request to verify provider configuration."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--org", required=True, help="Organization ID to attribute usage to.")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            org = Organization.objects.get(pk=options["org"])
        except (Organization.DoesNotExist, ValueError) as exc:
            raise CommandError("Organization not found.") from exc
        request = StructuredRequest(
            operation="ai.smoke_test",
            system="You verify an integration. Reply with status 'ok'.",
            prompt="Return status 'ok' and a five-word headline for a neighbourhood coffee shop.",
            schema=SmokeTestOutput,
            max_tokens=1024,
            effort="low",
        )
        try:
            result = generate_structured(org, request)
        except AIProviderError as exc:
            raise CommandError(f"{exc.code}: {exc}") from exc
        label = " (MOCK - no real provider called)" if result.is_mock else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"provider={result.provider} model={result.model}{label} "
                f"tokens={result.usage.input_tokens}/{result.usage.output_tokens} "
                f"fallback={result.served_by_fallback} output={result.output.model_dump()}"
            )
        )
