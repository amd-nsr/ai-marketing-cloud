import re
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .request_context import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# Accept caller-supplied IDs (e.g. from the frontend or a load balancer) only
# when they are short and safe to echo into logs and response headers.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Attaches a request ID to the request, the log context, and the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response
