from datetime import date

from rest_framework import serializers

from .models import EvidenceRequest, EvidenceRequestDocument, EvidenceRequestEvent


def _name(user):
    return (user.get_full_name() or user.email) if user else ''


class EvidenceRequestEventSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    action_label = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = EvidenceRequestEvent
        fields = ['id', 'action', 'action_label', 'user', 'user_name', 'note', 'data', 'created_at']
        read_only_fields = fields

    def get_user_name(self, obj):
        return _name(obj.user)


class EvidenceRequestDocumentSerializer(serializers.ModelSerializer):
    document_filename = serializers.SerializerMethodField()
    document_status = serializers.CharField(source='document.status', read_only=True, allow_null=True)
    page_count = serializers.IntegerField(source='document.page_count', read_only=True, allow_null=True)
    submitted_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceRequestDocument
        fields = ['id', 'document', 'document_filename', 'document_status', 'page_count', 'submitted_text',
                  'source_context', 'uploaded_for_request', 'source_page', 'source_snippet', 'note',
                  'submitted_by', 'submitted_by_name', 'analysis_status', 'analysis_outcome', 'analysis_summary',
                  'analysis_quote', 'analysis_page_number', 'analysis_document_reference',
                  'analysis_suggested_value', 'analysis_confidence', 'analysis_error', 'status',
                  'review_reason', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at']
        read_only_fields = fields

    def get_document_filename(self, obj):
        if not obj.document_id:
            return 'Text evidence'
        return obj.document.original_filename or obj.document.title

    def get_submitted_by_name(self, obj):
        return _name(obj.submitted_by)

    def get_reviewed_by_name(self, obj):
        return _name(obj.reviewed_by)


class EvidenceRequestSerializer(serializers.ModelSerializer):
    """List shape: who, what, which fact, status and whether it is overdue."""
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    overdue = serializers.SerializerMethodField()
    requested_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    fact_field_name = serializers.CharField(source='fact.field_name', read_only=True)
    fact_field_key = serializers.CharField(source='fact.field_key', read_only=True)
    fact_value = serializers.JSONField(source='fact.value', read_only=True)
    fact_status = serializers.CharField(source='fact.status', read_only=True)
    sprint_code = serializers.CharField(source='sprint.sprint_code', read_only=True)
    sprint_name = serializers.CharField(source='sprint.name', read_only=True)
    institution_name = serializers.CharField(source='sprint.institution.name', read_only=True)
    evidence_count = serializers.SerializerMethodField()
    responsible_role = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceRequest
        fields = ['id', 'sprint', 'sprint_code', 'sprint_name', 'institution_name', 'fact', 'fact_field_name', 'fact_field_key',
                  'fact_value', 'fact_status', 'description', 'suggested_owner_role', 'requested_by',
                  'requested_by_name', 'assigned_to', 'assigned_to_name', 'due_date', 'overdue', 'status',
                  'status_label', 'evidence_count', 'evidence_needed', 'reason', 'responsible_role',
                  'resolution_note', 'resolved_by', 'resolved_by_name',
                  'resolved_at', 'created_at', 'updated_at']
        read_only_fields = fields

    def get_overdue(self, obj):
        return bool(obj.due_date and not obj.is_resolved and obj.due_date < date.today())

    def get_requested_by_name(self, obj):
        return _name(obj.requested_by)

    def get_assigned_to_name(self, obj):
        return _name(obj.assigned_to)

    def get_resolved_by_name(self, obj):
        return _name(obj.resolved_by)

    def get_evidence_count(self, obj):
        return len(obj.evidence.all())

    def get_responsible_role(self, obj):
        return obj.suggested_owner_role


class SuggestedFactSerializer(serializers.Serializer):
    why = serializers.CharField()
    id = serializers.UUIDField(source='fact.id')
    field_name = serializers.CharField(source='fact.field_name')
    field_key = serializers.CharField(source='fact.field_key')
    value = serializers.JSONField(source='fact.value')
    status = serializers.CharField(source='fact.status')
    document = serializers.UUIDField(source='fact.document_id', allow_null=True)
    source_page = serializers.CharField(source='fact.source_page')
    source_snippet = serializers.CharField(source='fact.source_snippet')
    confidence_score = serializers.FloatField(source='fact.confidence_score')


class EvidenceRequestDetailSerializer(EvidenceRequestSerializer):
    evidence = EvidenceRequestDocumentSerializer(many=True, read_only=True)
    events = EvidenceRequestEventSerializer(many=True, read_only=True)
    fact_source_page = serializers.CharField(source='fact.source_page', read_only=True)
    fact_source_snippet = serializers.CharField(source='fact.source_snippet', read_only=True)
    fact_source_document = serializers.UUIDField(source='fact.source_document_id', read_only=True, allow_null=True)
    suggested_facts = serializers.SerializerMethodField()
    # The fact's gaps (a low-confidence one closes when this request's evidence is accepted).
    fact_gaps = serializers.SerializerMethodField()

    class Meta(EvidenceRequestSerializer.Meta):
        fields = EvidenceRequestSerializer.Meta.fields + [
            'fact_source_page', 'fact_source_snippet', 'fact_source_document', 'evidence', 'events',
            'suggested_facts', 'fact_gaps']
        read_only_fields = fields

    def get_fact_gaps(self, obj):
        return [{'id': str(g.id), 'gap_type': g.gap_type, 'gap_type_label': g.get_gap_type_display(),
                 'title': g.title, 'status': g.status, 'resolution': g.resolution}
                for g in obj.fact.gaps.order_by('-created_at')]

    def get_suggested_facts(self, obj):
        from .evidence_requests import suggested_facts
        return SuggestedFactSerializer(suggested_facts(obj), many=True).data


class EvidenceRequestCreateSerializer(serializers.Serializer):
    """POST /facts/{id}/request-evidence. `description` remains accepted for older clients."""
    description = serializers.CharField(required=False, allow_blank=True, default='')
    evidence_needed = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    comment = serializers.CharField(required=False, allow_blank=True, default='')
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)

    def resolved_description(self):
        d = self.validated_data
        return d.get('description') or d.get('reason') or d.get('comment') or ''


class EvidenceAssignSerializer(serializers.Serializer):
    assigned_to = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, default='')


class EvidenceCommentSerializer(serializers.Serializer):
    note = serializers.CharField()


class EvidenceSubmitSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(required=False, allow_null=True)
    file = serializers.FileField(required=False, allow_null=True)
    submitted_text = serializers.CharField(required=False, allow_blank=True, default='')
    source_context = serializers.CharField(required=False, allow_blank=True, default='')
    document_type = serializers.CharField(required=False, allow_blank=True, default='')
    source_page = serializers.CharField(required=False, allow_blank=True, default='', max_length=50)
    source_snippet = serializers.CharField(required=False, allow_blank=True, default='')
    note = serializers.CharField(required=False, allow_blank=True, default='')
    run_extraction = serializers.BooleanField(required=False, default=True)


class EvidenceReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['accept', 'accept_corrected', 'return', 'reject', 'withdraw'])
    evidence_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    corrected_value = serializers.JSONField(required=False, allow_null=True)
    source_page = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)
    source_snippet = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Legacy clients may still send this; rejection always leaves the request open for more evidence.
    return_to_assignee = serializers.BooleanField(required=False, default=True, write_only=True)


class AssigneeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.SerializerMethodField()
    email = serializers.EmailField()
    role = serializers.CharField()

    def get_name(self, obj):
        return obj.get_full_name() or obj.email
