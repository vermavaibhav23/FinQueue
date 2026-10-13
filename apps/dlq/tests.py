from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.dlq.models import DeadLetterQueue
from apps.dlq.services import requeue_dead_letter_job
from apps.jobs.models import Job, JobHistory


class FakeRedis:
    def __init__(self):
        self.sorted_sets = {}

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)


class DeadLetterQueueTests(TestCase):
    def test_requeue_resets_original_job(self):
        user = User.objects.create_user(username='admin')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.DEAD,
            retry_count=3,
            payload={'transaction_id': 'txn-1', 'amount': 1000},
            failure_reason='refund provider failed',
        )
        dlq_entry = DeadLetterQueue.objects.create(
            original_job=job,
            job_type=job.job_type,
            payload=job.payload,
            failure_reason=job.failure_reason,
            retry_attempts=job.retry_count,
        )

        requeued_job, _ = requeue_dead_letter_job(dlq_entry, redis_client=FakeRedis())

        self.assertEqual(requeued_job.status, Job.Status.PENDING)
        self.assertEqual(requeued_job.retry_count, 0)
        self.assertEqual(requeued_job.processing_round, 2)
        self.assertIsNone(requeued_job.failure_reason)

        history = JobHistory.objects.filter(job=job).latest('created_at')
        self.assertEqual(history.status, Job.Status.PENDING)
        self.assertEqual(history.retry_count, 0)
        self.assertEqual(history.message, 'Requeued from dead-letter queue.')

    def test_duplicate_manual_requeue_does_not_increment_round_twice(self):
        user = User.objects.create_user(username='double-admin-requeue')
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.DEAD,
            payload={'transaction_id': 'txn-2', 'amount': '1000.00'},
        )
        dlq = DeadLetterQueue.objects.create(
            original_job=job, job_type=job.job_type, payload=job.payload,
            failure_reason='failed', retry_attempts=3,
        )
        redis = FakeRedis()
        requeue_dead_letter_job(dlq, redis_client=redis)
        with self.assertRaises(ValidationError):
            requeue_dead_letter_job(dlq, redis_client=redis)

        job.refresh_from_db()
        self.assertEqual(job.processing_round, 2)
        self.assertEqual(job.status, Job.Status.PENDING)

    def test_requeue_of_dead_webhook_reuses_existing_event_round(self):
        user = User.objects.create_user(username='retry-dead-webhook')
        parent = Job.objects.create(
            user=user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            status=Job.Status.COMPLETED,
            processing_round=2,
            payload={'transaction_id': 'txn-3', 'amount': '1000.00'},
        )
        event_id = f'webhook:refund.completed:{parent.id}:round:2'
        job = Job.objects.create(
            user=user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.DEAD,
            source_job=parent,
            source_event='refund.completed',
            processing_round=2,
            payload={'event': 'refund.completed', 'event_id': event_id},
        )
        dlq = DeadLetterQueue.objects.create(
            original_job=job, job_type=job.job_type, payload=job.payload,
            failure_reason='merchant unavailable', retry_attempts=3,
        )
        requeue_dead_letter_job(dlq, redis_client=FakeRedis())

        job.refresh_from_db()
        self.assertEqual(job.processing_round, 2)
        self.assertEqual(job.payload['event_id'], event_id)
        self.assertEqual(job.status, Job.Status.PENDING)
