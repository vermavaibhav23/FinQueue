from rest_framework import serializers

from .models import DeadLetterQueue


class DeadLetterQueueSerializer(serializers.ModelSerializer):
    original_job_id = serializers.UUIDField(source='original_job.id', read_only=True)

    class Meta:
        model = DeadLetterQueue
        fields = (
            'id',
            'original_job_id',
            'job_type',
            'payload',
            'failure_reason',
            'retry_attempts',
            'died_at',
        )
        read_only_fields = fields
