from rest_framework import serializers

from .models import AIWorkflowRun


class AIWorkflowRunSerializer(serializers.ModelSerializer[AIWorkflowRun]):
    class Meta:
        model = AIWorkflowRun
        fields = [
            "id",
            "workflow",
            "status",
            "result_type",
            "result_id",
            "output",
            "provider",
            "model",
            "is_mock",
            "error_code",
            "error_message",
            "attempts",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields
