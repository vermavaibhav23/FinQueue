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


@override_settings(FINQUEUE_MAX_RETRIES=3)
class WorkerRetryTests(TestCase):
    def test_failed_job_is_scheduled_for_retry(self):
        user = User.objects.create_user(username='student')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.RUNNING,
            payload={
                'transaction_id': 'txn-1001',
                'amount': 1000,
            },
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_failed(job, 'gateway timeout')
        job.refresh_from_db()

        self.assertEqual(job.status, Job.Status.PENDING)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.failure_reason, 'gateway timeout')

    def test_webhook_handler_can_simulate_retryable_failure(self):
        user = User.objects.create_user(username='webhook-user')
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
