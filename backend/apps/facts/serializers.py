from rest_framework import serializers

from apps.scoring.constants import AIQIF_CRITERION_CODES, AIQIF_INDICATORS, PILLAR_LABELS

from .models import EvidenceRequest, ExtractedFact, FactAIQIFMapping, FactReviewHistory


class FactAIQIFMappingSerializer(serializers.ModelSerializer):
    """One AI-QIF category tag on a fact, with the framework's own code and
    name for its criterion and indicator."""
    criterion_code = serializers.SerializerMethodField()
    criterion_name = serializers.SerializerMethodField()
    indicator_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FactAIQIFMapping
        fields = [
            'id', 'criterion', 'criterion_code', 'criterion_name', 'indicator_code', 'indicator_name',
            'reason', 'confidence', 'status', 'review_status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'review_note', 'relationship', 'source', 'auto_accepted', 'framework_version', 'counts',
            'counts_reason', 'pending', 'pending_since', 'pending_by_name', 'pending_reason', 'auto_decision',
            'auto_reason',
        ]
        read_only_fields = fields

    counts = serializers.SerializerMethodField()
    #: Why it counts or not ("waiting for an expert decision", "the fact is not confirmed yet", ...).
    counts_reason = serializers.SerializerMethodField()
    #: Waiting for an expert decision (in the sprint's AI-QIF expert queue).
    pending = serializers.SerializerMethodField()
    pending_by_name = serializers.SerializerMethodField()

    def get_counts(self, obj):
        """Whether this tag counts toward AI-QIF coverage now (apps/facts/aiqif_tagging.counting_q)."""
        from .aiqif_tagging import count_reason
        return count_reason(obj, obj.fact)[0]

    def get_counts_reason(self, obj):
        from .aiqif_tagging import count_reason
        return count_reason(obj, obj.fact)[1]

    def get_pending(self, obj):
        from .aiqif_tagging import _queued
        return _queued(obj, obj.fact)

    def get_pending_by_name(self, obj):
        return (obj.pending_by.get_full_name() or obj.pending_by.email) if obj.pending_by_id else ''

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by_id else ''

    def get_criterion_code(self, obj):
        return AIQIF_CRITERION_CODES.get(obj.criterion, '')

    def get_criterion_name(self, obj):
        return PILLAR_LABELS.get(obj.criterion, '')

    def get_indicator_name(self, obj):
        return AIQIF_INDICATORS.get(obj.indicator_code, ('', ''))[1]


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
    # The fact's AI-QIF category tags -- separate from `pillar`, which is what
    # the CRI scores the fact under.
    aiqif_mappings = FactAIQIFMappingSerializer(many=True, read_only=True)
    #: True when the system confirmed it (confidence above FACT_AUTO_CONFIRM_MIN_CONFIDENCE), not a person.
    auto_confirmed = serializers.SerializerMethodField()
    #: The gaps whose "Upload Evidence" supplied this fact's document (the original gap).
    evidence_for_gaps = serializers.SerializerMethodField()
    # The fact's unresolved evidence request (apps/facts/evidence_requests.py), or null.
    open_evidence_request = serializers.SerializerMethodField()
    # Responsibility (apps/facts/ownership.py): the owner role, the person assigned and by when, and
    # whether the requesting user may act -- with who may, when not. Only the server's check counts.
    owner_role_label = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    can_act = serializers.SerializerMethodField()
    act_blocked_reason = serializers.SerializerMethodField()
    # Verification (apps/facts/verification/): four results kept apart -- extraction confidence (the model's
    # estimate), grounding (citation + quote, deterministic), validation (deterministic checks) and cross-source.
    verification = serializers.SerializerMethodField()
    # A correction awaiting approval (FactCorrectionProposal), or null.
    pending_correction = serializers.SerializerMethodField()

    class Meta:
        model = ExtractedFact
        fields = [
            'id', 'sprint_id', 'document_id', 'field_name', 'field_key', 'audit_field_id', 'value', 'value_text',
            'value_json', 'normalized_value', 'data_type', 'pillar', 'pillar_label', 'owner_role',
            'source_document_id', 'source_document_filename', 'source_page', 'source_snippet',
            'confidence_score', 'confidence', 'confidence_reason', 'extraction_method', 'status',
            'aiqif_mapping_status', 'aiqif_mappings', 'open_evidence_request', 'auto_confirmed', 'evidence_for_gaps',
            'fact_kind', 'naac_metric', 'profile_field', 'profile_code', 'kind_needs_check', 'kind_reviewed_at',
            'tagging_notes',
            'owner_role_label', 'assigned_to', 'assigned_to_name', 'assigned_at', 'due_date', 'can_act',
            'act_blocked_reason',
            'value_origin', 'original_value', 'original_source_page', 'original_source_snippet', 'derivation',
            'scope', 'verification', 'pending_correction',
            'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def _check(self, obj):
        request = self.context.get('request')
        if request is None or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return None
        from .ownership import check_fact
        return check_fact(request.user, obj)

    def get_owner_role_label(self, obj):
        from .ownership import fact_owner_role, role_label
        return role_label(fact_owner_role(obj)) or 'Coordinators (no owner role)'

    def get_assigned_to_name(self, obj):
        from .ownership import person_name
        return person_name(obj.assigned_to) if obj.assigned_to_id else ''

    def get_can_act(self, obj):
        result = self._check(obj)
        return None if result is None else result[0]

    def get_act_blocked_reason(self, obj):
        result = self._check(obj)
        return '' if result is None else result[1]

    def get_evidence_for_gaps(self, obj):
        if not obj.document_id:
            return []
        # The list view prefetches these for every row at once (SprintFactListView); one query otherwise.
        gaps = getattr(obj.document, 'prefetched_evidence_gaps', None) if obj.document_id else None
        if gaps is None:
            from apps.gaps.models import GapItem
            gaps = GapItem.objects.filter(evidence_documents=obj.document_id).only('id', 'title', 'gap_type', 'status')
        return [{'id': str(g.id), 'title': g.title, 'gap_type': g.gap_type, 'status': g.status} for g in gaps]

    def get_auto_confirmed(self, obj):
        from .auto_confirm import is_auto_confirmed
        return is_auto_confirmed(obj)

    def get_open_evidence_request(self, obj):
        from datetime import date
        pending = getattr(obj, 'open_evidence_requests', None)
        if pending is None:
            pending = list(obj.evidence_requests.filter(status__in=EvidenceRequest.UNRESOLVED)
                           .select_related('assigned_to'))
        if not pending:
            return None
        r = pending[0]
        return {
            'id': str(r.id), 'status': r.status, 'status_label': r.get_status_display(),
            'assigned_to': str(r.assigned_to_id) if r.assigned_to_id else None,
            'assigned_to_name': (r.assigned_to.get_full_name() or r.assigned_to.email) if r.assigned_to else '',
            'due_date': r.due_date, 'overdue': bool(r.due_date and r.due_date < date.today()),
        }

    def get_verification(self, obj):
        if not obj.verification_status:
            return None
        return {
            'status': obj.verification_status, 'status_label': obj.get_verification_status_display(),
            'extraction_confidence': obj.confidence_score, 'grounding': obj.grounding_status,
            'validation': obj.validation_status, 'cross_source': obj.cross_source_status,
            'risk_level': obj.risk_level, 'automation_decision': obj.automation_decision,
            'automation_reason': obj.automation_reason, 'verified_at': obj.verified_at,
        }

    def get_pending_correction(self, obj):
        pending = getattr(obj, 'pending_corrections', None)
        if pending is None:
            pending = list(obj.correction_proposals.filter(status='pending').select_related('submitted_by'))
        if not pending:
            return None
        p = pending[0]
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return {'id': str(p.id), 'proposed_value': p.proposed_value, 'reason': p.reason,
                'source_page': p.source_page, 'submitted_by': str(p.submitted_by_id) if p.submitted_by_id else None,
                'submitted_by_name': (p.submitted_by.get_full_name() or p.submitted_by.email) if p.submitted_by else '',
                'verification_outcome': (p.verification or {}).get('outcome'),
                'mine': bool(user and user.is_authenticated and p.submitted_by_id == user.pk),
                'created_at': p.created_at}

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
        fields = ['id', 'action', 'original_value', 'new_value', 'user', 'user_name', 'reason', 'decision_source',
                  'details', 'created_at']
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


class BulkFactConfirmSerializer(serializers.Serializer):
    """Bounded batch of sprint fact IDs to confirm through the normal review rules."""
    fact_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100,
    )
    comment = serializers.CharField(required=False, allow_blank=True, default='')
    #: Confirm only facts the verification found `verified` (the safe bulk action for exception review).
    only_verified = serializers.BooleanField(required=False, default=False)

    def validate_fact_ids(self, value):
        # A repeated ID should never create repeated review history entries.
        return list(dict.fromkeys(value))


