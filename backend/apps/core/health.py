"""Dependency checks used by the readiness probe."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import redis
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 2


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    latency_ms: float
    error: str | None = None


def _timed(name: str, check: Callable[[], None]) -> CheckResult:
    started = time.perf_counter()
    try:
        check()
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        logger.warning(
            "Health check failed", extra={"check": name, "error_type": type(exc).__name__}
        )
        return CheckResult(name, False, _elapsed_ms(started), type(exc).__name__)
    return CheckResult(name, True, _elapsed_ms(started))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_redis() -> None:
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
        socket_timeout=CHECK_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    finally:
        client.close()


def run_readiness_checks() -> list[CheckResult]:
    return [_timed("database", _check_database), _timed("redis", _check_redis)]
