from django.urls import path

from .views import (
    AssessorInputView, CycleActionView, CycleBenchmarkView, CycleDetailView, CycleListView, EvidenceFileView,
    EvidenceReviewView, EvidenceSubmitView, InstitutionListView, ProfileView, ReferenceView, ScorecardView,
    ScoreRuleView,
)

_routes = [
    ('/reference', ReferenceView, 'assessment-reference'),
    ('/institutions', InstitutionListView, 'assessment-institutions'),
    ('/institutions/<uuid:pk>/profile', ProfileView, 'assessment-profile'),
    ('/cycles', CycleListView, 'assessment-cycles'),
    ('/cycles/<uuid:pk>', CycleDetailView, 'assessment-cycle'),
    ('/cycles/<uuid:pk>/scorecard', ScorecardView, 'assessment-scorecard'),
    ('/cycles/<uuid:pk>/benchmarks/<str:code>', CycleBenchmarkView, 'assessment-benchmark'),
    ('/cycles/<uuid:pk>/benchmarks/<str:code>/evidence', EvidenceSubmitView, 'assessment-evidence-submit'),
    ('/cycles/<uuid:pk>/benchmarks/<str:code>/assessment', AssessorInputView, 'assessment-assessor-input'),
    ('/cycles/<uuid:pk>/<str:action>', CycleActionView, 'assessment-cycle-action'),
    ('/evidence/<uuid:pk>/file', EvidenceFileView, 'assessment-evidence-file'),
    ('/evidence/<uuid:pk>/review', EvidenceReviewView, 'assessment-evidence-review'),
    ('/score-rules', ScoreRuleView, 'assessment-score-rules'),
    ('/score-rules/<str:code>', ScoreRuleView, 'assessment-score-rule'),
]

# With and without a trailing slash, like the other apps (APPEND_SLASH=False).
urlpatterns = [p for route, view, name in _routes
               for p in (path(route, view.as_view(), name=name), path(route + '/', view.as_view()))]
