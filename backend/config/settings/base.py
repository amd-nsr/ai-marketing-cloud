"""Settings shared by every environment.

All environment-specific values come from environment variables (see the
repository-level ``.env.example``). Environment modules (development, test,
production) import from here and override only what differs.
"""

from pathlib import Path
from typing import Any

import django_stubs_ext
import environ

# Allows generic Django classes (e.g. ``UserAdmin[User]``) to be subscripted at runtime.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load the repository-root .env when present (local development only; never committed).
environ.Env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.audit",
    "apps.usage",
    "apps.brand",
    "apps.ai",
    "apps.marketing",
    "apps.content",
    "apps.social",
    "apps.publishing",
    "apps.automation",
    "apps.notifications",
    "apps.analytics",
    "apps.operations",
    "apps.meta",
    "apps.ads",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Data stores -----------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication --------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions live in PostgreSQL; the cookie is HttpOnly and first-party via the
# Next.js proxy (docs/decisions/0003). The CSRF cookie must be readable by the
# frontend so it can echo it in the X-CSRFToken header.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"]
)
PASSWORD_RESET_TIMEOUT = 60 * 60 * 3

# Public URL of the web app; used in emails (password reset, invitations).
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

# Django 6.1 MAILERS. EMAIL_URL examples: consolemail://, smtp+tls://user:pass@host:587
_email = env.email_url("EMAIL_URL", default="consolemail://")
_smtp_options = {
    "host": _email.get("EMAIL_HOST"),
    "port": _email.get("EMAIL_PORT"),
    "username": _email.get("EMAIL_HOST_USER"),
    "password": _email.get("EMAIL_HOST_PASSWORD"),
    "use_tls": _email.get("EMAIL_USE_TLS"),
    "use_ssl": _email.get("EMAIL_USE_SSL"),
    "timeout": 10,
}
MAILERS: dict[str, Any] = {
    "default": {
        "BACKEND": _email["EMAIL_BACKEND"],
        "OPTIONS": (
            {k: v for k, v in _smtp_options.items() if v not in (None, "")}
            if _email["EMAIL_BACKEND"].endswith("smtp.EmailBackend")
            else {}
        ),
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="AI Marketing Cloud <no-reply@localhost>")

# --- Internationalisation --------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Media storage ---------------------------------------------------------
# Uploaded and generated files. Never served publicly by Django: the API streams
# local files after an authorization check, or redirects to short-lived signed URLs.

MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")  # "local" or "s3"
_media_storage: dict[str, Any]
if STORAGE_BACKEND == "s3":
    _media_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "region_name": env("S3_REGION", default=None),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),  # MinIO / R2 / etc.
            "access_key": env("S3_ACCESS_KEY_ID", default=None),
            "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": env.int("S3_SIGNED_URL_TTL", default=600),
            "file_overwrite": False,
        },
    }
else:
    _media_storage = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT},
    }
STORAGES = {
    "default": _media_storage,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAX_IMAGE_UPLOAD_BYTES = env.int("MAX_IMAGE_UPLOAD_BYTES", default=10 * 1024 * 1024)
# Content studio media (video/audio library uploads, video rendering).
MAX_MEDIA_UPLOAD_BYTES = env.int("MAX_MEDIA_UPLOAD_BYTES", default=100 * 1024 * 1024)
MAX_MEDIA_DURATION_SECONDS = env.int("MAX_MEDIA_DURATION_SECONDS", default=600)
FFMPEG_BINARY = env("FFMPEG_BINARY", default="ffmpeg")
FFPROBE_BINARY = env("FFPROBE_BINARY", default="ffprobe")
VIDEO_RENDER_TIMEOUT_SECONDS = env.int("VIDEO_RENDER_TIMEOUT_SECONDS", default=600)
#: Font used for video text overlays and subtitles (any TTF/OTF path).
VIDEO_FONT_FILE = env(
    "VIDEO_FONT_FILE", default="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)
# Image generation is a separate capability from text AI: "none" (default, disabled),
# or "mock" (labelled placeholder images for development). See docs/decisions/0015.
IMAGE_PROVIDER = env("IMAGE_PROVIDER", default="none")
IMAGE_COST_PER_IMAGE_USD = env.float("IMAGE_COST_PER_IMAGE_USD", default=0.0)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# --- Usage limits (per organization; overridable per org) -----------------

USAGE_DEFAULT_LIMITS: dict[str, Any] = {
    "ai_requests_per_month": env.int("LIMIT_AI_REQUESTS_PER_MONTH", default=500),
    "ai_cost_per_month_usd": env.float("LIMIT_AI_COST_PER_MONTH_USD", default=25.0),
    "storage_bytes": env.int("LIMIT_STORAGE_BYTES", default=1024 * 1024 * 1024),
    "publishes_per_day": env.int("LIMIT_PUBLISHES_PER_DAY", default=25),
}

# --- AI ----------------------------------------------------------------------
# Provider selection is configuration (docs/decisions/0009-ai-provider-layer.md).
# "mock" is a clearly labelled deterministic provider for tests and keyless local
# development; production settings refuse it unless explicitly allowed.

AI_PROVIDER = env("AI_PROVIDER", default="anthropic")  # "anthropic" | "mock"
AI_MODEL = env("AI_MODEL", default="claude-opus-5")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default=None)
AI_TIMEOUT_SECONDS = env.float("AI_TIMEOUT_SECONDS", default=180.0)
AI_MAX_RETRIES = env.int("AI_MAX_RETRIES", default=2)
AI_USE_REFUSAL_FALLBACK = env.bool("AI_USE_REFUSAL_FALLBACK", default=True)
# USD per million tokens (list prices; used only for estimates and quotas).
AI_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-5": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write": 2.5},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
    "mock-1": {"input": 0.0, "output": 0.0},
}

