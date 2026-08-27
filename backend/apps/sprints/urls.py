from django.urls import path

from apps.documents.views import SprintDocumentListView, SprintDocumentUploadView
from apps.extraction.views import SprintExtractionJobListCreateView
from apps.facts.views import SprintFactListView
from apps.gaps.views import SprintGapListView
from apps.recommendations.views import SprintRecommendationGenerateView, SprintRecommendationListView
from apps.reports.views import SprintReportGenerateView, SprintReportListView
from apps.scoring.views import (
    SprintBaselineApproveProvisionalView,
    SprintBaselineApproveView,
    SprintBaselineReturnView,
    SprintBaselineView,
    SprintScoreHistoryView,
    SprintScoreView,
)

from .views import SprintViewSet

sprint_list = SprintViewSet.as_view({'get': 'list', 'post': 'create'})
sprint_detail = SprintViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
})
sprint_overview = SprintViewSet.as_view({'get': 'overview'})

urlpatterns = [
    # Registered with and without a trailing slash for the same reason as
    # apps.institutions.urls: the task spec documents .../sprints/, while
    # APPEND_SLASH=False and this project's existing frontend calls
    # '/sprints' without one -- both forms resolve to the same actions.
    path('', sprint_list, name='sprint-list'),
    path('/', sprint_list, name='sprint-list-slash'),
    path('/<uuid:pk>', sprint_detail, name='sprint-detail'),
    path('/<uuid:pk>/', sprint_detail, name='sprint-detail-slash'),
    path('/<uuid:pk>/overview', sprint_overview, name='sprint-overview'),
    path('/<uuid:pk>/overview/', sprint_overview, name='sprint-overview-slash'),

    # Nested sprint sub-resources (documents, facts, gaps, score, ...).
    # documents/, extraction-jobs/, facts/, gaps/, and score/ are
    # dual-registered with/without a trailing slash for the same reason as
    # the sprint routes above (all explicitly spec'd with one); the rest are
    # unaffected by this task and still only registered the way the
    # frontend already calls them.
    path('/<uuid:sprint_id>/documents', SprintDocumentListView.as_view(), name='sprint-documents'),
    path('/<uuid:sprint_id>/documents/', SprintDocumentListView.as_view(), name='sprint-documents-slash'),
    path('/<uuid:sprint_id>/upload-file', SprintDocumentUploadView.as_view(), name='sprint-upload-file'),
    path('/<uuid:sprint_id>/upload-file/', SprintDocumentUploadView.as_view(), name='sprint-upload-file-slash'),
    path(
        '/<uuid:sprint_id>/extraction-jobs',
        SprintExtractionJobListCreateView.as_view(),
        name='sprint-extraction-jobs',
    ),
    path(
        '/<uuid:sprint_id>/extraction-jobs/',
        SprintExtractionJobListCreateView.as_view(),
        name='sprint-extraction-jobs-slash',
    ),
    path('/<uuid:sprint_id>/facts', SprintFactListView.as_view(), name='sprint-facts'),
    path('/<uuid:sprint_id>/facts/', SprintFactListView.as_view(), name='sprint-facts-slash'),
    path('/<uuid:sprint_id>/gaps', SprintGapListView.as_view(), name='sprint-gaps'),
    path('/<uuid:sprint_id>/gaps/', SprintGapListView.as_view(), name='sprint-gaps-slash'),
    path('/<uuid:sprint_id>/score', SprintScoreView.as_view(), name='sprint-score'),
    path('/<uuid:sprint_id>/score/', SprintScoreView.as_view(), name='sprint-score-slash'),
    path('/<uuid:sprint_id>/score/history', SprintScoreHistoryView.as_view(), name='sprint-score-history'),
    path(
        '/<uuid:sprint_id>/score/history/', SprintScoreHistoryView.as_view(), name='sprint-score-history-slash',
    ),
    path('/<uuid:sprint_id>/baseline', SprintBaselineView.as_view(), name='sprint-baseline'),
    path('/<uuid:sprint_id>/baseline/', SprintBaselineView.as_view(), name='sprint-baseline-slash'),
    path(
        '/<uuid:sprint_id>/baseline/approve',
        SprintBaselineApproveView.as_view(),
        name='sprint-baseline-approve',
    ),
    path(
        '/<uuid:sprint_id>/baseline/approve/',
        SprintBaselineApproveView.as_view(),
        name='sprint-baseline-approve-slash',
    ),
    path(
        '/<uuid:sprint_id>/baseline/approve-provisional',
        SprintBaselineApproveProvisionalView.as_view(),
        name='sprint-baseline-approve-provisional',
    ),
    path(
        '/<uuid:sprint_id>/baseline/approve-provisional/',
        SprintBaselineApproveProvisionalView.as_view(),
        name='sprint-baseline-approve-provisional-slash',
    ),
    path(
        '/<uuid:sprint_id>/baseline/return',
        SprintBaselineReturnView.as_view(),
        name='sprint-baseline-return',
    ),
    path(
        '/<uuid:sprint_id>/baseline/return/',
        SprintBaselineReturnView.as_view(),
        name='sprint-baseline-return-slash',
    ),
    path(
        '/<uuid:sprint_id>/recommendations',
        SprintRecommendationListView.as_view(),
        name='sprint-recommendations',
    ),
    path(
        '/<uuid:sprint_id>/recommendations/',
        SprintRecommendationListView.as_view(),
        name='sprint-recommendations-slash',
    ),
    path(
        '/<uuid:sprint_id>/recommendations/generate',
        SprintRecommendationGenerateView.as_view(),
        name='sprint-recommendations-generate',
    ),
    path(
        '/<uuid:sprint_id>/recommendations/generate/',
        SprintRecommendationGenerateView.as_view(),
        name='sprint-recommendations-generate-slash',
    ),
    path('/<uuid:sprint_id>/reports', SprintReportListView.as_view(), name='sprint-reports'),
    path('/<uuid:sprint_id>/reports/', SprintReportListView.as_view(), name='sprint-reports-slash'),
    path(
        '/<uuid:sprint_id>/reports/generate', SprintReportGenerateView.as_view(), name='sprint-reports-generate',
    ),
    path(
        '/<uuid:sprint_id>/reports/generate/',
        SprintReportGenerateView.as_view(),
        name='sprint-reports-generate-slash',
    ),
]
