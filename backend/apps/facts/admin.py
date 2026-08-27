from django.contrib import admin

from .models import ExtractedFact, FactReviewHistory


class FactReviewHistoryInline(admin.TabularInline):
    model = FactReviewHistory
    extra = 0
    readonly_fields = ['id', 'action', 'original_value', 'new_value', 'user', 'reason', 'created_at']
    can_delete = False
    ordering = ['-created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExtractedFact)
class ExtractedFactAdmin(admin.ModelAdmin):
    list_display = [
        'field_key', 'sprint', 'pillar', 'data_type', 'confidence_score',
        'owner_role', 'status', 'reviewed_by', 'created_at',
    ]
    list_filter = ['status', 'pillar', 'data_type', 'owner_role']
    search_fields = ['field_key', 'field_name', 'source_snippet']
    autocomplete_fields = ['sprint', 'document', 'source_document', 'reviewed_by']
    readonly_fields = ['id', 'reviewed_at', 'created_at', 'updated_at']
    inlines = [FactReviewHistoryInline]


@admin.register(FactReviewHistory)
class FactReviewHistoryAdmin(admin.ModelAdmin):
    list_display = ['fact', 'action', 'user', 'created_at']
    list_filter = ['action']
    search_fields = ['fact__field_key', 'reason']
    autocomplete_fields = ['fact', 'user']
    readonly_fields = ['id', 'original_value', 'new_value', 'created_at']
