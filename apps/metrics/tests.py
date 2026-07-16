from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.jobs.models import Job


class MetricsViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_metrics_are_scoped_to_the_authenticated_user(self):
        owner = User.objects.create_user(username='owner', password='password123')
        other = User.objects.create_user(username='other', password='password123')

        Job.objects.create(
            user=owner,
            job_type=Job.JobType.PROCESS_PAYMENT,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.PENDING,
            payload={'amount': 1000},
        )
        Job.objects.create(
            user=owner,
            job_type=Job.JobType.FRAUD_CHECK,
            priority=Job.Priority.HIGH,
            status=Job.Status.COMPLETED,
            payload={'amount': 2500},
        )
        Job.objects.create(
            user=other,
            job_type=Job.JobType.PROCESS_PAYMENT,
            priority=Job.Priority.LOW,
            status=Job.Status.DEAD,
            payload={'amount': 3000},
        )

        self.client.force_authenticate(owner)
        response = self.client.get('/metrics/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_jobs'], 2)
        self.assertEqual(response.json()['pending'], 1)
        self.assertEqual(response.json()['completed'], 1)
        self.assertEqual(response.json()['dead'], 0)