# --- Social platforms & publishing --------------------------------------------
# Real integrations need app credentials from each platform's developer console.
META_APP_ID = env("META_APP_ID", default=None)
META_APP_SECRET = env("META_APP_SECRET", default=None)
META_GRAPH_VERSION = env("META_GRAPH_VERSION", default="v26.0")
#: Request the Marketing API permissions (ads_read, ads_management) during Meta login.
#: Off by default: only ask for what the deployment uses (App Review covers each scope).
META_ADS_ENABLED = env.bool("META_ADS_ENABLED", default=False)
#: Shared secret Meta echoes back when verifying the webhook subscription.
META_WEBHOOK_VERIFY_TOKEN = env("META_WEBHOOK_VERIFY_TOKEN", default=None)
#: Throttle Meta calls once any reported usage reaches this percentage.
META_USAGE_THROTTLE_PERCENT = env.int("META_USAGE_THROTTLE_PERCENT", default=90)
#: Warn (and later require reconnection) when a Meta user token expires within N days.
META_TOKEN_WARNING_DAYS = env.int("META_TOKEN_WARNING_DAYS", default=7)
#: Days of daily ad insights fetched per sync.
ADS_INSIGHTS_DAYS = env.int("ADS_INSIGHTS_DAYS", default=30)
#: Spend-affecting ad changes are refused if spend wasn't synced within this many hours.
ADS_SPEND_DATA_MAX_AGE_HOURS = env.int("ADS_SPEND_DATA_MAX_AGE_HOURS", default=24)
TIKTOK_CLIENT_KEY = env("TIKTOK_CLIENT_KEY", default=None)
TIKTOK_CLIENT_SECRET = env("TIKTOK_CLIENT_SECRET", default=None)
SOCIAL_HTTP_TIMEOUT_SECONDS = env.float("SOCIAL_HTTP_TIMEOUT_SECONDS", default=30.0)
# Simulation accounts (mock adapter). Disabled by default; development/test enable it.
SOCIAL_MOCK_ENABLED = env.bool("SOCIAL_MOCK_ENABLED", default=False)


def _derived_dev_key(secret: str) -> str:
    import base64
    import hashlib

    return base64.urlsafe_b64encode(
        hashlib.sha256(f"social-tokens:{secret}".encode()).digest()
    ).decode()


# Comma-separated Fernet keys; the first encrypts, all decrypt (rotation). Production
# requires explicit keys; other environments derive one from SECRET_KEY.
SOCIAL_TOKEN_ENCRYPTION_KEYS: list[str] = env.list("SOCIAL_TOKEN_ENCRYPTION_KEYS", default=[]) or [
    _derived_dev_key(SECRET_KEY)
]
PUBLISH_MAX_ATTEMPTS = env.int("PUBLISH_MAX_ATTEMPTS", default=4)
PUBLISH_RETRY_BASE_SECONDS = env.int("PUBLISH_RETRY_BASE_SECONDS", default=30)
PUBLISH_RECONCILE_DELAY_SECONDS = env.int("PUBLISH_RECONCILE_DELAY_SECONDS", default=120)
PUBLISH_MAX_SCHEDULE_DAYS = 90

