from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['sprint', 'version', 'status', 'overall_cri', 'confidence_score', 'generated_at']
    list_filter = ['status']
    readonly_fields = [
        'id', 'sprint', 'version', 'report_data', 'pdf_file', 'docx_file', 'generated_by', 'generated_at',
        'created_at', 'updated_at',
    ]
