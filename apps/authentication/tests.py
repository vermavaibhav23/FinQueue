from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class AuthenticationViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_logout_returns_bad_request_for_invalid_refresh_token(self):
        response = self.client.post('/auth/logout/', {'refresh': 'invalid-token'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())

    def test_current_user_requires_authentication(self):
        response = self.client.get('/auth/me/')
        self.assertEqual(response.status_code, 401)

    def test_current_user_and_token_refresh(self):
        user = User.objects.create_user(username='merchant', password='safe-password')
        refresh = RefreshToken.for_user(user)
        refreshed = self.client.post('/auth/refresh/', {'refresh': str(refresh)})
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.json()['access']}")
        response = self.client.get('/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], 'merchant')
        self.assertFalse(response.json()['is_staff'])

