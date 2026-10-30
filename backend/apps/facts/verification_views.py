"""HTTP endpoints for fact verification, exception review and correction proposals (apps/facts/verification/).

Sprint level (mounted under /api/v1/sprints/<id>/verification...):
    GET  /verification/summary        workload metrics + exception groups (why facts need a person)
    GET  /verification/shadow-report  read-only replay of the rules over decisions people made (staff only)
    POST /verification/reverify       re-run verification on the sprint's unreviewed facts (records results;
                                      the policy applies in FACT_VERIFICATION_MODE -- shadow changes nothing)
    GET  /fact-corrections?status=    correction proposals of the sprint
Fact level (/api/v1/facts/<id>/...):
    GET  /verification                the latest run in full + earlier runs (summary)
    GET|POST /corrections             a fact's proposals / propose one
Proposal level (/api/v1/fact-corrections/<id>/approve|reject|withdraw).

Institution and sprint scoping: every lookup goes through get_authorized_sprint / require_institution_access;
proposals and their documents must belong to the fact's sprint.
"""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import CanReviewFacts, IsInstitutionMember, require_institution_access
from apps.sprints.access import get_authorized_sprint

from .models import ExtractedFact, FactCorrectionProposal, FactVerification
from .verification import corrections, engine, metrics, policy


class FactVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FactVerification
        fields = ['id', 'source', 'mode', 'outcome', 'reason', 'value', 'citation', 'extraction_confidence',
                  'grounding', 'validation', 'derivation', 'cross_source', 'numeric', 'scope', 'ai_assessments', 'risk_level',
                  'precedent', 'automation_decision', 'automation_reason', 'blockers', 'policy_version', 'created_at']
        read_only_fields = fields


class CorrectionProposalSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    field_name = serializers.CharField(source='fact.field_name', read_only=True)
    source_document_name = serializers.SerializerMethodField()
    can_decide = serializers.SerializerMethodField()

    class Meta:
        model = FactCorrectionProposal
        fields = ['id', 'fact', 'field_name', 'value_before', 'status_before', 'proposed_value', 'reason',
                  'source_document', 'source_document_name', 'source_page', 'source_snippet', 'derivation',
                  'verification', 'status', 'submitted_by', 'submitted_by_name', 'reviewed_by', 'reviewed_by_name',
                  'reviewed_at', 'review_reason', 'created_at', 'can_decide']
        read_only_fields = fields

    @staticmethod
    def _name(user):
        return (user.get_full_name() or user.email) if user else ''

    def get_submitted_by_name(self, obj):
        return self._name(obj.submitted_by)

    def get_reviewed_by_name(self, obj):
        return self._name(obj.reviewed_by)

    def get_source_document_name(self, obj):
        return obj.source_document.original_filename if obj.source_document_id else None

    def get_can_decide(self, obj):
        request = self.context.get('request')
        if request is None or obj.status != FactCorrectionProposal.Status.PENDING:
            return False
        if obj.submitted_by_id == request.user.pk:
            return False
        return corrections._may_act(request.user, obj.fact)[0]


class CorrectionCreateSerializer(serializers.Serializer):
    value = serializers.JSONField(allow_null=True)
    reason = serializers.CharField()
    source_document_id = serializers.UUIDField(required=False, allow_null=True)
    source_page = serializers.CharField(required=False, allow_blank=True, default='')
    source_snippet = serializers.CharField(required=False, allow_blank=True, default='')
    derivation = serializers.JSONField(required=False, default=dict)


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


def _error(exc):
    if isinstance(exc, corrections.CorrectionForbidden):
        raise PermissionDenied(str(exc))
    raise ValidationError({'detail': str(exc)})


class SprintVerificationSummaryView(APIView):
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        groups = metrics.exception_queue(sprint)
        limit = 25
        for group in groups:
            group['items'] = group['items'][:limit]
        return Response({'mode': policy.mode(), 'policy_version': engine.POLICY_VERSION,
                         'policy': policy.policy(), 'workload': metrics.workload(sprint), 'groups': groups})


