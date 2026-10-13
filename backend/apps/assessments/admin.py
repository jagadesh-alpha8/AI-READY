from django.contrib import admin

from .models import (
    ApplicableBenchmark, AssessmentCycle, BenchmarkAssessment, BenchmarkProfile, BenchmarkScoreRule, EvidenceItem,
    EvidenceReview, Programme, ScoringModel,
)


@admin.register(AssessmentCycle)
class AssessmentCycleAdmin(admin.ModelAdmin):
    list_display = ['name', 'institution', 'release', 'status', 'opens_on', 'created_at']
    list_filter = ['status']
    readonly_fields = ['release', 'profile_snapshot', 'finalized_by', 'finalized_at']


@admin.register(EvidenceItem)
class EvidenceItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'cycle', 'evidence_type', 'status', 'submitted_by', 'created_at']
    list_filter = ['status']


@admin.register(EvidenceReview)
class EvidenceReviewAdmin(admin.ModelAdmin):
    list_display = ['item', 'decision', 'reviewer', 'reviewed_at']

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register([BenchmarkProfile, Programme, ScoringModel, BenchmarkScoreRule, ApplicableBenchmark,
                     BenchmarkAssessment])
