"""Uniform error envelope for every API response.

Shape::

    {"error": {"code": "not_found", "message": "...", "details": {...} | null,
               "request_id": "..."}}
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .request_context import request_id_var

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_var.get(),
        }
    }


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        # Unhandled error: log full detail server-side, never leak it to the client.
        logger.exception("Unhandled API exception", exc_info=exc)
        return Response(
            _error_body("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not isinstance(
        exc, exceptions.APIException
    ):  # pragma: no cover - DRF handles APIException only
        return response
    if isinstance(exc, exceptions.ValidationError):
        body = _error_body("validation_error", "The request contains invalid data.", response.data)
    else:
        detail = (
            response.data.get("detail", exc.default_detail)
            if isinstance(response.data, dict)
            else exc.default_detail
        )
        body = _error_body(str(exc.default_code), str(detail))
    response.data = body
    return response


# Django-level handlers for errors raised outside DRF views (e.g. unknown URLs).
# Django only uses these when DEBUG is False.


def json_not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(_error_body("not_found", "Not found."), status=404)


def json_server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(_error_body("server_error", "An unexpected error occurred."), status=500)
