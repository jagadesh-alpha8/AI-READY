from django.urls import path

from .views import (
    ExtractionJobCancelView,
    ExtractionJobDetailView,
    ExtractionJobProcessView,
    PlatformAIUsageView,
    SprintExtractionCancelView,
    SprintExtractionProcessIncompleteView,
)

urlpatterns = [
    path('/usage-report', PlatformAIUsageView.as_view(), name='platform-ai-usage'),
    path('/usage-report/', PlatformAIUsageView.as_view(), name='platform-ai-usage-slash'),
    path('/<uuid:pk>', ExtractionJobDetailView.as_view(), name='extraction-job-detail'),
    path('/<uuid:pk>/', ExtractionJobDetailView.as_view(), name='extraction-job-detail-slash'),
    path('/<uuid:pk>/cancel', ExtractionJobCancelView.as_view(), name='extraction-job-cancel'),
    path('/<uuid:pk>/process', ExtractionJobProcessView.as_view(), name='extraction-job-process'),
    path('/sprints/<uuid:sprint_id>/cancel', SprintExtractionCancelView.as_view(), name='sprint-extraction-cancel'),
    path(
        '/sprints/<uuid:sprint_id>/process-incomplete',
        SprintExtractionProcessIncompleteView.as_view(),
        name='sprint-extraction-process-incomplete',
    ),
]
