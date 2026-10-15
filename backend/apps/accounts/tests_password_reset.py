"""Forgot password: request a link by email, then set a new password with it."""
import re

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User

PASSWORD = 'Str0ng!DevPassw0rd'
NEW_PASSWORD = 'An0ther!Passw0rd-2026'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   FRONTEND_BASE_URL='https://ai.example.test')
class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='Priya@College.edu', username='priya', password=PASSWORD,
                                             role='consultant')

    def _request(self, email):
        return self.client.post('/api/v1/auth/password-reset', {'email': email})

    def _link(self):
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r'https://ai\.example\.test/reset-password\?uid=([^&\s]+)&token=([^\s"<]+)',
                          mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1), match.group(2)

    def _confirm(self, uid, token, password=NEW_PASSWORD):
        return self.client.post('/api/v1/auth/password-reset/confirm',
                                {'uid': uid, 'token': token, 'new_password': password})

    def test_known_and_unknown_emails_get_the_same_answer(self):
        known = self._request('priya@college.edu')
        unknown = self._request('nobody@college.edu')
        self.assertEqual((known.status_code, unknown.status_code), (200, 200))
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_missing_email_is_a_400(self):
        self.assertEqual(self._request('').status_code, 400)

    def test_inactive_user_gets_no_email(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self._request('priya@college.edu').status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_link_sets_the_new_password_once(self):
        self._request('priya@college.edu')
        uid, token = self._link()
        self.assertEqual(self._confirm(uid, token).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # Used once: the same link no longer works.
        again = self._confirm(uid, token, 'Yet-An0ther!Passw0rd')
        self.assertEqual(again.status_code, 400)
        self.assertIn('token', again.json())

    def test_bad_token_and_bad_uid_are_refused(self):
        self._request('priya@college.edu')
        uid, token = self._link()
        self.assertEqual(self._confirm(uid, token[:-2] + 'xx').status_code, 400)
        self.assertEqual(self._confirm('not-base64!', token).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_weak_password_is_refused(self):
        self._request('priya@college.edu')
        uid, token = self._link()
        response = self._confirm(uid, token, '123')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.json())

    def test_reset_signs_out_everywhere(self):
        login = self.client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': PASSWORD})
        self.assertEqual(login.status_code, 200)
        refresh = login.data['refresh_token']
        self.assertTrue(refresh)
        self._request('priya@college.edu')
        uid, token = self._link()
        self.assertEqual(self._confirm(uid, token).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/refresh/', {'refresh': refresh}).status_code, 401)

    def test_requests_for_one_email_are_limited(self):
        old = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {'password_reset': '100/hour', 'password_reset_email': '3/hour'}
        self.addCleanup(setattr, SimpleRateThrottle, 'THROTTLE_RATES', old)
        codes = [self._request('priya@college.edu').status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertEqual(len(mail.outbox), 3)
