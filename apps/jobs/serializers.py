from rest_framework import serializers

from .models import Job


class JobSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ('id', 'job_type', 'priority', 'payload', 'status', 'created_at')
        read_only_fields = ('id', 'status', 'created_at')
        extra_kwargs = {
            'priority': {'required': False},
        }

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Payload must be a JSON object.')

        return value

    def validate(self, attrs):
        job_type = attrs.get('job_type')

        if job_type == Job.JobType.FRAUD_CHECK:
            attrs['priority'] = Job.Priority.HIGH
        elif job_type == Job.JobType.SEND_NOTIFICATION:
            attrs['priority'] = Job.Priority.LOW
        elif job_type == Job.JobType.PROCESS_PAYMENT:
            attrs['priority'] = attrs.get('priority') or Job.Priority.MEDIUM

        return attrs

    def create(self, validated_data):
        return Job.objects.create(
            user=self.context['request'].user,
            **validated_data,
        )


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = (
            'id',
            'job_type',
            'priority',
            'status',
            'payload',
            'retry_count',
            'result',
            'failure_reason',
            'created_at',
            'updated_at',
            'started_at',
            'completed_at',
        )
        read_only_fields = fields
