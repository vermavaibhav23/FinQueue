from django.contrib.auth.models import User
from django.test import TestCase

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
        self.assertIsNone(requeued_job.failure_reason)

        history = JobHistory.objects.filter(job=job).latest('created_at')
        self.assertEqual(history.status, Job.Status.PENDING)
        self.assertEqual(history.retry_count, 0)
        self.assertEqual(history.message, 'Requeued from dead-letter queue.')
