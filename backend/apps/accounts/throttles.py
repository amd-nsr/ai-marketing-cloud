from rest_framework.throttling import ScopedRateThrottle


class AuthRateThrottle(ScopedRateThrottle):
    """Per-client-IP limit for credential endpoints (scope configured per view)."""
