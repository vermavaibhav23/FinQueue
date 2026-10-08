from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from apps.jobs.models import Job
from apps.worker.engine import WorkerEngine
from apps.worker.handlers import dispatch_job


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
        self.assertEqual(notification.priority, Job.Priority.LOW)
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
            webhook.payload['data']['failure_reason'],
            'refund provider unavailable',
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

        result = dispatch_job(job)

        self.assertEqual(result['notification_status'], 'SENT')
        self.assertEqual(result['channel'], 'email')
