from django.contrib import admin

from .models import Baseline, BaselineDecisionHistory, Pillar, PillarCriterion, PillarScore, ScoringRun


class PillarCriterionInline(admin.TabularInline):
    model = PillarCriterion
    extra = 0
    fields = ['key', 'name', 'weight', 'fact_field_keys', 'is_active']


@admin.register(Pillar)
class PillarAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'weight', 'display_order', 'is_active']
    list_editable = ['weight', 'display_order', 'is_active']
    ordering = ['display_order', 'key']
    inlines = [PillarCriterionInline]


@admin.register(PillarCriterion)
class PillarCriterionAdmin(admin.ModelAdmin):
    list_display = ['name', 'pillar', 'weight', 'is_active']
    list_filter = ['pillar', 'is_active']
    search_fields = ['name', 'key']


@admin.register(PillarScore)
class PillarScoreAdmin(admin.ModelAdmin):
    list_display = [
        'sprint', 'pillar', 'raw_score', 'weighted_score', 'confidence_score', 'status', 'calculated_at',
    ]
    list_filter = ['status', 'pillar']
    readonly_fields = [
        'id', 'sprint', 'pillar', 'raw_score', 'weighted_score', 'confidence_score', 'status',
        'evidence_count', 'gap_count', 'calculation_version', 'calculated_at',
    ]


@admin.register(ScoringRun)
class ScoringRunAdmin(admin.ModelAdmin):
    list_display = ['sprint', 'overall_cri', 'overall_confidence', 'calculation_version', 'created_at']
    list_filter = ['calculation_version']
    readonly_fields = [
        'id', 'sprint', 'calculation_version', 'overall_cri', 'overall_confidence', 'evidence_count',
        'gap_count', 'pillar_snapshot', 'triggered_by', 'created_at',
    ]


class BaselineDecisionHistoryInline(admin.TabularInline):
    model = BaselineDecisionHistory
    extra = 0
    readonly_fields = ['id', 'action', 'user', 'comments', 'created_at']
    can_delete = False


@admin.register(Baseline)
class BaselineAdmin(admin.ModelAdmin):
    list_display = ['sprint', 'status', 'scoring_run', 'approved_by', 'approved_at', 'created_at']
    list_filter = ['status']
    readonly_fields = [
        'id', 'sprint', 'scoring_run', 'status', 'approved_by', 'approved_at', 'comments', 'created_at',
        'updated_at',
    ]
    inlines = [BaselineDecisionHistoryInline]


# ---------------------------------------------------------------- Follow-up questions about depth (skeleton)
from django.utils import timezone

from .models import DepthJudgment, DepthPastCase, DepthQuestion, DepthResponse


class DepthResponseInline(admin.TabularInline):
    model = DepthResponse
    extra = 0
    fields = ['kind', 'answer', 'document_ids', 'supported', 'submitted_via']


@admin.register(DepthQuestion)
class DepthQuestionAdmin(admin.ModelAdmin):
    list_display = ['run_ref', 'rank', 'kind', 'indicator_code', 'status']
    list_filter = ['kind', 'status']
    search_fields = ['run_ref', 'indicator_code', 'text']
    inlines = [DepthResponseInline]


@admin.register(DepthJudgment)
class DepthJudgmentAdmin(admin.ModelAdmin):
    list_display = ['run_ref', 'condition_id', 'judged_level', 'final_level', 'provisional_credit', 'final_credit']
    list_filter = ['final_level', 'contradicts_evidence', 'relies_on_unsupported']
    search_fields = ['run_ref', 'condition_id']


@admin.register(DepthPastCase)
class DepthPastCaseAdmin(admin.ModelAdmin):
    """Approving past cases (decision 4: who may do this is still open). Only approved cases guide later judgments."""
    list_display = ['condition_id', 'level', 'status', 'reviewed_by', 'spec_version', 'created_at']
    list_filter = ['status', 'level', 'spec_version']
    search_fields = ['condition_id', 'reasoning']
    readonly_fields = ['judgment', 'condition_id', 'level', 'dimension_findings', 'reasoning', 'spec_version',
                       'reviewed_by', 'reviewed_at']
    actions = ['approve', 'reject']

    def _review(self, request, queryset, status):
        queryset.update(status=status, reviewed_by=request.user, reviewed_at=timezone.now())

    @admin.action(description='Approve as a reference for later judgments')
    def approve(self, request, queryset):
        self._review(request, queryset, DepthPastCase.Status.APPROVED)

    @admin.action(description='Reject')
    def reject(self, request, queryset):
        self._review(request, queryset, DepthPastCase.Status.REJECTED)


from .models import DriftLedger, PartCase, PastCaseRelease  # noqa: E402


@admin.register(PartCase)
class PartCaseAdmin(admin.ModelAdmin):
    """Part cases (capability/past_cases.py). Internal: never shown to a college. A person marks the sampled cases by
    setting their finding (person_finding), which makes them anchors for the replay before each release."""
    list_display = ['condition_id', 'part_id', 'source', 'final_finding', 'audit_mark', 'sampled', 'person_finding',
                    'release', 'state', 'created_at']
    list_filter = ['source', 'state', 'audit_mark', 'sampled', 'release']
    search_fields = ['condition_id', 'run_ref']
    fields = ['condition_id', 'part_id', 'run_ref', 'institution', 'source', 'passages_kind', 'passages', 'passes',
              'own_finding', 'final_finding', 'reason', 'audit_mark', 'audit_finding', 'audit_reason', 'audit_model',
              'sampled', 'person_finding', 'review_note', 'reviewed_by', 'reviewed_at', 'release', 'state',
              'withdrawn_reason', 'versions']
    readonly_fields = [f for f in fields if f not in ('person_finding', 'review_note')]

    def save_model(self, request, obj, form, change):
        if 'person_finding' in form.changed_data:
            obj.reviewed_by, obj.reviewed_at = request.user, timezone.now()
        super().save_model(request, obj, form, change)


admin.site.register(PastCaseRelease)
admin.site.register(DriftLedger)
