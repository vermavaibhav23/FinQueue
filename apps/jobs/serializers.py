from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import Job


PRIORITY_BY_JOB_TYPE = {
    Job.JobType.REFUND_PROCESSING: Job.Priority.HIGH,
    Job.JobType.WEBHOOK_DELIVERY: Job.Priority.MEDIUM,
    Job.JobType.SEND_NOTIFICATION: Job.Priority.LOW,
}


class JobSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ('id', 'job_type', 'priority', 'payload', 'status', 'created_at')
        read_only_fields = ('id', 'priority', 'status', 'created_at')

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Payload must be a JSON object.')

        return value

    def validate(self, attrs):
        job_type = attrs['job_type']
        payload = attrs['payload']

        if job_type == Job.JobType.REFUND_PROCESSING:
            self._validate_refund_payload(payload)
        elif job_type == Job.JobType.WEBHOOK_DELIVERY:
            self._validate_webhook_payload(payload)
        elif job_type == Job.JobType.SEND_NOTIFICATION:
            self._validate_notification_payload(payload)

        attrs['priority'] = PRIORITY_BY_JOB_TYPE[job_type]
        return attrs

    def create(self, validated_data):
        return Job.objects.create(
            user=self.context['request'].user,
            **validated_data,
        )

    @staticmethod
    def _validate_refund_payload(payload):
        transaction_id = str(payload.get('transaction_id', '')).strip()
        if not transaction_id:
            raise serializers.ValidationError(
                {'payload': 'refund_processing requires transaction_id.'}
            )

        try:
            amount = Decimal(str(payload.get('amount')))
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError(
                {'payload': 'refund_processing requires a valid amount.'}
            )

        if amount <= 0:
            raise serializers.ValidationError(
                {'payload': 'Refund amount must be greater than 0.'}
            )

        webhook_url = str(payload.get('webhook_url', '')).strip()
        if not webhook_url.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                {
                    'payload': (
                        'refund_processing requires webhook_url so the terminal '
                        'refund event can be delivered asynchronously.'
                    )
                }
            )

        notification = payload.get('notification')
        if not isinstance(notification, dict):
            raise serializers.ValidationError(
                {
                    'payload': (
                        'refund_processing requires a notification object with '
                        'channel and recipient.'
                    )
                }
            )

        channel = str(notification.get('channel', '')).lower().strip()
        recipient = str(notification.get('recipient', '')).strip()

        if channel not in {'email', 'sms', 'push'}:
            raise serializers.ValidationError(
                {'payload': 'Notification channel must be email, sms, or push.'}
            )

        if not recipient:
            raise serializers.ValidationError(
                {'payload': 'Notification recipient is required.'}
            )

    @staticmethod
    def _validate_webhook_payload(payload):
        url = str(payload.get('url', '')).strip()
        event = str(payload.get('event', '')).strip()

        if not url.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                {'payload': 'webhook_delivery requires a valid http/https url.'}
            )

        if not event:
            raise serializers.ValidationError(
                {'payload': 'webhook_delivery requires an event name.'}
            )

        data = payload.get('data', {})
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {'payload': 'Webhook data must be a JSON object.'}
            )

    @staticmethod
    def _validate_notification_payload(payload):
        channel = str(payload.get('channel', '')).lower().strip()
        recipient = str(payload.get('recipient', '')).strip()
        message = str(payload.get('message', '')).strip()

        if channel not in {'email', 'sms', 'push'}:
            raise serializers.ValidationError(
                {'payload': 'Notification channel must be email, sms, or push.'}
            )

        if not recipient:
            raise serializers.ValidationError(
                {'payload': 'send_notification requires a recipient.'}
            )

        if not message:
            raise serializers.ValidationError(
                {'payload': 'send_notification requires a message.'}
            )


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = (
            'id',
            'source_job',
            'source_event',
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
