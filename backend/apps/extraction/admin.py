from django.contrib import admin

from .models import ExtractionJob


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'sprint', 'document', 'status', 'current_step',
        'progress_percentage', 'retry_count', 'created_at',
    ]
    list_filter = ['status', 'current_step']
    search_fields = ['sprint__sprint_code', 'document__original_filename']
    autocomplete_fields = ['sprint', 'document']
    readonly_fields = [
        'id', 'started_at', 'completed_at', 'retry_count', 'created_at', 'updated_at',
    ]
