from rest_framework import serializers

from .models import ExtractionJob


class ExtractionJobSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    document_id = serializers.PrimaryKeyRelatedField(source='document', read_only=True)
    document_filename = serializers.CharField(source='document.original_filename', read_only=True)
    current_step_label = serializers.CharField(source='get_current_step_display', read_only=True)

    class Meta:
        model = ExtractionJob
        fields = [
            'id', 'sprint_id', 'document_id', 'document_filename', 'status',
            'current_step', 'current_step_label', 'progress_percentage',
            'started_at', 'completed_at', 'error_message', 'retry_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ExtractionJobCreateSerializer(serializers.Serializer):
    """Optional request body for POST /sprints/{id}/extraction-jobs/.

    Omit `document_id` to (re)process every eligible document in the
    sprint; provide it to target a single document explicitly.
    """
    document_id = serializers.UUIDField(required=False)
