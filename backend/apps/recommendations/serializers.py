from rest_framework import serializers

from apps.facts.serializers import ExtractedFactSerializer
from apps.scoring.constants import PILLAR_LABELS

from .models import Recommendation


class RecommendationSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    source_gap = serializers.PrimaryKeyRelatedField(read_only=True)
    supporting_facts = ExtractedFactSerializer(many=True, read_only=True)
    pillar_label = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # Aliases of description/expected_cri_lift, kept so the existing
    # (unmodified) frontend's RecommendationsReview.tsx -- which reads
    # rec.edited_text || rec.recommendation_text and rec.expected_score_lift
    # -- keeps working unchanged. `edited_text` is always '' because this
    # engine writes consultant edits directly into `description` (status
    # flips to 'edited' instead -- see RecommendationUpdateSerializer), so
    # the frontend's `||` fallback always resolves to the current text.
    recommendation_text = serializers.CharField(source='description', read_only=True)
    edited_text = serializers.SerializerMethodField()
    expected_score_lift = serializers.FloatField(source='expected_cri_lift', read_only=True)

    class Meta:
        model = Recommendation
        fields = [
            'id', 'sprint_id', 'title', 'description', 'trigger_gap', 'source_gap', 'supporting_facts',
            'pillar', 'pillar_label', 'owner_role', 'priority', 'timeline', 'expected_cri_lift',
            'support_offering', 'consultant_notes', 'status', 'created_by', 'updated_by',
            'created_at', 'updated_at', 'recommendation_text', 'edited_text', 'expected_score_lift',
        ]
        # Only names DRF would otherwise auto-generate as writable belong
        # here -- sprint_id/source_gap/supporting_facts/created_by/updated_by
        # are already read_only via their explicit field declarations above,
        # and listing a field both ways raises an AssertionError.
        read_only_fields = ['id', 'trigger_gap', 'pillar', 'owner_role', 'created_at', 'updated_at']

    def get_pillar_label(self, obj):
        return PILLAR_LABELS.get(obj.pillar, '') if obj.pillar else ''

    def get_edited_text(self, obj):
        return ''


class RecommendationUpdateSerializer(serializers.ModelSerializer):
    """PATCH shape for consultant edits -- only the fields a consultant is
    meant to adjust after reviewing a generated recommendation; the
    trigger/evidence linkage (source_gap, supporting_facts, pillar,
    owner_role) stays as the engine generated it."""

    class Meta:
        model = Recommendation
        fields = [
            'title', 'description', 'priority', 'timeline', 'expected_cri_lift',
            'support_offering', 'consultant_notes', 'status',
        ]

    def validate_expected_cri_lift(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError('expected_cri_lift must be between 0 and 100.')
        return value

    def update(self, instance, validated_data):
        # An explicit status in the payload (e.g. 'accepted', 'hidden',
        # 'completed') always wins; otherwise editing a still-draft
        # recommendation's content is what moves it to 'edited'.
        if 'status' not in validated_data and instance.status == Recommendation.Status.DRAFT:
            validated_data['status'] = Recommendation.Status.EDITED
        return super().update(instance, validated_data)
