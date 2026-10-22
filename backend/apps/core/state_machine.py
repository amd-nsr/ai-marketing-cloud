"""Explicit, table-driven status transitions for workflow models."""

from collections.abc import Mapping

from .errors import InvalidTransition


def assert_transition(
    resource: str,
    transitions: Mapping[str, frozenset[str]],
    current: str,
    target: str,
) -> None:
    """Raise InvalidTransition unless ``current -> target`` is an allowed edge."""
    if target not in transitions.get(current, frozenset()):
        raise InvalidTransition(resource, current, target)
