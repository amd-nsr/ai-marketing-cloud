"""Production settings. Every security-relevant value must be explicit."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import AI_PROVIDER, ALLOWED_HOSTS, SECRET_KEY, env

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("change-me"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique value in production.")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must be set in production.")

if AI_PROVIDER == "mock" and not env.bool("AI_ALLOW_MOCK_IN_PRODUCTION", default=False):
    raise ImproperlyConfigured("AI_PROVIDER=mock is not allowed in production.")

if not env.list("SOCIAL_TOKEN_ENCRYPTION_KEYS", default=[]):
    raise ImproperlyConfigured("SOCIAL_TOKEN_ENCRYPTION_KEYS must be set in production.")

# TLS is terminated at the load balancer / reverse proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/"]  # Internal probes may use plain HTTP.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
