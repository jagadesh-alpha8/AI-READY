from rest_framework import serializers

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    """Output-only -- reports are never created/edited through this
    serializer (see apps.reports.views/tasks), so no read_only_fields
    bookkeeping is needed."""
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    generated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    pdf_available = serializers.SerializerMethodField()
    docx_available = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            'id', 'sprint_id', 'version', 'status', 'executive_summary', 'overall_cri', 'confidence_score',
            'generated_at', 'generated_by', 'pdf_available', 'docx_available', 'report_data',
            'created_at', 'updated_at',
        ]

    def get_pdf_available(self, obj):
        return bool(obj.pdf_file)

    def get_docx_available(self, obj):
        return bool(obj.docx_file)


class ReportListSerializer(ReportSerializer):
    """Same shape as ReportSerializer but without the (potentially large)
    `report_data` blob -- what GET .../reports/ (list) returns; GET
    .../reports/{id}/ (detail) uses the full serializer."""

    class Meta(ReportSerializer.Meta):
        fields = [f for f in ReportSerializer.Meta.fields if f != 'report_data']
