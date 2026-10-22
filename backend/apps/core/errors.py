"""Domain-level exceptions that map cleanly onto API responses."""

from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    """The request conflicts with the resource's current state (e.g. invalid transition)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


class InvalidTransition(Conflict):
    default_code = "invalid_transition"

    def __init__(self, resource: str, current: str, target: str) -> None:
        super().__init__(f"Cannot move {resource} from '{current}' to '{target}'.")


class QuotaExceeded(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Your organization has reached its usage limit."
    default_code = "quota_exceeded"


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A required service is not configured or unavailable."
    default_code = "service_unavailable"
