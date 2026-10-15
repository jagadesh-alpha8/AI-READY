"""Small project-wide security helpers.

- `client_ip(request)`: the caller's address, honouring the same proxy count
  DRF's throttles use (REST_FRAMEWORK['NUM_PROXIES'] / TRUSTED_PROXY_COUNT).
- `AdminLoginRateLimitMiddleware`: the Django admin's login form is not a DRF
  view, so the API's login throttle does not cover it. Limits POSTs to
  /admin/login/ per client address (ADMIN_LOGIN_RATE, default 10 per minute).
- `HealthView`: GET /api/v1/health -- database + cache reachable. No login, no
  data; used by the container healthcheck and the deploy job.
"""


from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def client_ip(request):
    num_proxies = settings.REST_FRAMEWORK.get('NUM_PROXIES') or 0
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if num_proxies and xff:
        parts = [p.strip() for p in xff.split(',') if p.strip()]
        if parts:
            return parts[-min(num_proxies, len(parts))]
    return request.META.get('REMOTE_ADDR', '')


def _parse_rate(rate):
    count, _, period = rate.partition('/')
    seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period[0]]
    return int(count), seconds


class AdminLoginRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.limit, self.window = _parse_rate(getattr(settings, 'ADMIN_LOGIN_RATE', '10/minute'))

    def __call__(self, request):
        if request.method == 'POST' and request.path.rstrip('/').endswith('/admin/login'):
            # The window starts at the first attempt and expires `window`
            # seconds later (not on clock-minute boundaries, which would let
            # a burst straddling the boundary through).
            key = f'admin-login:{client_ip(request)}'
            if cache.add(key, 1, self.window):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:  # expired between add() and incr()
                    cache.add(key, 1, self.window)
                    count = 1
            if count > self.limit:
                return HttpResponse('Too many login attempts. Please wait a minute and try again.',
                                    status=429, content_type='text/plain')
        return self.get_response(request)


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checks = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            checks['database'] = 'ok'
        except Exception as exc:  # report, don't raise -- this is the health endpoint
            checks['database'] = f'error: {type(exc).__name__}'
        try:
            cache.set('health:ping', 1, 10)
            checks['cache'] = 'ok' if cache.get('health:ping') == 1 else 'error: no value'
        except Exception as exc:
            checks['cache'] = f'error: {type(exc).__name__}'
        healthy = all(v == 'ok' for v in checks.values())
        return Response({'status': 'ok' if healthy else 'error', **checks}, status=200 if healthy else 503)
