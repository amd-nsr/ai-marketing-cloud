from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

# Fast hashing keeps the suite quick; never use outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tests must not depend on a running Redis unless they opt in explicitly.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
CELERY_TASK_ALWAYS_EAGER = True
AI_PROVIDER = "mock"
SOCIAL_MOCK_ENABLED = True
PUBLISH_RETRY_BASE_SECONDS = 1
PUBLISH_RECONCILE_DELAY_SECONDS = 0
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CELERY_TASK_EAGER_PROPAGATES = True

LOG_FORMAT = "console"
LOGGING["handlers"]["stdout"]["formatter"] = "console"  # noqa: F405
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
