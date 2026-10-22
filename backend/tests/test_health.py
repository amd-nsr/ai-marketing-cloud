import pytest
import redis
from django.urls import reverse

from apps.core import health

pytestmark = pytest.mark.django_db


def test_liveness_is_public_and_does_not_touch_dependencies(api_client, monkeypatch):
    def fail() -> None:
        raise AssertionError("liveness must not run dependency checks")

    monkeypatch.setattr(health, "run_readiness_checks", fail)
    response = api_client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok_when_dependencies_reachable(api_client, monkeypatch):
    monkeypatch.setattr(health, "_check_redis", lambda: None)
    response = api_client.get(reverse("health-ready"))
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


def test_readiness_503_and_no_detail_leak_when_redis_down(api_client, monkeypatch):
    def broken() -> None:
        raise redis.ConnectionError("connect to redis://:s3cret@internal-host failed")

    monkeypatch.setattr(health, "_check_redis", broken)
    response = api_client.get(reverse("health-ready"))
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "unavailable"
    assert body["checks"]["redis"] == {
        "ok": False,
        "latency_ms": body["checks"]["redis"]["latency_ms"],
        "error": "ConnectionError",
    }
    assert "s3cret" not in response.content.decode()


@pytest.mark.integration
def test_readiness_against_real_redis(api_client, settings):
    try:
        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
    except redis.RedisError:
        pytest.skip("Redis is not reachable at REDIS_URL")
    response = api_client.get(reverse("health-ready"))
    assert response.status_code == 200, response.json()
