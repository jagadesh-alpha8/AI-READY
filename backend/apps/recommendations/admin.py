from django.contrib import admin

from .models import Recommendation


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ['sprint', 'pillar', 'owner_role', 'priority', 'expected_cri_lift', 'status', 'created_at']
    list_filter = ['status', 'priority', 'pillar']
    readonly_fields = ['id', 'source_gap', 'supporting_facts', 'created_by', 'created_at', 'updated_at']
