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

    def test_refund_is_forced_to_high_priority(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.REFUND_PROCESSING,
                'priority': Job.Priority.LOW,
                'payload': {
                    'transaction_id': 'txn-1001',
                    'amount': '1000.00',
                    'webhook_url': 'https://merchant.example/webhooks',
                    'notification': {
                        'channel': 'email',
                        'recipient': 'customer@example.com',
                    },
                },
            },
            context={'request': self.request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.priority, Job.Priority.HIGH)
        self.assertEqual(job.user, self.user)

    def test_refund_requires_follow_up_routing_details(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.REFUND_PROCESSING,
                'payload': {
                    'transaction_id': 'txn-1001',
                    'amount': '1000.00',
                },
            },
            context={'request': self.request},
        )

        self.assertFalse(serializer.is_valid())

    def test_webhook_is_forced_to_medium_priority(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.WEBHOOK_DELIVERY,
                'priority': Job.Priority.HIGH,
                'payload': {
                    'url': 'https://merchant.example/webhooks',
                    'event': 'refund.completed',
                    'data': {'refund_id': 'refund-1'},
                },
            },
            context={'request': self.request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.priority, Job.Priority.MEDIUM)

    def test_notification_is_forced_to_low_priority(self):
        serializer = JobSubmitSerializer(
            data={
                'job_type': Job.JobType.SEND_NOTIFICATION,
                'priority': Job.Priority.HIGH,
                'payload': {
                    'channel': 'email',
                    'recipient': 'user@example.com',
                    'message': 'Your refund is complete.',
                },
            },
            context={'request': self.request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        job = serializer.save()

        self.assertEqual(job.priority, Job.Priority.LOW)

    def test_priority_score_keeps_refund_before_webhook(self):
        refund_job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.REFUND_PROCESSING,
            priority=Job.Priority.HIGH,
            payload={'transaction_id': 'txn-1', 'amount': 1000},
        )
        webhook_job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
            },
        )

        self.assertLess(
            calculate_priority_score(refund_job),
            calculate_priority_score(webhook_job),
        )
