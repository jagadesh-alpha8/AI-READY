from rest_framework import serializers

from apps.scoring.constants import PILLAR_LABELS

from .constants import GAP_PRIORITY_SCORE_PENALTY
from .models import GapItem


class GapItemSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    source_fact_id = serializers.PrimaryKeyRelatedField(source='source_fact', read_only=True)
    related_document_id = serializers.PrimaryKeyRelatedField(source='related_document', read_only=True)
    resolved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # Populated only for gap_type=CONFLICT -- see GapItem's own field
    # comments for why value_a/value_b are immutable snapshots rather than
    # just reading source_fact/conflict_fact_b's *current* value.
    conflict_fact_b_id = serializers.PrimaryKeyRelatedField(source='conflict_fact_b', read_only=True)
    pillar_label = serializers.SerializerMethodField()
    owner_role = serializers.SerializerMethodField()
    # Read-only, derived for the existing (unmodified) frontend's
    # GapDashboard.tsx, which reads gap.audit_field_id and gap.score_impact
    # off each row -- GapItem has neither as a stored column (see
    # apps.gaps.constants' note on why score_impact was removed in favour of
    # deriving it from priority), so both are computed here rather than left
    # blank.
    audit_field_id = serializers.SerializerMethodField()
    score_impact = serializers.SerializerMethodField()

    class Meta:
        model = GapItem
        fields = [
            'id', 'sprint_id', 'gap_type', 'title', 'description', 'pillar', 'pillar_label',
            'priority', 'source_fact_id', 'related_document_id', 'owner_role', 'audit_field_id',
            'score_impact', 'status', 'resolution', 'resolved_by', 'resolved_at', 'created_at', 'updated_at',
            'conflict_fact_b_id', 'conflict_value_a', 'conflict_value_b', 'conflict_confidence',
        ]
        read_only_fields = fields

    def get_pillar_label(self, obj):
        return PILLAR_LABELS.get(obj.pillar, '') if obj.pillar else ''

    def get_owner_role(self, obj):
        """Derived, not stored: whoever owns the linked fact's/document's data
        owns closing the gap it produced."""
        if obj.source_fact_id:
            return obj.source_fact.owner_role
        if obj.related_document_id:
            return obj.related_document.owner_role
        return ''

    def get_audit_field_id(self, obj):
        return obj.source_fact.field_key if obj.source_fact_id else ''

    def get_score_impact(self, obj):
        return GAP_PRIORITY_SCORE_PENALTY.get(obj.priority, 0.0)


class _ResolutionSerializer(serializers.Serializer):
    """Shared `resolution` field for every gap action. Also accepts `value`
    as an alias -- the existing (unmodified) frontend's GapDashboard.tsx
    sends `value`, not `resolution`."""
    resolution = serializers.CharField(required=False, allow_blank=True, default='')
    value = serializers.CharField(required=False, allow_blank=True, default='')

    def resolved_resolution(self):
        return self.validated_data.get('resolution') or self.validated_data.get('value') or ''


class GapResolveSerializer(_ResolutionSerializer):
    pass


class GapMarkUnavailableSerializer(_ResolutionSerializer):
    pass


class GapSkipSerializer(_ResolutionSerializer):
    pass
