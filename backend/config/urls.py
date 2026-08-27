from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/schema', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API v1 — every prefix below is deliberately slash-free (see APPEND_SLASH
    # in settings) to match the frontend's axios client exactly.
    path('api/v1/auth/', include('apps.accounts.urls')),
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
]

if settings.DEBUG:
    # Deliberately NOT serving MEDIA_URL here: uploaded documents (NAAC SSR,
    # faculty lists, etc.) are institution-confidential, and static() serves
    # a directory with no authentication or authorization check at all.
    # Document downloads go exclusively through the authenticated
    # /api/v1/documents/{id}/download endpoint (see apps.documents.views).
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)