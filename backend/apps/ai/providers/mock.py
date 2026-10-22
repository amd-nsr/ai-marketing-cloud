"""Deterministic mock provider for automated tests and keyless local development.

Every result it produces is flagged ``is_mock=True`` and stored as such; the UI labels
it. It never contacts any external service and is refused in production settings.
"""

import hashlib
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from .base import (
    Capability,
    ProviderOutputInvalid,
    StructuredRequest,
    StructuredResult,
    T,
    UnsupportedCapability,
    Usage,
)

MockFixture = Callable[[StructuredRequest[Any]], BaseModel]
_FIXTURES: dict[type[BaseModel], MockFixture] = {}


def register_mock_fixture(schema: type[BaseModel], fixture: MockFixture) -> None:
    """Domain apps register how the mock answers for each of their output schemas."""
    _FIXTURES[schema] = fixture


class MockProvider:
    name = "mock"
    model = "mock-1"
    capabilities = frozenset({Capability.STRUCTURED_OUTPUT})
    is_mock = True

    #: Tests can force failures: set to an AIProviderError instance to raise it next call.
    next_error: Exception | None = None

    def generate_structured(self, request: StructuredRequest[T]) -> StructuredResult[T]:
        if MockProvider.next_error is not None:
            error, MockProvider.next_error = MockProvider.next_error, None
            raise error
        fixture = _FIXTURES.get(request.schema)
        if fixture is None:
            raise UnsupportedCapability(
                f"No mock fixture registered for {request.schema.__name__}."
            )
        output = fixture(request)
        if not isinstance(output, request.schema):
            raise ProviderOutputInvalid("Mock fixture returned the wrong type.")
        # Deterministic pseudo token counts so usage accounting is exercised.
        digest = int(hashlib.sha256(request.prompt.encode()).hexdigest()[:6], 16)
        return StructuredResult(
            output=output,
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=len(request.prompt) // 4 + 50, output_tokens=200 + digest % 300
            ),
            latency_ms=5,
            request_id=f"mock-{digest:06x}",
            is_mock=True,
        )
