from rest_framework import serializers

from apps.scoring.constants import PILLAR_LABELS

from .models import ExtractedFact, FactReviewHistory


class ExtractedFactSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    document_id = serializers.PrimaryKeyRelatedField(source='document', read_only=True)
    source_document_id = serializers.PrimaryKeyRelatedField(source='source_document', read_only=True)
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    pillar_label = serializers.SerializerMethodField()
    # Read-only aliases of field_key/value/confidence_score, kept so the
    # existing (unmodified) frontend's FactsReview.tsx -- which reads
    # fact.audit_field_id/fact.value_json/fact.confidence -- renders real
    # fact data instead of blank cells.
    audit_field_id = serializers.CharField(source='field_key', read_only=True)
    value_json = serializers.JSONField(source='value', read_only=True)
    confidence = serializers.FloatField(source='confidence_score', read_only=True)
    # The frontend's Facts Review table shows which document backs a fact --
    # source_document_id alone (a UUID) isn't renderable, so this adds the
    # one human-readable field a "source document" column actually needs,
    # the same way pillar_label backs the pillar column.
    source_document_filename = serializers.SerializerMethodField()

    class Meta:
        model = ExtractedFact
        fields = [
            'id', 'sprint_id', 'document_id', 'field_name', 'field_key', 'audit_field_id', 'value',
            'value_json', 'normalized_value', 'data_type', 'pillar', 'pillar_label', 'owner_role',
            'source_document_id', 'source_document_filename', 'source_page', 'source_snippet',
            'confidence_score', 'confidence', 'confidence_reason', 'extraction_method', 'status',
            'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_pillar_label(self, obj):
        return PILLAR_LABELS.get(obj.pillar, '') if obj.pillar else ''

    def get_source_document_filename(self, obj):
        if not obj.source_document_id:
            return ''
        return obj.source_document.original_filename or obj.source_document.title


class FactReviewHistorySerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = FactReviewHistory
        fields = ['id', 'action', 'original_value', 'new_value', 'user', 'user_name', 'reason', 'created_at']
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else ''


class ExtractedFactDetailSerializer(ExtractedFactSerializer):
    """Same as ExtractedFactSerializer, plus the full audit trail -- used for
    the single-fact GET and returned after every review action so a caller
    can see the new history entry immediately."""
    review_history = FactReviewHistorySerializer(many=True, read_only=True)

    class Meta(ExtractedFactSerializer.Meta):
        fields = ExtractedFactSerializer.Meta.fields + ['review_history']
        read_only_fields = fields


class _ReasonSerializer(serializers.Serializer):
    """Shared `reason` field for every review action. Also accepts `comment`
    as an alias -- the existing (unmodified) frontend's FactsReview.tsx
    sends `comment`, not `reason`."""
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    comment = serializers.CharField(required=False, allow_blank=True, default='')

    def resolved_reason(self):
        return self.validated_data.get('reason') or self.validated_data.get('comment') or ''


class FactConfirmSerializer(_ReasonSerializer):
    pass


class FactRejectSerializer(_ReasonSerializer):
    pass


class FactEvidenceRequestSerializer(_ReasonSerializer):
    pass


class FactCorrectSerializer(_ReasonSerializer):
    """`new_value` is the canonical field; `corrected_value` is accepted as
    an alias for the same reason as `comment` above (the existing frontend
    sends `corrected_value`)."""
    new_value = serializers.JSONField(required=False, allow_null=True)
    corrected_value = serializers.JSONField(required=False, allow_null=True)

    def validate(self, attrs):
        if 'new_value' not in attrs and 'corrected_value' not in attrs:
            raise serializers.ValidationError({'new_value': 'This field is required.'})
        return attrs

    def resolved_new_value(self):
        if 'new_value' in self.validated_data:
            return self.validated_data['new_value']
        return self.validated_data.get('corrected_value')
