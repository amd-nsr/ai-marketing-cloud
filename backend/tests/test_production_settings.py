"""Production settings must refuse to start with insecure configuration."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
STRONG_KEY = "x" * 64


def _load_production_settings(**overrides: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DATABASE_URL": "postgres://u:p@localhost:5432/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "DJANGO_SECRET_KEY": STRONG_KEY,
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
        "SOCIAL_TOKEN_ENCRYPTION_KEYS": "x" * 43 + "=",
        **overrides,
    }
    code = "import django; django.setup(); from django.conf import settings; print(settings.DEBUG)"
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True
    )


def test_production_settings_load_with_secure_configuration():
    result = _load_production_settings()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_production_rejects_weak_secret_key():
    result = _load_production_settings(DJANGO_SECRET_KEY="change-me-dev-only-insecure-key")
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_production_requires_allowed_hosts():
    result = _load_production_settings(DJANGO_ALLOWED_HOSTS="")
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_production_rejects_mock_ai_provider():
    result = _load_production_settings(AI_PROVIDER="mock")
    assert result.returncode != 0
    assert "AI_PROVIDER=mock" in result.stderr
