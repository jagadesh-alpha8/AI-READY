from django.urls import path

from .evidence_views import (
    EvidenceAssessmentRetryView,
    EvidenceRequestAssignView,
    EvidenceRequestCommentView,
    EvidenceRequestDetailView,
    EvidenceRequestListView,
    EvidenceRequestReviewView,
    EvidenceRequestSubmitView,
    EvidenceRequestSummaryView,
)

urlpatterns = [
    path('', EvidenceRequestListView.as_view(), name='evidence-requests'),
    path('/summary', EvidenceRequestSummaryView.as_view(), name='evidence-request-summary'),
    path('/<uuid:pk>', EvidenceRequestDetailView.as_view(), name='evidence-request-detail'),
    path('/<uuid:pk>/assign', EvidenceRequestAssignView.as_view(), name='evidence-request-assign'),
    path('/<uuid:pk>/comment', EvidenceRequestCommentView.as_view(), name='evidence-request-comment'),
    path('/<uuid:pk>/submit', EvidenceRequestSubmitView.as_view(), name='evidence-request-submit'),
    path('/<uuid:pk>/review', EvidenceRequestReviewView.as_view(), name='evidence-request-review'),
    path('/<uuid:pk>/evidence/<uuid:evidence_id>/retry-assessment', EvidenceAssessmentRetryView.as_view(),
         name='evidence-assessment-retry'),
]
