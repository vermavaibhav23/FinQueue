from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.dlq.models import DeadLetterQueue
from apps.dlq.services import move_to_dead_letter_queue, requeue_dead_letter_job
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
        self.assertFalse(DeadLetterQueue.objects.filter(original_job=job).exists())

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
        self.assertFalse(DeadLetterQueue.objects.filter(pk=dlq.pk).exists())

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
        self.assertFalse(DeadLetterQueue.objects.filter(pk=dlq.pk).exists())

    def test_requeue_then_second_failure_creates_new_single_dlq_row(self):
        user = User.objects.create_user(username='second-failure')
        job = Job.objects.create(
            user=user, job_type=Job.JobType.SEND_NOTIFICATION,
            priority=Job.Priority.LOW, status=Job.Status.DEAD,
            retry_count=3, payload={'channel': 'email'},
            failure_reason='first failure',
        )
        first = DeadLetterQueue.objects.create(
            original_job=job, job_type=job.job_type, payload=job.payload,
            failure_reason='first failure', retry_attempts=3,
        )
        requeue_dead_letter_job(first, redis_client=FakeRedis())
        self.assertFalse(DeadLetterQueue.objects.filter(original_job=job).exists())

        job.refresh_from_db()
        job.status = Job.Status.RUNNING
        job.retry_count = 3
        job.save(update_fields=('status', 'retry_count', 'updated_at'))
        second, follow_ups = move_to_dead_letter_queue(job, 'second failure')
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(follow_ups, [])
        self.assertEqual(DeadLetterQueue.objects.filter(original_job=job).count(), 1)
        self.assertEqual(
            list(JobHistory.objects.filter(job=job).order_by('created_at')
                 .values_list('status', flat=True)),
            [Job.Status.PENDING, Job.Status.DEAD],
        )

        # A stale reference must not requeue the new DEAD attempt.
        with self.assertRaises(ValidationError):
            requeue_dead_letter_job(first, redis_client=FakeRedis())
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.DEAD)
        self.assertTrue(DeadLetterQueue.objects.filter(pk=second.pk).exists())

    def test_one_active_dlq_entry_per_job_enforced_by_database(self):
        user = User.objects.create_user(username='unique-active-dlq')
        job = Job.objects.create(
            user=user, job_type=Job.JobType.SEND_NOTIFICATION,
            priority=Job.Priority.LOW, status=Job.Status.DEAD,
            payload={'channel': 'email'},
        )
        DeadLetterQueue.objects.create(
            original_job=job, job_type=job.job_type, payload=job.payload,
            failure_reason='first failure', retry_attempts=3,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeadLetterQueue.objects.create(
                    original_job=job, job_type=job.job_type, payload=job.payload,
                    failure_reason='duplicate', retry_attempts=3,
                )
