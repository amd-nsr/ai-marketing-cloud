from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "action",
            "actor_type",
            "actor_email",
            "target_type",
            "target_id",
            "metadata",
            "request_id",
            "created_at",
        ]
        read_only_fields = fields
