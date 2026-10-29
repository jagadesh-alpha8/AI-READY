from django.urls import path

from apps.documents.views import (
    SprintDocumentListView,
    SprintDocumentUploadView,
    SprintDriveImportJobListCreateView,
    SprintDriveImportJobStopView,
)
from apps.extraction.views import SprintAIUsageView, SprintExtractionJobListCreateView, SprintProcessingSummaryView
from apps.facts.evidence_views import SprintEvidenceAssigneesView, SprintEvidenceRequestListView
from apps.facts.views import (
    SprintAIQIFAutoCheckView, SprintAIQIFExpertQueueView, SprintAIQIFSummaryView, SprintBulkFactConfirmView,
    SprintFactFacetsView, SprintFactListView, SprintProfileSuggestionView, SprintWorkSummaryView,
)
from apps.facts.verification_views import (
    SprintCorrectionListView, SprintReverifyView, SprintShadowReportView, SprintVerificationSummaryView,
)
from apps.gaps.views import SprintGapFacetsView, SprintGapListView
from apps.recommendations.views import SprintRecommendationGenerateView, SprintRecommendationListView
from apps.reports.views import SprintReportGenerateView, SprintReportListView
from apps.vector_store.views import (
    SprintEvidenceSearchView,
    SprintVectorIndexStatusView,
    SprintVectorIndexView,
)
from apps.scoring.views import (
    SprintBaselineApproveProvisionalView,
    SprintBaselineApproveView,
    SprintBaselineReturnView,
    SprintBaselineReviseView,
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
    path('/<uuid:sprint_id>/processing-summary', SprintProcessingSummaryView.as_view(),
         name='sprint-processing-summary'),
    path('/<uuid:sprint_id>/ai-usage', SprintAIUsageView.as_view(), name='sprint-ai-usage'),
    path('/<uuid:sprint_id>/ai-usage/', SprintAIUsageView.as_view(), name='sprint-ai-usage-slash'),
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
    path(
        '/<uuid:sprint_id>/drive-import-jobs',
        SprintDriveImportJobListCreateView.as_view(),
        name='sprint-drive-import-jobs',
    ),
    path(
        '/<uuid:sprint_id>/drive-import-jobs/',
        SprintDriveImportJobListCreateView.as_view(),
        name='sprint-drive-import-jobs-slash',
    ),
    path(
        '/<uuid:sprint_id>/drive-import-jobs/<uuid:job_id>/stop',
        SprintDriveImportJobStopView.as_view(),
        name='sprint-drive-import-job-stop',
    ),
    path(
        '/<uuid:sprint_id>/drive-import-jobs/<uuid:job_id>/stop/',
        SprintDriveImportJobStopView.as_view(),
        name='sprint-drive-import-job-stop-slash',
    ),
    path('/<uuid:sprint_id>/facts', SprintFactListView.as_view(), name='sprint-facts'),
    path('/<uuid:sprint_id>/facts/facets', SprintFactFacetsView.as_view(), name='sprint-facts-facets'),
    path('/<uuid:sprint_id>/aiqif-summary', SprintAIQIFSummaryView.as_view(), name='sprint-aiqif-summary'),
    path('/<uuid:sprint_id>/aiqif-expert-queue', SprintAIQIFExpertQueueView.as_view(),
         name='sprint-aiqif-expert-queue'),
    path('/<uuid:sprint_id>/aiqif-expert-queue/auto-check', SprintAIQIFAutoCheckView.as_view(),
         name='sprint-aiqif-auto-check'),
    path('/<uuid:sprint_id>/profile-suggestion', SprintProfileSuggestionView.as_view(),
         name='sprint-profile-suggestion'),
    path('/<uuid:sprint_id>/facts/bulk-confirm', SprintBulkFactConfirmView.as_view(),
         name='sprint-facts-bulk-confirm'),
    path('/<uuid:sprint_id>/facts/bulk-confirm/', SprintBulkFactConfirmView.as_view(),
         name='sprint-facts-bulk-confirm-slash'),
    path('/<uuid:sprint_id>/work-summary', SprintWorkSummaryView.as_view(), name='sprint-work-summary'),
    path('/<uuid:sprint_id>/verification/summary', SprintVerificationSummaryView.as_view(),
         name='sprint-verification-summary'),
    path('/<uuid:sprint_id>/verification/shadow-report', SprintShadowReportView.as_view(),
         name='sprint-verification-shadow-report'),
    path('/<uuid:sprint_id>/verification/reverify', SprintReverifyView.as_view(), name='sprint-verification-reverify'),
    path('/<uuid:sprint_id>/fact-corrections', SprintCorrectionListView.as_view(), name='sprint-fact-corrections'),
    path('/<uuid:sprint_id>/evidence-requests', SprintEvidenceRequestListView.as_view(),
         name='sprint-evidence-requests'),
    path('/<uuid:sprint_id>/evidence-requests/assignees', SprintEvidenceAssigneesView.as_view(),
         name='sprint-evidence-assignees'),
    path('/<uuid:sprint_id>/facts/', SprintFactListView.as_view(), name='sprint-facts-slash'),
    path('/<uuid:sprint_id>/gaps', SprintGapListView.as_view(), name='sprint-gaps'),
    path('/<uuid:sprint_id>/gaps/facets', SprintGapFacetsView.as_view(), name='sprint-gaps-facets'),
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
    path('/<uuid:sprint_id>/baseline/revise', SprintBaselineReviseView.as_view(), name='sprint-baseline-revise'),
    path('/<uuid:sprint_id>/baseline/revise/', SprintBaselineReviseView.as_view(), name='sprint-baseline-revise-slash'),
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
    # Vector store: semantic indexing of this sprint's documents, and evidence
    # retrieval over them. Nested here like every other sprint sub-resource, so
    # institution scoping is the same get_authorized_sprint() check.
    path(
        '/<uuid:sprint_id>/vector-index',
        SprintVectorIndexView.as_view(), name='sprint-vector-index',
    ),
    path(
        '/<uuid:sprint_id>/vector-index/',
        SprintVectorIndexView.as_view(), name='sprint-vector-index-slash',
    ),
    path(
        '/<uuid:sprint_id>/vector-index/status',
        SprintVectorIndexStatusView.as_view(), name='sprint-vector-index-status',
    ),
    path(
        '/<uuid:sprint_id>/vector-index/status/',
        SprintVectorIndexStatusView.as_view(), name='sprint-vector-index-status-slash',
    ),
    path(
        '/<uuid:sprint_id>/evidence-search',
        SprintEvidenceSearchView.as_view(), name='sprint-evidence-search',
    ),
    path(
        '/<uuid:sprint_id>/evidence-search/',
        SprintEvidenceSearchView.as_view(), name='sprint-evidence-search-slash',
    ),

    path(
        '/<uuid:sprint_id>/reports/generate', SprintReportGenerateView.as_view(), name='sprint-reports-generate',
    ),
    path(
        '/<uuid:sprint_id>/reports/generate/',
        SprintReportGenerateView.as_view(),
        name='sprint-reports-generate-slash',
    ),
]
