from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from apps.jobs.models import IdempotencyRequest, Job
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



class JobSubmissionIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='merchant',
            password='password123',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = '/jobs/submit/'
        self.payload = {
            'job_type': Job.JobType.REFUND_PROCESSING,
            'payload': {
                'transaction_id': 'txn-1001',
                'amount': '1000.00',
                'webhook_url': 'https://merchant.example/webhooks',
                'notification': {
                    'channel': 'email',
                    'recipient': 'customer@example.com',
                },
            },
        }

    def test_same_key_and_same_request_returns_existing_job(self):
        from unittest.mock import patch

        with patch('apps.jobs.views.check_job_submission_rate_limit'):
            first = self.client.post(
                self.url,
                self.payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY='refund-1001',
            )
            second = self.client.post(
                self.url,
                self.payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY='refund-1001',
            )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertFalse(first.json()['idempotent_replay'])
        self.assertTrue(second.json()['idempotent_replay'])
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(IdempotencyRequest.objects.count(), 1)

    def test_same_key_with_different_request_is_rejected(self):
        from unittest.mock import patch

        changed_payload = {
            **self.payload,
            'payload': {
                **self.payload['payload'],
                'amount': '5000.00',
            },
        }

        with patch('apps.jobs.views.check_job_submission_rate_limit'):
            first = self.client.post(
                self.url,
                self.payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY='refund-1001',
            )
            second = self.client.post(
                self.url,
                changed_payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY='refund-1001',
            )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(IdempotencyRequest.objects.count(), 1)

    def test_missing_idempotency_key_is_rejected(self):
        response = self.client.post(
            self.url,
            self.payload,
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Job.objects.count(), 0)


class JobCancellationSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='cancel-user',
            password='password123',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_recovered_or_retried_pending_job_cannot_be_hard_deleted(self):
        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.PENDING,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'refund.completed',
            },
            started_at=__import__('django.utils.timezone', fromlist=['now']).now(),
        )

        response = self.client.delete(f'/jobs/{job.id}/')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Job.objects.filter(id=job.id).exists())

    def test_never_started_pending_job_can_be_cancelled(self):
        from unittest.mock import patch

        job = Job.objects.create(
            user=self.user,
            job_type=Job.JobType.WEBHOOK_DELIVERY,
            priority=Job.Priority.MEDIUM,
            status=Job.Status.PENDING,
            payload={
                'url': 'https://merchant.example/webhooks',
                'event': 'manual.test',
            },
        )

        with patch('apps.jobs.views.remove_job_from_queues'):
            response = self.client.delete(f'/jobs/{job.id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Job.objects.filter(id=job.id).exists())