class FactRejectSerializer(_ReasonSerializer):
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


class FactAIQIFMappingReviewSerializer(serializers.Serializer):
    """A reviewer's decision on one AI-QIF tag of a fact."""
    decision = serializers.ChoiceField(choices=['confirm', 'reject'])
    note = serializers.CharField(required=False, allow_blank=True, default='')


class FactAIQIFMappingAddSerializer(serializers.Serializer):
    """A Super Admin adds an AI-QIF tag to a fact (aiqif_tagging.add_tag)."""
    indicator_code = serializers.CharField()
    relationship = serializers.ChoiceField(choices=FactAIQIFMapping.Relationship.choices,
                                           default=FactAIQIFMapping.Relationship.SUPPORTING)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class FactAIQIFMappingEditSerializer(serializers.Serializer):
    """A Super Admin edits a tag (aiqif_tagging.edit_tag): a new indicator / relationship, a note, and optionally
    the decision on the edited mapping."""
    indicator_code = serializers.CharField(required=False, allow_blank=True, default='')
    relationship = serializers.ChoiceField(choices=FactAIQIFMapping.Relationship.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    decision = serializers.ChoiceField(choices=['confirm', 'reject'], required=False)


class FactKindSerializer(serializers.Serializer):
    """A Super Admin decides what a fact is for (aiqif_tagging.decide_kind)."""
    fact_kind = serializers.ChoiceField(choices=ExtractedFact.FactKind.choices)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class AssignSerializer(serializers.Serializer):
    """POST /facts/<id>/assign and /gaps/<id>/assign. assigned_to null = unassign."""
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default='')
