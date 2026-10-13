from rest_framework import serializers

from .models import ExtractionJob


class ExtractionJobSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    document_id = serializers.PrimaryKeyRelatedField(source='document', read_only=True)
    document_filename = serializers.CharField(source='document.original_filename', read_only=True)
    current_step_label = serializers.CharField(source='get_current_step_display', read_only=True)
    # AI tokens and cost of this job (all its attempts). The job list
    # annotates these in one query; anywhere else they're summed per job.
    ai_input_tokens = serializers.SerializerMethodField()
    ai_output_tokens = serializers.SerializerMethodField()
    ai_cost_usd = serializers.SerializerMethodField()

    class Meta:
        model = ExtractionJob
        fields = [
            'id', 'sprint_id', 'document_id', 'document_filename', 'status',
            'current_step', 'current_step_label', 'progress_percentage',
            'started_at', 'completed_at', 'error_message', 'retry_count', 'ai_router',
            'created_at', 'updated_at', 'ai_input_tokens', 'ai_output_tokens', 'ai_cost_usd',
        ]
        read_only_fields = fields

    @staticmethod
    def _usage(obj):
        if not hasattr(obj, 'ai_input_tokens'):
            from django.db.models import Sum
            totals = obj.ai_usage.aggregate(
                ai_input_tokens=Sum('input_tokens'), ai_output_tokens=Sum('output_tokens'), ai_cost_usd=Sum('cost_usd'),
            )
            for key, value in totals.items():
                setattr(obj, key, value)
        return obj

    def get_ai_input_tokens(self, obj):
        return self._usage(obj).ai_input_tokens or 0

    def get_ai_output_tokens(self, obj):
        return self._usage(obj).ai_output_tokens or 0

    def get_ai_cost_usd(self, obj):
        from .usage import money
        return money(self._usage(obj).ai_cost_usd)


class ExtractionJobCreateSerializer(serializers.Serializer):
    """Optional request body for POST /sprints/{id}/extraction-jobs/.

    Omit `document_id` / `document_ids` to (re)process every eligible
    document in the sprint; provide `document_id` to target a single
    document, or `document_ids` for the set the user ticked on the Upload
    Data Pack page.
    """
    document_id = serializers.UUIDField(required=False)
    document_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False, max_length=1000,
    )

    def validate(self, attrs):
        if attrs.get('document_id') and attrs.get('document_ids'):
            raise serializers.ValidationError('Send either document_id or document_ids, not both.')
        return attrs
