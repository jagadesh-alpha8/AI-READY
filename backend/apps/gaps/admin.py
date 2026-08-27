from django.contrib import admin

from .models import GapItem


@admin.register(GapItem)
class GapItemAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'sprint', 'gap_type', 'pillar', 'priority', 'status', 'resolved_by', 'created_at',
    ]
    list_filter = ['status', 'gap_type', 'priority', 'pillar']
    search_fields = ['title', 'description']
    autocomplete_fields = ['sprint', 'source_fact', 'related_document', 'resolved_by', 'conflict_fact_b']
    readonly_fields = ['id', 'resolved_at', 'created_at', 'updated_at']
