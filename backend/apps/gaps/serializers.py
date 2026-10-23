from datetime import date

from django.db.models import Prefetch
from rest_framework import serializers

from apps.facts.models import EvidenceRequest

from apps.scoring.constants import PILLAR_LABELS

from .constants import GAP_PRIORITY_SCORE_PENALTY
from .models import GapEvent, GapItem
from .services import close_block, resolve_block


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
    # The document the gap was raised from, for the dashboard's Source column.
    source_document_filename = serializers.SerializerMethodField()
    # The linked fact's review status, and its most recent evidence request (open or decided) with the
    # person it is actually assigned to -- `owner_role` above is only the role that owns the data.
    fact_status = serializers.SerializerMethodField()
    evidence_request = serializers.SerializerMethodField()
    # Why Resolve / Skip / Mark unavailable are refused right now ('' = allowed); see services.py.
    resolve_blocked_reason = serializers.SerializerMethodField()
    close_blocked_reason = serializers.SerializerMethodField()
    # Conflict gaps only: the two sides to compare (see get_conflict_sides); null for other gap types.
    conflict_sides = serializers.SerializerMethodField()
    # The linked fact's own citation, for the dashboard's Source Snippet column: exactly as stored on the
    # fact, null when the gap has no fact or the fact has none (never filled in).
    source_snippet = serializers.SerializerMethodField()
    source_page = serializers.SerializerMethodField()
    # Responsibility (apps/facts/ownership.py): owner role in words, the person assigned, and whether the
    # requesting user may resolve / close it -- with who may, when not. Only the server's check counts.
    owner_role_label = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    can_act = serializers.SerializerMethodField()
    act_blocked_reason = serializers.SerializerMethodField()
    # Upload Evidence (gaps/evidence_upload.py): eligibility, the requested document type, and where it stands.
    can_upload_evidence = serializers.SerializerMethodField()
    requested_document_type = serializers.SerializerMethodField()
    evidence_state = serializers.SerializerMethodField()

    #: For list views: each fact's evidence requests, newest first, in one query.
    EVIDENCE_REQUESTS_PREFETCH = Prefetch(
        'source_fact__evidence_requests', to_attr='gap_evidence_requests',
        queryset=EvidenceRequest.objects.select_related('assigned_to').order_by('-created_at'),
    )

    class Meta:
        model = GapItem
        fields = [
            'id', 'sprint_id', 'gap_type', 'title', 'description', 'pillar', 'pillar_label',
            'priority', 'source_fact_id', 'related_document_id', 'source_document_filename', 'owner_role', 'audit_field_id',
            'score_impact', 'status', 'resolution', 'resolved_by', 'resolved_at', 'created_at', 'updated_at',
            'conflict_fact_b_id', 'conflict_value_a', 'conflict_value_b', 'conflict_confidence',
            'fact_status', 'evidence_request', 'resolve_blocked_reason', 'close_blocked_reason',
            'conflict_sides', 'source_snippet', 'source_page',
            'owner_role_label', 'assigned_to', 'assigned_to_name', 'assigned_at', 'due_date', 'can_act',
            'act_blocked_reason', 'can_upload_evidence', 'requested_document_type', 'evidence_state',
        ]
        read_only_fields = fields

    def _requests(self, obj):
        fact = obj.source_fact
        if fact is None:
            return []
        if getattr(fact, 'gap_evidence_requests', None) is None:  # not prefetched: one query, then cached
            fact.gap_evidence_requests = list(
                fact.evidence_requests.select_related('assigned_to').order_by('-created_at'))
        return fact.gap_evidence_requests

    def _has_open_request(self, obj):
        return any(r.status in EvidenceRequest.UNRESOLVED for r in self._requests(obj))

    def get_can_upload_evidence(self, obj):
        from .evidence_upload import ELIGIBLE_TYPES
        return obj.gap_type in ELIGIBLE_TYPES and obj.status in GapItem.ACTIVE_STATUSES

    def get_requested_document_type(self, obj):
        from .evidence_upload import ELIGIBLE_TYPES, requested_document_type
        return requested_document_type(obj) if obj.gap_type in ELIGIBLE_TYPES else ''

    def get_evidence_state(self, obj):
        from .evidence_upload import ELIGIBLE_TYPES, evidence_state
        if obj.gap_type not in ELIGIBLE_TYPES:
            return None
        return evidence_state(obj, requests=self._requests(obj))

    def get_fact_status(self, obj):
        return obj.source_fact.status if obj.source_fact_id else ''

    def get_evidence_request(self, obj):
        requests = self._requests(obj)
        if not requests:
            return None
        r = requests[0]
        return {
            'id': str(r.id), 'status': r.status, 'status_label': r.get_status_display(),
            'assigned_to': str(r.assigned_to_id) if r.assigned_to_id else None,
            'assigned_to_name': (r.assigned_to.get_full_name() or r.assigned_to.email) if r.assigned_to else '',
            'due_date': r.due_date, 'overdue': bool(r.due_date and not r.is_resolved and r.due_date < date.today()),
        }

    def get_resolve_blocked_reason(self, obj):
        if obj.status not in GapItem.ACTIVE_STATUSES:
            return ''
        return resolve_block(obj, has_open_request=self._has_open_request(obj))

    def get_close_blocked_reason(self, obj):
        """What stops Skip / Mark unavailable besides the reason they always need."""
        if obj.status not in GapItem.ACTIVE_STATUSES:
            return ''
        return close_block(obj, 'a reason', has_open_request=self._has_open_request(obj))

    def _check(self, obj):
        request = self.context.get('request')
        if request is None or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return None
        from apps.facts.ownership import check_gap
        return check_gap(request.user, obj)

    def get_owner_role_label(self, obj):
        from apps.facts.ownership import gap_owner_role, role_label
        return role_label(gap_owner_role(obj)) or 'Coordinators (no owner role)'

    def get_assigned_to_name(self, obj):
        from apps.facts.ownership import person_name
        return person_name(obj.assigned_to) if obj.assigned_to_id else ''

    def get_can_act(self, obj):
        result = self._check(obj)
        return None if result is None else result[0]

    def get_act_blocked_reason(self, obj):
        result = self._check(obj)
        return '' if result is None else result[1]

    def get_conflict_sides(self, obj):
        """Side A is `source_fact`, side B `conflict_fact_b`; `value_at_detection` is the stored snapshot
        (conflict_value_a/b). Only what is recorded is returned -- a missing fact, document, page,
        snippet or snapshot is null, never filled in. A gap raised by the end-of-sprint detector
        (apps.gaps.services._detect_conflicting_facts) has no side B or snapshots at all."""
        if obj.gap_type != GapItem.GapType.CONFLICT:
            return None
        fact_b = obj.conflict_fact_b
        if fact_b is not None and fact_b.sprint_id != obj.sprint_id:
            fact_b = None  # never expose a fact from outside the gap's own sprint
        return [
            _conflict_side('A', obj.source_fact, obj.conflict_value_a),
            _conflict_side('B', fact_b, obj.conflict_value_b),
        ]

    def get_pillar_label(self, obj):
        return PILLAR_LABELS.get(obj.pillar, '') if obj.pillar else ''

    def get_owner_role(self, obj):
        """Derived, not stored: whoever owns the linked fact's/document's data
        owns closing the gap it produced."""
        if obj.source_fact_id:
            return obj.source_fact.owner_role
        if obj.related_document_id:
            return obj.related_document.owner_role
        if obj.gap_type == GapItem.GapType.MISSING_DOCUMENT:
            # The upload checklist's owner of the missing document type (apps/facts/ownership.py).
            from apps.facts.ownership import checklist_owner_role
            from .services import missing_document_type
            return checklist_owner_role(missing_document_type(obj))
        return ''

    def get_source_document_filename(self, obj):
        document = None
        if obj.source_fact_id:
            document = obj.source_fact.source_document or obj.source_fact.document
        if document is None and obj.related_document_id:
            document = obj.related_document
        if document is None:
            return ''
        return document.original_filename or document.title

    def get_source_snippet(self, obj):
        return (obj.source_fact.source_snippet or None) if obj.source_fact_id else None

    def get_source_page(self, obj):
        return (obj.source_fact.source_page or None) if obj.source_fact_id else None

    def get_audit_field_id(self, obj):
        return obj.source_fact.field_key if obj.source_fact_id else ''

    def get_score_impact(self, obj):
        return GAP_PRIORITY_SCORE_PENALTY.get(obj.priority, 0.0)


