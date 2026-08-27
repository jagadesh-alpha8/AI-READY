from django.contrib import admin

from .models import Sprint


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = [
        'sprint_code', 'name', 'institution', 'mode', 'status',
        'completion_percentage', 'overall_cri', 'confidence_score', 'created_at',
    ]
    list_filter = ['mode', 'status', 'institution']
    search_fields = ['sprint_code', 'name', 'institution__name']
    readonly_fields = ['id', 'sprint_code', 'overall_cri', 'confidence_score', 'created_at', 'updated_at']
    autocomplete_fields = ['institution', 'created_by']
