from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.jobs.models import Job
from apps.jobs.serializers import JobSubmitSerializer
from apps.jobs.services import calculate_priority_score


class JobSubmitSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student',
            password='password123',
        )
        self.request = APIRequestFactory().post('/jobs/submit/')
        self.request.user = self.user

    def test_fraud_check_is_forced_to_high_priority(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.FRAUD_CHECK,
                'priority': Job.Priority.LOW,
                'payload': {'amount': 75000},
            },
            context={'request': self.request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.priority, Job.Priority.HIGH)
        self.assertEqual(job.user, self.user)

    def test_process_payment_defaults_to_medium_priority(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.PROCESS_PAYMENT,
                'payload': {'amount': 1000},
            },
            context={'request': self.request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.priority, Job.Priority.MEDIUM)

    def test_priority_score_keeps_high_before_medium(self):
        high_job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.FRAUD_CHECK,
            priority=Job.Priority.HIGH,
            payload={'amount': 1000},
        )
        medium_job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.PROCESS_PAYMENT,
            priority=Job.Priority.MEDIUM,
            payload={'amount': 1000},
        )

        self.assertLess(
            calculate_priority_score(high_job),
            calculate_priority_score(medium_job),
        )
