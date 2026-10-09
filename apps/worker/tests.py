from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.jobs.models import Job
from apps.worker.engine import WorkerEngine
from apps.worker.handlers import dispatch_job, get_external_operation_id
from apps.worker.recovery import recover_stale_running_jobs


class FakeRedis:
    def __init__(self):
        self.sorted_sets = {}

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)


def refund_payload():
    return {
        'transaction_id': 'txn-1001',
        'amount': '1000.00',
        'currency': 'INR',
        'webhook_url': 'https://merchant.example/webhooks',
        'notification': {
            'channel': 'email',
            'recipient': 'customer@example.com',
        },
    }


@override_settings(FINQUEUE_MAX_RETRIES=3)
class WorkerRetryTests(TestCase):
    def test_failed_job_is_scheduled_for_retry(self):
        user = User.objects.create_user(username='student')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.RUNNING,
            payload=refund_payload(),
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_failed(job, 'gateway timeout')
        job.refresh_from_db()

        self.assertEqual(job.status, Job.Status.PENDING)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.failure_reason, 'gateway timeout')
        self.assertIsNone(job.lease_expires_at)
        self.assertEqual(Job.objects.filter(source_job=job).count(), 0)

    def test_completed_refund_creates_webhook_and_notification_jobs(self):
        user = User.objects.create_user(username='refund-success')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.RUNNING,
            payload=refund_payload(),
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_completed(
            job,
            {
                'refund_id': 'refund-123',
                'transaction_id': 'txn-1001',
                'status': 'REFUNDED',
                'amount': '1000.00',
                'currency': 'INR',
            },
        )

        job.refresh_from_db()
        follow_ups = Job.objects.filter(source_job=job).order_by('priority')

        self.assertEqual(job.status, Job.Status.COMPLETED)
        self.assertEqual(follow_ups.count(), 2)

        webhook = follow_ups.get(job_type=Job.JobType.WEBHOOK_DELIVERY)
        notification = follow_ups.get(job_type=Job.JobType.SEND_NOTIFICATION)

        self.assertEqual(webhook.priority, Job.Priority.MEDIUM)
        self.assertEqual(webhook.payload['event'], 'refund.completed')
        self.assertEqual(webhook.payload['data']['refund_id'], 'refund-123')
        self.assertEqual(
            webhook.payload['event_id'],
            f'refund.completed:{job.id}',
        )
        self.assertEqual(notification.priority, Job.Priority.LOW)
        self.assertEqual(
            notification.payload['notification_id'],
            f'notification:refund.completed:{job.id}',
        )
        self.assertIn('has been processed', notification.payload['message'])

    def test_dead_refund_creates_failed_webhook_and_notification_jobs(self):
        user = User.objects.create_user(username='refund-dead')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.RUNNING,
            retry_count=3,
            payload=refund_payload(),
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_failed(job, 'refund provider unavailable')

        job.refresh_from_db()
        follow_ups = Job.objects.filter(source_job=job)

        self.assertEqual(job.status, Job.Status.DEAD)
        self.assertEqual(follow_ups.count(), 2)

        webhook = follow_ups.get(job_type=Job.JobType.WEBHOOK_DELIVERY)
        notification = follow_ups.get(job_type=Job.JobType.SEND_NOTIFICATION)

        self.assertEqual(webhook.payload['event'], 'refund.failed')
        self.assertEqual(
            webhook.payload['event_id'],
            f'refund.failed:{job.id}',
        )
        self.assertEqual(
            webhook.payload['data']['failure_reason'],
            'refund provider unavailable',
        )
        self.assertEqual(
            notification.payload['notification_id'],
            f'notification:refund.failed:{job.id}',
        )
        self.assertIn('could not be processed', notification.payload['message'])

    def test_follow_up_creation_is_idempotent(self):
        user = User.objects.create_user(username='refund-idempotent')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.RUNNING,
            payload=refund_payload(),
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_completed(job, {'refund_id': 'refund-123'})
        engine._enqueue_terminal_follow_ups(job)

        self.assertEqual(Job.objects.filter(source_job=job).count(), 2)

    def test_webhook_completion_does_not_create_more_follow_up_jobs(self):
        user = User.objects.create_user(username='webhook-user')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.RUNNING,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
            },
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_completed(job, {'delivery_status': 'DELIVERED'})

        self.assertEqual(Job.objects.filter(source_job=job).count(), 0)

    def test_webhook_handler_can_simulate_retryable_failure(self):
        user = User.objects.create_user(username='webhook-failure')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
                'simulate_failure': True,
            },
        )

        with patch('apps.worker.handlers.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'temporary 5xx'):
                dispatch_job(job)

    def test_notification_handler_success(self):
        user = User.objects.create_user(username='notification-user')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.SEND_NOTIFICATION,
            priority=Job.Priority.LOW,
            payload={
                'channel': 'email',
                'recipient': 'user@example.com',
                'message': 'Your refund is complete.',
            },
        )

        with patch('apps.worker.handlers.time.sleep'):
            result = dispatch_job(job)

        self.assertEqual(result['notification_status'], 'SENT')
        self.assertEqual(result['channel'], 'email')
        self.assertEqual(result['notification_id'], f'notification:{job.id}')


class ExternalIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='idempotency-user')

    def test_refund_uses_same_external_key_on_every_retry(self):
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            payload=refund_payload(),
        )

        with patch('apps.worker.handlers.time.sleep'):
            first = dispatch_job(job)
            second = dispatch_job(job)

        expected = f'refund:{job.id}'
        self.assertEqual(first['external_idempotency_key'], expected)
        self.assertEqual(second['external_idempotency_key'], expected)

    def test_webhook_reuses_persisted_event_id(self):
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
                'event_id': 'refund.completed:source-123',
                'data': {'refund_id': 'refund-123'},
            },
        )

        with patch('apps.worker.handlers.time.sleep'):
            first = dispatch_job(job)
            second = dispatch_job(job)

        self.assertEqual(first['event_id'], 'refund.completed:source-123')
        self.assertEqual(second['event_id'], 'refund.completed:source-123')

    def test_notification_reuses_persisted_notification_id(self):
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.SEND_NOTIFICATION,
            priority=Job.Priority.LOW,
            payload={
                'channel': 'email',
                'recipient': 'user@example.com',
                'message': 'Refund complete.',
                'notification_id': 'notification:refund.completed:source-123',
            },
        )

        with patch('apps.worker.handlers.time.sleep'):
            first = dispatch_job(job)
            second = dispatch_job(job)

        self.assertEqual(
            first['notification_id'],
            'notification:refund.completed:source-123',
        )
        self.assertEqual(
            second['notification_id'],
            'notification:refund.completed:source-123',
        )

    def test_fallback_external_ids_are_derived_from_job_id(self):
        webhook = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'manual.test',
            },
        )
        notification = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.SEND_NOTIFICATION,
            priority=Job.Priority.LOW,
            payload={
                'channel': 'email',
                'recipient': 'user@example.com',
                'message': 'Test',
            },
        )

        self.assertEqual(
            get_external_operation_id(webhook),
            f'webhook:{webhook.id}',
        )
        self.assertEqual(
            get_external_operation_id(notification),
            f'notification:{notification.id}',
        )


class StaleJobRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='recovery-user')
        self.redis = FakeRedis()

    def test_expired_running_job_is_reset_to_pending_and_requeued(self):
        now = timezone.now()
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.RUNNING,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
            },
            started_at=now - timedelta(minutes=1),
            lease_expires_at=now - timedelta(seconds=1),
        )

        recovered = recover_stale_running_jobs(
            redis_client=self.redis,
            now=now,
        )
        job.refresh_from_db()

        self.assertEqual(recovered, 1)
        self.assertEqual(job.status, Job.Status.PENDING)
        self.assertIsNone(job.lease_expires_at)
        self.assertIsNotNone(job.started_at)
        self.assertIn('previous external attempt outcome may be unknown', job.failure_reason)
        self.assertIn(
            str(job.id),
            self.redis.sorted_sets[settings.FINQUEUE_JOBS_KEY],
        )

    def test_unexpired_running_job_is_not_recovered(self):
        now = timezone.now()
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.RUNNING,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
            },
            started_at=now,
            lease_expires_at=now + timedelta(seconds=20),
        )

        recovered = recover_stale_running_jobs(
            redis_client=self.redis,
            now=now,
        )
        job.refresh_from_db()

        self.assertEqual(recovered, 0)
        self.assertEqual(job.status, Job.Status.RUNNING)
        self.assertEqual(self.redis.sorted_sets, {})
