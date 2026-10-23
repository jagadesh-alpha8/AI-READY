"""Slow-request diagnostics: which API endpoints are slow, and whether because of many database queries.

For every /api/ request the middleware measures the wall time and counts database queries (a
connection.execute_wrapper -- works with DEBUG off). It logs one warning line when a request is slower than
API_SLOW_REQUEST_MS or ran more than API_SLOW_REQUEST_QUERIES queries:

    api.slow_request method=GET path=/api/v1/sprints/<id>/facts status=200 ms=1840 queries=12 user=<id>

Only the method, the path (no query string -- it can hold search text), the status, the numbers and the
user id are logged: never SQL, parameters, bodies, document contents, tokens or credentials. With DEBUG on a
`Server-Timing` header (duration and query count only) is added for the browser's network panel.
"""
import logging
import time

from django.conf import settings
from django.db import connection

logger = logging.getLogger('api.performance')


class _QueryCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, execute, sql, params, many, context):
        self.count += 1
        return execute(sql, params, many, context)


class RequestDiagnosticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        counter = _QueryCounter()
        started = time.monotonic()
        with connection.execute_wrapper(counter):
            response = self.get_response(request)
        ms = (time.monotonic() - started) * 1000
        slow_ms = getattr(settings, 'API_SLOW_REQUEST_MS', 1000)
        slow_queries = getattr(settings, 'API_SLOW_REQUEST_QUERIES', 100)
        if ms >= slow_ms or counter.count >= slow_queries:
            user = getattr(request, 'user', None)
            logger.warning('api.slow_request method=%s path=%s status=%s ms=%.0f queries=%d user=%s',
                           request.method, request.path, getattr(response, 'status_code', '?'), ms, counter.count,
                           getattr(user, 'pk', None) if getattr(user, 'is_authenticated', False) else '-')
        if settings.DEBUG:
            response['Server-Timing'] = f'app;dur={ms:.0f}, db;desc="{counter.count} queries"'
        return response
