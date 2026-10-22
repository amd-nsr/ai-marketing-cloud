from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import health

_check_serializer = inline_serializer(
    "HealthCheck",
    {
        "ok": serializers.BooleanField(),
        "latency_ms": serializers.FloatField(),
        "error": serializers.CharField(allow_null=True),
    },
)


class LivenessView(APIView):
    """The process is up and serving requests. Does not touch dependencies."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer("Liveness", {"status": serializers.CharField()}),
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """The process can serve real traffic: PostgreSQL and Redis are reachable."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                "Readiness",
                {
                    "status": serializers.ChoiceField(choices=["ok", "unavailable"]),
                    "checks": serializers.DictField(child=_check_serializer),
                },
            ),
            503: None,
        },
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        results = health.run_readiness_checks()
        healthy = all(r.ok for r in results)
        return Response(
            {
                "status": "ok" if healthy else "unavailable",
                "checks": {
                    r.name: {"ok": r.ok, "latency_ms": r.latency_ms, "error": r.error}
                    for r in results
                },
            },
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
