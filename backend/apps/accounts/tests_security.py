"""Brute-force limits on sign-in, the admin login limit, the health endpoint,
and API docs being off in production."""
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import resolve, Resolver404
from rest_framework.settings import api_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User

PASSWORD = 'Str0ng!DevPassw0rd'
REAL_RATES = {'login': '3/minute', 'login_email': '5/hour', 'password_change': '10/hour'}


class _RealRates:
    """Use small, real throttle rates (tests normally run with them lifted)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self._old = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = REAL_RATES
        self.addCleanup(setattr, SimpleRateThrottle, 'THROTTLE_RATES', self._old)
        self.addCleanup(cache.clear)


class LoginThrottleTests(_RealRates, APITestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_user(email='a@ingage.ai', username='a', password=PASSWORD, role='consultant')

    def _login(self, email, password='wrong', ip='203.0.113.5'):
        return self.client.post('/api/v1/auth/login/', {'email': email, 'password': password}, REMOTE_ADDR=ip)

    def test_too_many_attempts_from_one_address_are_refused(self):
        codes = [self._login(f'x{i}@ingage.ai').status_code for i in range(4)]
        self.assertEqual(codes, [400, 400, 400, 429])

    def test_one_email_is_limited_across_addresses(self):
        codes = [self._login('a@ingage.ai', ip=f'198.51.100.{i}').status_code for i in range(6)]
        self.assertEqual(codes[:5], [400] * 5)
        self.assertEqual(codes[5], 429)

    def test_correct_password_still_works_under_the_limit(self):
        self.assertEqual(self._login('a@ingage.ai', password=PASSWORD).status_code, 200)

    @override_settings(REST_FRAMEWORK={**__import__('django.conf').conf.settings.REST_FRAMEWORK, 'NUM_PROXIES': 1})
    def test_behind_nginx_each_client_gets_its_own_bucket(self):
        api_settings.reload()
        self.addCleanup(api_settings.reload)
        nginx = '172.18.0.5'
        for i in range(3):
            self.client.post('/api/v1/auth/login/', {'email': f'y{i}@ingage.ai', 'password': 'x'},
                             REMOTE_ADDR=nginx, HTTP_X_FORWARDED_FOR='203.0.113.9')
        other = self.client.post('/api/v1/auth/login/', {'email': 'z@ingage.ai', 'password': 'x'},
                                 REMOTE_ADDR=nginx, HTTP_X_FORWARDED_FOR='203.0.113.77')
        self.assertEqual(other.status_code, 400)  # a different client is not blocked


@override_settings(ADMIN_LOGIN_RATE='2/minute')
class AdminLoginLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_admin_login_posts_are_limited(self):
        codes = [self.client.post('/admin/login/', {'username': 'x', 'password': 'y'}).status_code for _ in range(3)]
        self.assertEqual(codes[2], 429)
        self.assertNotEqual(codes[0], 429)


class HealthTests(APITestCase):
    def test_health_needs_no_login_and_reports_ok(self):
        r = self.client.get('/api/v1/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'status': 'ok', 'database': 'ok', 'cache': 'ok'})


class ApiDocsTests(TestCase):
    def test_docs_follow_the_setting(self):
        from django.conf import settings
        try:
            resolve('/api/docs')
            registered = True
        except Resolver404:
            registered = False
        self.assertEqual(registered, settings.API_DOCS_ENABLED)
