from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from apps.jobs.models import Job
from apps.worker.engine import WorkerEngine


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
            job_type=Job.JobType.PROCESS_PAYMENT,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.RUNNING,
            payload={'amount': 1000},
        )
        engine = WorkerEngine()
        engine.redis_client = FakeRedis()

        engine.mark_failed(job, 'gateway timeout')
        job.refresh_from_db()

        self.assertEqual(job.status, Job.Status.PENDING)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.failure_reason, 'gateway timeout')
