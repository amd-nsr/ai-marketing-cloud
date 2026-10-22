"""Per-request context propagated to logs without threading it through call sites."""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
