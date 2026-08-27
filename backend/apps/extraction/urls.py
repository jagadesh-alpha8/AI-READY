from django.urls import path

from .views import ExtractionJobDetailView, SprintExtractionCancelView

urlpatterns = [
    path('/<uuid:pk>', ExtractionJobDetailView.as_view(), name='extraction-job-detail'),
    path('/<uuid:pk>/', ExtractionJobDetailView.as_view(), name='extraction-job-detail-slash'),
    path('/sprints/<uuid:sprint_id>/cancel', SprintExtractionCancelView.as_view(), name='sprint-extraction-cancel'),

]
