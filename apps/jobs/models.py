import uuid

from django.conf import settings
from django.db import models


class Job(models.Model):
    class JobType(models.TextChoices):
        REFUND_PROCESSING = 'refund_processing', 'Refund Processing'
        WEBHOOK_DELIVERY = 'webhook_delivery', 'Webhook Delivery'
        SEND_NOTIFICATION = 'send_notification', 'Send Notification'

    class Priority(models.TextChoices):
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DEAD = 'dead', 'Dead'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='jobs',
    )
    source_job = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='follow_up_jobs',
    )
    source_event = models.CharField(max_length=64, null=True, blank=True)
    job_type = models.CharField(max_length=32, choices=JobType.choices)
    priority = models.CharField(max_length=16, choices=Priority.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    payload = models.JSONField()
    idempotency_key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
    )
    request_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )
    retry_count = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'jobs'
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('user', 'status')),
            models.Index(fields=('job_type', 'status')),
            models.Index(fields=('priority', 'created_at')),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='unique_job_user_idempotency_key',
            ),
            models.UniqueConstraint(
                fields=('source_job', 'job_type', 'source_event'),
                name='unique_follow_up_per_source_event',
            ),
        ]

    def __str__(self):
        return f'{self.job_type} [{self.status}]'
