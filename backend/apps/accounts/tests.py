from rest_framework import status
from rest_framework.test import APITestCase

from apps.institutions.models import Institution

from .models import User

PASSWORD = 'Str0ng!DevPassw0rd'


class AuthFlowTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Test College', city='Chennai', state='TN')
        self.user = User.objects.create_user(
            email='iqac@test.edu',
            username='iqac_test',
            password=PASSWORD,
            first_name='Test',
            last_name='User',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.institution,
        )

    def _login(self, email=None, password=None):
        return self.client.post('/api/v1/auth/login/', {
            'email': email or self.user.email,
            'password': password or PASSWORD,
        })

    # -- login -----------------------------------------------------------

    def test_login_success_returns_tokens_and_user(self):
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)
        self.assertEqual(response.data['user']['email'], self.user.email)
        self.assertEqual(response.data['user']['role'], User.Role.IQAC_COORDINATOR)
        # the response must never leak the password/hash
        self.assertNotIn('password', response.data['user'])

    def test_login_success_without_trailing_slash_matches_frontend_client(self):
        response = self.client.post('/api/v1/auth/login', {
            'email': self.user.email, 'password': PASSWORD,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.data)

    def test_login_invalid_password(self):
        response = self._login(password='wrong-password')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_unknown_email(self):
        response = self._login(email='nobody@test.edu', password=PASSWORD)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_inactive_user_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_jwt_access_token_carries_role_and_institution_claims(self):
        import jwt as pyjwt
        from django.conf import settings

        response = self._login()
        decoded = pyjwt.decode(
            response.data['access_token'], settings.SIMPLE_JWT['SIGNING_KEY'], algorithms=['HS256'],
        )
        self.assertEqual(decoded['role'], User.Role.IQAC_COORDINATOR)
        self.assertEqual(decoded['institution_id'], str(self.institution.id))
        self.assertNotIn('password', decoded)

    # -- refresh -----------------------------------------------------------

    def test_jwt_refresh_issues_new_access_token(self):
        login = self._login()
        response = self.client.post('/api/v1/auth/refresh/', {'refresh': login.data['refresh_token']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotEqual(response.data['access'], login.data['access_token'])

    def test_jwt_refresh_rejects_garbage_token(self):
        response = self.client.post('/api/v1/auth/refresh/', {'refresh': 'not-a-real-token'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- me ------------------------------------------------------------

    def test_current_user_requires_authentication(self):
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_returns_profile(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['name'], 'Test User')
        self.assertEqual(str(response.data['institution_id']), str(self.institution.id))

    # -- logout ----------------------------------------------------------

    def test_logout_blacklists_refresh_token(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.post('/api/v1/auth/logout/', {'refresh': login.data['refresh_token']})
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        # the blacklisted refresh token can no longer be used
        self.client.credentials()
        replay = self.client.post('/api/v1/auth/refresh/', {'refresh': login.data['refresh_token']})
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_authentication(self):
        response = self.client.post('/api/v1/auth/logout/', {'refresh': 'whatever'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- change password ---------------------------------------------------

    def test_change_password_success(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.post('/api/v1/auth/change-password/', {
            'old_password': PASSWORD, 'new_password': 'AnotherStr0ng!Passw0rd',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AnotherStr0ng!Passw0rd'))

    def test_change_password_wrong_old_password(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.post('/api/v1/auth/change-password/', {
            'old_password': 'not-the-password', 'new_password': 'AnotherStr0ng!Passw0rd',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_change_password_rejects_weak_password(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.post('/api/v1/auth/change-password/', {
            'old_password': PASSWORD, 'new_password': '12345',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
