from django.test import TestCase
from rest_framework.test import APIClient


class AuthenticationViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_logout_returns_bad_request_for_invalid_refresh_token(self):
        response = self.client.post('/auth/logout/', {'refresh': 'invalid-token'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