# --- API -------------------------------------------------------------------

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_AUTH", default="10/min"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", default="5/hour"),
        "ai": env("THROTTLE_AI", default="20/min"),
    },
    # Number of trusted reverse proxies in front of Django (the Next.js server counts).
    # Used to derive client IPs for rate limiting from X-Forwarded-For.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": "AI Marketing Cloud API",
    "DESCRIPTION": "HTTP API consumed by the AI Marketing Cloud frontend.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    # The API surface is not public. Contracts are generated offline with
    # `manage.py spectacular`; development relaxes this for the docs UI.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    # Distinct, stable names for the many "status" enums.
    "ENUM_NAME_OVERRIDES": {
        "InvitationStatusEnum": "apps.organizations.models.Invitation.Status",
        "AIWorkflowRunStatusEnum": "apps.ai.models.AIWorkflowRun.Status",
        "MarketingPlanStatusEnum": "apps.marketing.models.MarketingPlan.Status",
        "CampaignStatusEnum": "apps.marketing.models.Campaign.Status",
        "ContentStatusEnum": "apps.content.models.ContentItem.Status",
        "ApprovalStatusEnum": "apps.content.models.Approval.Status",
        "PublishingJobStatusEnum": "apps.publishing.models.PublishingJob.Status",
        "SocialAccountStatusEnum": "apps.social.models.SocialAccount.Status",
        "PublishingAttemptOutcomeEnum": "apps.publishing.models.PublishingAttempt.Outcome",
        "BrandAssetKindEnum": "apps.brand.models.BrandAsset.Kind",
        "NotificationKindEnum": "apps.notifications.models.Notification.Kind",
        "RecommendationKindEnum": "apps.analytics.models.MarketingRecommendation.Kind",
        "RecommendationStatusEnum": "apps.analytics.models.MarketingRecommendation.Status",
        "AutonomyModeEnum": "apps.automation.models.AutonomyMode",
        "AutomationActionStatusEnum": "apps.automation.models.AutomationAction.Status",
        "AutomationActionTypeEnum": "apps.automation.models.AutomationAction.ActionType",
        # Plans and content versions share the same provenance values.
        "AuthorshipSourceEnum": "apps.content.models.ContentVersion.Source",
        "PlatformEnum": ["instagram", "facebook", "tiktok"],
        "SocialPlatformEnum": "apps.social.models.SocialPlatform",
        "ContentPlatformEnum": "apps.content.models.Platform",
        "AdCampaignSourceEnum": "apps.ads.models.AdCampaign.Source",
        "AdCampaignStateEnum": "apps.ads.models.AdCampaign.State",
        "AdObjectiveEnum": "apps.ads.models.AdCampaign.Objective",
        "AdSyncStatusEnum": "apps.ads.models.AdSyncRun.Status",
        "MetaConnectionStatusEnum": "apps.meta.models.MetaConnection.Status",
    },
}

# --- Background jobs -------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None  # Durable state lives in PostgreSQL, not Celery results.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = TIME_ZONE
# Run exactly ONE beat process per environment (docs/decisions/0005).
CELERY_BEAT_SCHEDULE = {
    "publishing-dispatch": {"task": "publishing.dispatch_due", "schedule": 30.0},
    "publishing-reconcile": {"task": "publishing.reconcile", "schedule": 60.0},
    "analytics-collect": {"task": "analytics.collect_metrics", "schedule": 15 * 60.0},
    "analytics-recommendations": {
        "task": "analytics.generate_recommendations",
        "schedule": 6 * 3600.0,
    },
    "automation-run": {"task": "automation.run", "schedule": 15 * 60.0},
    "automation-reevaluate": {"task": "automation.reevaluate", "schedule": 5 * 60.0},
    "operations-heartbeat": {"task": "operations.heartbeat", "schedule": 60.0},
    "operations-sweep": {"task": "operations.sweep", "schedule": 5 * 60.0},
    "meta-check-connections": {"task": "meta.check_connections", "schedule": 24 * 3600.0},
    "ads-sync": {"task": "ads.sync_due", "schedule": 30 * 60.0},
    "ads-optimize": {"task": "ads.optimize", "schedule": 60 * 60.0},
}

# --- Operations ------------------------------------------------------------

# Background processing counts as down when no heartbeat arrived for this long.
OPERATIONS_HEARTBEAT_STALE_SECONDS = env.int("OPERATIONS_HEARTBEAT_STALE_SECONDS", default=180)
# AI runs: re-submit if still queued after N minutes, fail if never started after M,
# fail as timed out if running longer than T (well above AI_TIMEOUT_SECONDS x retries).
AI_RUN_RESUBMIT_AFTER_MINUTES = env.int("AI_RUN_RESUBMIT_AFTER_MINUTES", default=10)
AI_RUN_QUEUE_TIMEOUT_MINUTES = env.int("AI_RUN_QUEUE_TIMEOUT_MINUTES", default=60)
AI_RUN_TIMEOUT_MINUTES = env.int("AI_RUN_TIMEOUT_MINUTES", default=20)
AUTOMATION_ACTION_STUCK_MINUTES = env.int("AUTOMATION_ACTION_STUCK_MINUTES", default=15)

# --- Logging ---------------------------------------------------------------

LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_FORMAT = env("LOG_FORMAT", default="json")  # "json" or "console"

LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "console": {
            "format": "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
        "celery": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
    },
}
