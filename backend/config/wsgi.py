import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Load the URL configuration (and so every view and the AI SDKs they import) while the worker boots, not on
# its first request: otherwise the first user after a deploy waits several seconds for the imports.
from django.urls import get_resolver  # noqa: E402

get_resolver().url_patterns