class SprintShadowReportView(APIView):
    """Staff only: replays the rules over this sprint's person-decided facts. Read-only."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        if request.user.role not in User.CROSS_INSTITUTION_ROLES:
            raise PermissionDenied('The shadow report is for InGage staff.')
        sprint = get_authorized_sprint(request.user, sprint_id)
        return Response(metrics.shadow_report(ExtractedFact.objects.filter(sprint=sprint), limit=500))


class SprintReverifyView(APIView):
    permission_classes = [CanReviewFacts]

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        counts = {'checked': 0, 'outcomes': {}}
        for fact in ExtractedFact.objects.filter(sprint=sprint, status=ExtractedFact.Status.EXTRACTED).select_related(
                'source_document', 'document', 'sprint'):
            run = engine.verify_fact(fact, source=FactVerification.Source.REVERIFY, apply_policy=True)
            counts['checked'] += 1
            counts['outcomes'][run.outcome] = counts['outcomes'].get(run.outcome, 0) + 1
        return Response({**counts, 'mode': policy.mode()})


class FactVerificationDetailView(APIView):
    permission_classes = [IsInstitutionMember]

    def get(self, request, pk):
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
        require_institution_access(request.user, fact)
        runs = list(fact.verifications.all()[:10])
        return Response({'fact_id': str(fact.id), 'mode': policy.mode(),
                         'latest': FactVerificationSerializer(runs[0]).data if runs else None,
                         'earlier': [{'id': str(r.id), 'source': r.source, 'outcome': r.outcome, 'reason': r.reason,
                                      'automation_decision': r.automation_decision, 'created_at': r.created_at}
                                     for r in runs[1:]],
                         'precedent': metrics.precedent_for(fact) if fact.status == ExtractedFact.Status.EXTRACTED
                         else None})


class FactCorrectionListCreateView(APIView):
    permission_classes = [IsInstitutionMember]

    def get(self, request, pk):
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
        require_institution_access(request.user, fact)
        return Response(CorrectionProposalSerializer(
            fact.correction_proposals.select_related('submitted_by', 'reviewed_by', 'source_document', 'fact__sprint'),
            many=True, context={'request': request}).data)

    def post(self, request, pk):
        from apps.documents.models import Document
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint', 'source_document', 'document'), pk=pk)
        require_institution_access(request.user, fact)
        body = CorrectionCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        document = None
        if data.get('source_document_id'):
            document = Document.objects.filter(pk=data['source_document_id'], sprint_id=fact.sprint_id).first()
            if document is None:
                raise ValidationError({'detail': 'The supporting document must belong to this sprint.'})
        try:
            proposal = corrections.propose(
                fact, request.user, value=data['value'], reason=data['reason'], source_document=document,
                source_page=data.get('source_page', ''), source_snippet=data.get('source_snippet', ''),
                derivation=data.get('derivation') or {})
        except corrections.CorrectionError as exc:
            _error(exc)
        return Response(CorrectionProposalSerializer(proposal, context={'request': request}).data, status=201)


class SprintCorrectionListView(APIView):
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        rows = FactCorrectionProposal.objects.filter(sprint=sprint).select_related(
            'fact__sprint', 'submitted_by', 'reviewed_by', 'source_document')
        if request.query_params.get('status'):
            rows = rows.filter(status=request.query_params['status'])
        return Response(CorrectionProposalSerializer(rows[:200], many=True, context={'request': request}).data)


class _ProposalActionView(APIView):
    permission_classes = [CanReviewFacts]
    action = None

    def post(self, request, pk):
        proposal = get_object_or_404(FactCorrectionProposal.objects.select_related('fact__sprint'), pk=pk)
        require_institution_access(request.user, proposal.fact)
        body = DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reason = body.validated_data.get('reason', '')
        try:
            if self.action == 'approve':
                proposal = corrections.approve(proposal, request.user, note=reason)
            elif self.action == 'reject':
                proposal = corrections.reject(proposal, request.user, reason=reason)
            else:
                proposal = corrections.withdraw(proposal, request.user)
        except corrections.CorrectionError as exc:
            _error(exc)
        proposal.refresh_from_db()
        return Response(CorrectionProposalSerializer(proposal, context={'request': request}).data)


class CorrectionApproveView(_ProposalActionView):
    action = 'approve'


class CorrectionRejectView(_ProposalActionView):
    action = 'reject'


class CorrectionWithdrawView(_ProposalActionView):
    action = 'withdraw'
