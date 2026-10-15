from django.urls import path

from .views import (
    AssessorInputView, CycleActionView, CycleBenchmarkView, CycleDetailView, CycleListView, EvidenceFileView,
    EvidenceReviewView, EvidenceSubmitView, InstitutionListView, ProfileView, ReferenceView, ScorecardView,
    ScoreRuleView,
)

from .views_plan import (
    CyclePlanView, GapView, InitiativeView, SprintDocumentsView, TaskView, TemplateDetailView, TemplateListView,
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
    ('/cycles/<uuid:pk>/plan', CyclePlanView, 'assessment-plan'),
    ('/cycles/<uuid:pk>/sprint-documents', SprintDocumentsView, 'assessment-sprint-documents'),
    ('/cycles/<uuid:pk>/<str:action>', CycleActionView, 'assessment-cycle-action'),
    ('/evidence/<uuid:pk>/file', EvidenceFileView, 'assessment-evidence-file'),
    ('/evidence/<uuid:pk>/review', EvidenceReviewView, 'assessment-evidence-review'),
    ('/gaps/<uuid:pk>', GapView, 'assessment-gap'),
    ('/gaps/<uuid:pk>/validate', GapView, 'assessment-gap-validate'),
    ('/initiatives/<uuid:pk>', InitiativeView, 'assessment-initiative'),
    ('/initiatives/<uuid:pk>/tasks', InitiativeView, 'assessment-initiative-tasks'),
    ('/tasks/<uuid:pk>', TaskView, 'assessment-task'),
    ('/templates', TemplateListView, 'assessment-templates'),
    ('/templates/<uuid:pk>', TemplateDetailView, 'assessment-template'),
    ('/score-rules', ScoreRuleView, 'assessment-score-rules'),
    ('/score-rules/<str:code>', ScoreRuleView, 'assessment-score-rule'),
]

# With and without a trailing slash, like the other apps (APPEND_SLASH=False).
urlpatterns = [p for route, view, name in _routes
               for p in (path(route, view.as_view(), name=name), path(route + '/', view.as_view()))]
