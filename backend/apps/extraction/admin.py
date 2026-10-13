from django.contrib import admin

from .models import AIUsage, ExtractionJob


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'sprint', 'document', 'status', 'current_step',
        'progress_percentage', 'retry_count', 'ai_router', 'created_at',
    ]
    list_filter = ['status', 'current_step', 'ai_router']
    search_fields = ['sprint__sprint_code', 'document__original_filename']
    autocomplete_fields = ['sprint', 'document']
    readonly_fields = [
        'id', 'started_at', 'completed_at', 'retry_count', 'ai_router', 'created_at', 'updated_at',
    ]


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    """Read-only: these are billing records, written only by the AI clients."""
    list_display = [
        'created_at', 'institution', 'sprint', 'stage', 'model',
        'input_tokens', 'output_tokens', 'cost_usd', 'document',
    ]
    list_filter = ['stage', 'model', 'provider', 'institution', ('created_at', admin.DateFieldListFilter)]
    search_fields = ['sprint__sprint_code', 'institution__name', 'document__original_filename', 'model']
    date_hierarchy = 'created_at'
    list_select_related = ['institution', 'sprint', 'document']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
