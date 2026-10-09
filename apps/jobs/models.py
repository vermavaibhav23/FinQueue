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
                fields=('source_job', 'job_type', 'source_event'),
                name='unique_follow_up_per_source_event',
            ),
        ]

    def __str__(self):
        return f'{self.job_type} [{self.status}]'


class Transaction(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        SUSPICIOUS = 'suspicious', 'Suspicious'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    merchant = models.CharField(max_length=255)
    currency = models.CharField(max_length=8, default='INR')
    device_id = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_reasons = models.JSONField(default=list, blank=True)
    processed_at = models.DateTimeField()

    class Meta:
        db_table = 'transactions'
        ordering = ('-processed_at',)
        indexes = [
            models.Index(fields=('user', 'processed_at')),
            models.Index(fields=('status', 'processed_at')),
            models.Index(fields=('job',)),
        ]

    def __str__(self):
        return f'{self.status} transaction for {self.amount} {self.currency}'


class IdempotencyRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='idempotency_requests',
    )
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    job = models.OneToOneField(
        Job,
        on_delete=models.CASCADE,
        related_name='idempotency_request',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'idempotency_requests'
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='unique_user_idempotency_key',
            ),
        ]

    def __str__(self):
        return f'{self.user_id}:{self.idempotency_key}'
