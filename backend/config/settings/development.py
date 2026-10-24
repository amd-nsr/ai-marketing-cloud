from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])
LOG_FORMAT = env("LOG_FORMAT", default="console")
LOGGING["handlers"]["stdout"]["formatter"] = LOG_FORMAT  # noqa: F405

# The browsable API is convenient while developing; production serves JSON only.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = ["rest_framework.permissions.AllowAny"]  # noqa: F405

# Without a key, local development uses the labelled mock AI provider.
AI_PROVIDER = env(
    "AI_PROVIDER", default="anthropic" if env("ANTHROPIC_API_KEY", default=None) else "mock"
)

SOCIAL_MOCK_ENABLED = env.bool("SOCIAL_MOCK_ENABLED", default=True)
# Show the advertising features locally (simulation ad accounts work without Meta access).
META_ADS_ENABLED = env.bool("META_ADS_ENABLED", default=True)

# Labelled placeholder images, so the design studio's generate flow can be exercised
# locally. There is no real image provider yet (docs/decisions/0015).
IMAGE_PROVIDER = env("IMAGE_PROVIDER", default="mock")
