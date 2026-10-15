from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from config.security import HealthView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health', HealthView.as_view(), name='health'),

    # API v1 — every prefix below is deliberately slash-free (see APPEND_SLASH
    # in settings) to match the frontend's axios client exactly.
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/users', include('apps.accounts.user_urls')),
    path('api/v1/institutions', include('apps.institutions.urls')),
    path('api/v1/sprints', include('apps.sprints.urls')),
    path('api/v1/documents', include('apps.documents.urls')),
    path('api/v1/extraction-jobs', include('apps.extraction.urls')),
    path('api/v1/facts', include('apps.facts.urls')),
    path('api/v1/gaps', include('apps.gaps.urls')),
    path('api/v1/scoring', include('apps.scoring.urls')),
    path('api/v1/recommendations', include('apps.recommendations.urls')),
    path('api/v1/reports', include('apps.reports.urls')),
    path('api/v1/dashboard', include('apps.dashboard.urls')),
    path('api/v1/benchmarks', include('apps.benchmarks.urls')),
    path('api/v1/assessments', include('apps.assessments.urls')),
]

if settings.DEBUG:
    # Deliberately NOT serving MEDIA_URL here: uploaded documents (NAAC SSR,
    # faculty lists, etc.) are institution-confidential, and static() serves
    # a directory with no authentication or authorization check at all.
    # Document downloads go exclusively through the authenticated
    # /api/v1/documents/{id}/download endpoint (see apps.documents.views).
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# API documentation -- only when API_DOCS_ENABLED (default: on with DEBUG, off
# in production), because it maps every endpoint for anyone who finds it.
if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path('api/schema', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/redoc', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]