def _conflict_side(label, fact, snapshot):
    if fact is None:
        return {'side': label, 'fact_id': None, 'field_name': '', 'value_at_detection': snapshot,
                'current_value': None, 'fact_status': '', 'document_id': None, 'document_name': None,
                'page': None, 'snippet': None, 'confidence_score': None}
    # The citation the fact carries now (its evidence document, else the one it was extracted from).
    document = fact.source_document or fact.document
    return {
        'side': label, 'fact_id': str(fact.id), 'field_name': fact.field_name or fact.field_key,
        'value_at_detection': snapshot, 'current_value': fact.value, 'fact_status': fact.status,
        'document_id': str(document.id) if document else None,
        'document_name': (document.original_filename or document.title or None) if document else None,
        'page': fact.source_page or None, 'snippet': fact.source_snippet or None,
        'confidence_score': fact.confidence_score,
    }


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


class GapEventSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source='get_action_display', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = GapEvent
        fields = ['id', 'action', 'action_label', 'user', 'user_name', 'note', 'data', 'created_at']
        read_only_fields = fields

    def get_user_name(self, obj):
        return (obj.user.get_full_name() or obj.user.email) if obj.user_id else ''


class GapItemDetailSerializer(GapItemSerializer):
    """One gap with its history (GET /gaps/<id>). For a conflict: every competing value (all facts of the field
    when the conflict recorded only one side) and whether the user may choose the correct one."""
    events = GapEventSerializer(many=True, read_only=True)
    conflict_candidates = serializers.SerializerMethodField()
    can_choose_value = serializers.SerializerMethodField()
    choose_value_blocked_reason = serializers.SerializerMethodField()

    class Meta(GapItemSerializer.Meta):
        fields = GapItemSerializer.Meta.fields + ['events', 'conflict_candidates', 'can_choose_value',
                                                  'choose_value_blocked_reason']
        read_only_fields = fields

    def get_conflict_candidates(self, obj):
        if obj.gap_type != GapItem.GapType.CONFLICT:
            return None
        from .services import conflict_facts
        facts = [f for f in conflict_facts(obj) if f.sprint_id == obj.sprint_id]
        return [_conflict_side(chr(ord('A') + i), f, None) for i, f in enumerate(facts)]

    def _choice(self, obj):
        request = self.context.get('request')
        if obj.gap_type != GapItem.GapType.CONFLICT or request is None or not request.user.is_authenticated:
            return False, ''
        if obj.status not in GapItem.ACTIVE_STATUSES:
            return False, 'This conflict is already closed.'
        from apps.facts.ownership import check_conflict_choice
        return check_conflict_choice(request.user, obj)

    def get_can_choose_value(self, obj):
        return self._choice(obj)[0]

    def get_choose_value_blocked_reason(self, obj):
        return self._choice(obj)[1]
