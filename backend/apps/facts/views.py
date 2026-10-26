from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from django.db.models import Prefetch, Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import (
    CanReviewFacts, IsInstitutionMember, IsSuperAdmin, require_institution_access,
)
from apps.gaps.models import GapItem
from apps.gaps.services import after_fact_review
from apps.sprints.access import get_authorized_sprint
from config.pagination import DefaultPageNumberPagination, OptionalPageNumberPagination

from .filters import ExtractedFactFilter
from . import evidence_requests, ownership
from .evidence_serializers import EvidenceRequestCreateSerializer
from .models import EvidenceRequest, ExtractedFact, FactAIQIFMapping, FactReviewHistory
from .serializers import (
    BulkFactConfirmSerializer,
    ExtractedFactDetailSerializer,
    ExtractedFactSerializer,
    FactAIQIFMappingReviewSerializer,
    FactConfirmSerializer,
    FactCorrectSerializer,
    FactRejectSerializer,
)


class SprintFactListView(generics.ListAPIView):
    """Read-only: facts are only ever created by the extraction pipeline."""
    serializer_class = ExtractedFactSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = ExtractedFactFilter
    ordering_fields = ['created_at', 'updated_at', 'confidence_score', 'reviewed_at', 'field_key']
    ordering = ['-created_at', 'id']
    # Always paginated (50 per page, at most 100): a sprint has hundreds of facts.
    pagination_class = DefaultPageNumberPagination

    def get_queryset(self):
        from apps.gaps.models import GapItem
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        # A fixed number of queries per page, however many rows: every relation the serializer reads is
        # joined or prefetched (the gaps each fact's document is evidence for included).
        return (
            ExtractedFact.objects.filter(sprint_id=self.kwargs['sprint_id'])
            .select_related('source_document', 'document', 'sprint', 'assigned_to', 'reviewed_by').prefetch_related(
                Prefetch('aiqif_mappings', queryset=FactAIQIFMapping.objects.select_related('reviewed_by', 'pending_by')),
                Prefetch('evidence_requests', to_attr='open_evidence_requests',
                         queryset=EvidenceRequest.objects.filter(status__in=EvidenceRequest.UNRESOLVED)
                         .select_related('assigned_to')),
                Prefetch('document__evidence_for_gaps', to_attr='prefetched_evidence_gaps',
                         queryset=GapItem.objects.only('id', 'title', 'gap_type', 'status')),
            )
        )


class SprintFactFacetsView(APIView):
    """GET /sprints/<id>/facts/facets -- how many facts have each filter value, over the whole sprint (database
    aggregates, no rows loaded): the options and totals of the Facts Review filters, and per-document counts."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        from django.db.models import Count

        from apps.scoring.constants import AIQIF_CRITERION_CODES, AIQIF_INDICATORS, PILLAR_LABELS

        from .aiqif_tagging import queued_tags_q
        from .filters import CONFIDENCE_BANDS, confidence_band_q
        sprint = get_authorized_sprint(request.user, sprint_id)
        facts = ExtractedFact.objects.filter(sprint=sprint)

        def counts(field, rename=None):
            rows = facts.values(field).annotate(n=Count('id')).order_by()
            return {(rename(r[field]) if rename else r[field]) or '': r['n'] for r in rows}

        bands = facts.aggregate(**{band: Count('id', filter=confidence_band_q(band)) for band in CONFIDENCE_BANDS})
        criteria = (FactAIQIFMapping.objects.filter(fact__sprint=sprint).values('criterion')
                    .annotate(n=Count('fact', distinct=True)).order_by())
        return Response({
            'total': facts.count(),
            'status': counts('status'),
            'pillar': counts('pillar'),
            'fact_kind': counts('fact_kind', lambda v: v or 'none'),
            'aiqif_mapping_status': counts('aiqif_mapping_status'),
            'owner_role': {k: v for k, v in counts('owner_role').items() if k},
            'source_document': {k: v for k, v in counts('source_document__original_filename').items() if k},
            'confidence_band': bands,
            'aiqif_criterion': sorted(
                [{'criterion': r['criterion'], 'code': AIQIF_CRITERION_CODES.get(r['criterion'], ''),
                  'name': PILLAR_LABELS.get(r['criterion'], ''), 'count': r['n']} for r in criteria],
                key=lambda g: g['code']),
            'by_document': {str(k): v for k, v in counts('document_id').items() if k},
            # Facts with a tag in each review state (the "Tag review" filter).
            'tag_review': {
                'confirmed': facts.filter(aiqif_mappings__review_status='confirmed').distinct().count(),
                'rejected': facts.filter(aiqif_mappings__review_status='rejected').distinct().count(),
                'pending': facts.filter(id__in=FactAIQIFMapping.objects.filter(
                    queued_tags_q(), fact__sprint=sprint).values('fact_id')).count(),
            },
            'indicators': [{'code': code, 'criterion': criterion, 'name': name}
                           for code, (criterion, name) in AIQIF_INDICATORS.items()],
        })


class SprintBulkFactConfirmView(APIView):
    """Confirm a bounded batch through the same ownership, request, and audit rules as one fact."""
    permission_classes = [CanReviewFacts]

    @extend_schema(request=BulkFactConfirmSerializer)
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        body = BulkFactConfirmSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reason = body.validated_data.get('comment', '').strip() or 'Confirmed by reviewer via bulk action.'

        confirmed = []
        skipped = []
        for fact_id in body.validated_data['fact_ids']:
            skip_reason = ''
            with transaction.atomic():
                fact = (ExtractedFact.objects.select_for_update().select_related('sprint')
                        .filter(pk=fact_id, sprint=sprint).first())
                if fact is None:
                    skip_reason = 'Fact was not found in this sprint.'
                elif fact.status != ExtractedFact.Status.EXTRACTED:
                    skip_reason = 'Fact is no longer awaiting review.'
                elif evidence_requests.open_request_for(fact):
                    skip_reason = 'Resolve the open evidence request first.'
                elif fact.confidence_score < settings.GAP_LOW_CONFIDENCE_THRESHOLD:
                    skip_reason = 'Low-confidence facts need individual review.'
                elif not (fact.source_snippet or '').strip():
                    skip_reason = 'The source quote is missing; review this fact individually.'
                elif GapItem.objects.filter(
                    sprint=sprint,
                    gap_type=GapItem.GapType.CONFLICT,
                    status__in=GapItem.ACTIVE_STATUSES,
                ).filter(
                    Q(source_fact_id=fact.id)
                    | Q(conflict_fact_b_id=fact.id)
                    | Q(conflict_fact_b__isnull=True, source_fact__field_key=fact.field_key)
                ).exists():
                    skip_reason = 'This fact has an unresolved conflict.'
                else:
                    allowed, why = ownership.check_fact(request.user, fact)
                    if not allowed:
                        skip_reason = why
                    else:
                        FactReviewHistory.objects.create(
                            fact=fact,
                            action=FactReviewHistory.Action.CONFIRMED,
                            original_value=fact.value,
                            user=request.user,
                            reason=reason,
                        )
                        fact.status = ExtractedFact.Status.CONFIRMED
                        fact.reviewed_by = request.user
                        fact.reviewed_at = timezone.now()
                        fact.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
                        after_fact_review(fact, user=request.user, reason=reason)

            if skip_reason:
                skipped.append({'id': str(fact_id), 'reason': skip_reason})
            else:
                confirmed.append(str(fact_id))

        return Response({
            'requested_count': len(body.validated_data['fact_ids']),
            'confirmed': confirmed,
            'confirmed_count': len(confirmed),
            'skipped': skipped,
            'skipped_count': len(skipped),
        })


class FactDetailView(generics.RetrieveAPIView):
    """Read-only. A fact's value/status only ever changes through the
    confirm/correct/reject/request-evidence actions below, so every change
    is captured in FactReviewHistory -- there's no generic PATCH here to
    bypass that."""
    queryset = ExtractedFact.objects.select_related('source_document', 'sprint', 'assigned_to', 'reviewed_by').prefetch_related('aiqif_mappings')
    serializer_class = ExtractedFactDetailSerializer
    lookup_field = 'pk'
    permission_classes = [IsInstitutionMember]


class BaseFactActionView(APIView):
    """Shared plumbing for the four review actions: look up + authorize the
    fact, validate the action's payload, record a FactReviewHistory entry
    capturing the value as it stood *before* this action, then apply the
    status change (and, for correct, the value change)."""
    permission_classes = [CanReviewFacts]
    serializer_class = None
    action_name = None
    new_status = None
    changes_value = False

    def get_new_value(self, serializer):
        raise NotImplementedError

    def post(self, request, pk):
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
        require_institution_access(request.user, fact)
        allowed, why = ownership.check_fact(request.user, fact)
        if not allowed:  # the owner role, an Institution Admin or InGage staff only (ownership.py)
            raise PermissionDenied(why)
        if evidence_requests.open_request_for(fact):
            # Only the reviewer's decision on the request may confirm/correct the fact now (or withdraw it).
            raise ValidationError({'detail': 'This fact has an open evidence request. Decide it on the request '
                                             '(accept, accept with correction, reject or withdraw).'})

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.resolved_reason()
        if self.new_status == ExtractedFact.Status.REJECTED and not reason.strip():
            raise ValidationError({'detail': 'Say why the fact is rejected; the reason is kept with its gap.'})
        new_value = self.get_new_value(serializer) if self.changes_value else None

        with transaction.atomic():
            FactReviewHistory.objects.create(
                fact=fact,
                action=self.action_name,
                original_value=fact.value,
                new_value=new_value,
                user=request.user,
                reason=reason,
            )

            update_fields = ['status', 'reviewed_by', 'reviewed_at', 'updated_at']
            if self.changes_value:
                fact.value = new_value
                update_fields.append('value')
            fact.status = self.new_status
            fact.reviewed_by = request.user
            fact.reviewed_at = timezone.now()
            fact.save(update_fields=update_fields)

            # The review settles the fact's gaps (apps.gaps.services.after_fact_review): confirm/correct
            # closes its "needs confirmation" gap, reject turns it into "needs replacement" with the
            # reason, and a conflict whose values now agree closes.
            after_fact_review(fact, user=request.user, reason=reason)

        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class FactConfirmView(BaseFactActionView):
    serializer_class = FactConfirmSerializer
    action_name = FactReviewHistory.Action.CONFIRMED
    new_status = ExtractedFact.Status.CONFIRMED

    @extend_schema(request=FactConfirmSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class FactRejectView(BaseFactActionView):
    serializer_class = FactRejectSerializer
    action_name = FactReviewHistory.Action.REJECTED
    new_status = ExtractedFact.Status.REJECTED

    @extend_schema(request=FactRejectSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class FactRequestEvidenceView(APIView):
    """Creates an EvidenceRequest (what is needed and why, optional assignee and due date); the fact's
    status becomes evidence_requested with a FactReviewHistory row, as before. See evidence_requests.py."""
    permission_classes = [CanReviewFacts]

    @extend_schema(request=EvidenceRequestCreateSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk):
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
        require_institution_access(request.user, fact)
        allowed, why = ownership.check_fact(request.user, fact)
        if not (allowed or ownership.is_coordinator(request.user, fact.sprint.institution_id)):
            raise PermissionDenied(why)  # the fact's owners, or a coordinator chasing it
        body = EvidenceRequestCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            evidence_requests.create_request(
                fact, request.user, description=body.resolved_description(),
                evidence_needed=body.validated_data.get('evidence_needed', ''),
                reason=body.validated_data.get('reason', ''),
                assigned_to=body.validated_data.get('assigned_to'), due_date=body.validated_data.get('due_date'))
        except evidence_requests.EvidenceRequestError as exc:
            raise ValidationError({'detail': str(exc)})
        fact.refresh_from_db()
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class FactCorrectView(BaseFactActionView):
    serializer_class = FactCorrectSerializer
    action_name = FactReviewHistory.Action.CORRECTED
    new_status = ExtractedFact.Status.CORRECTED
    changes_value = True

    def get_new_value(self, serializer):
        return serializer.resolved_new_value()

    @extend_schema(request=FactCorrectSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class FactAIQIFMappingReviewView(APIView):
    """POST /facts/<id>/aiqif-mappings/<indicator_code>/review {decision: confirm|reject, note}.

    Super Admin only (the AI-QIF expert queue, apps/facts/aiqif_tagging.py). Confirms or rejects one AI-QIF tag
    on a fact; the decision is kept in the fact's review history, kept by every later re-extraction, and the
    CRI is recalculated so coverage follows it."""
    permission_classes = [IsSuperAdmin]

    @extend_schema(request=FactAIQIFMappingReviewSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk, indicator_code):
        from apps.scoring.services import run_scoring_engine

        from .aiqif_tagging import review_tag
        fact = get_object_or_404(ExtractedFact, pk=pk)
        require_institution_access(request.user, fact)
        mapping = get_object_or_404(FactAIQIFMapping, fact=fact, indicator_code=indicator_code)
        serializer = FactAIQIFMappingReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review_tag(mapping, request.user, serializer.validated_data['decision'], serializer.validated_data['note'])
        run_scoring_engine(fact.sprint, triggered_by=request.user)
        fact = ExtractedFact.objects.prefetch_related('aiqif_mappings').get(pk=fact.pk)
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class FactAIQIFMappingAddView(APIView):
    """POST /facts/<id>/aiqif-mappings {indicator_code, relationship, note} -- Super Admin only.
    Adds (or replaces) an AI-QIF tag as an expert decision; recalculates the CRI."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        from apps.scoring.services import run_scoring_engine

        from .aiqif_tagging import TaggingError, add_tag
        from .serializers import FactAIQIFMappingAddSerializer
        fact = get_object_or_404(ExtractedFact, pk=pk)
        require_institution_access(request.user, fact)
        body = FactAIQIFMappingAddSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            add_tag(fact, request.user, body.validated_data['indicator_code'], body.validated_data['relationship'],
                    body.validated_data['note'])
        except TaggingError as exc:
            raise ValidationError({'detail': str(exc)})
        run_scoring_engine(fact.sprint, triggered_by=request.user)
        fact = ExtractedFact.objects.prefetch_related('aiqif_mappings').get(pk=fact.pk)
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data, status=201)


def _expert_mapping(request, pk, indicator_code):
    """The tag `indicator_code` of fact `pk`, for a Super Admin who may access the fact's institution."""
    fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
    require_institution_access(request.user, fact)
    mapping = get_object_or_404(FactAIQIFMapping, fact=fact, indicator_code=indicator_code)
    return fact, mapping


def _after_tag_change(request, fact):
    """Recalculate the sprint's CRI (coverage and coverage-adjusted CRI follow the tags; the Raw CRI only reads
    facts) and return the fact as the list shows it."""
    from apps.scoring.services import run_scoring_engine
    run_scoring_engine(fact.sprint, triggered_by=request.user)
    fact = ExtractedFact.objects.prefetch_related(
        Prefetch('aiqif_mappings', queryset=FactAIQIFMapping.objects.select_related('reviewed_by', 'pending_by')),
        'review_history').get(pk=fact.pk)
    return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class FactAIQIFMappingEditView(APIView):
    """POST /facts/<id>/aiqif-mappings/<indicator_code>/edit {indicator_code?, relationship?, note, decision?}
    -- Super Admin only. A new indicator or relationship never inherits the earlier approval: it waits for a
    decision unless `decision` (confirm / reject) is given now. The fact itself is never changed."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk, indicator_code):
        from .aiqif_tagging import TaggingError, edit_tag
        from .serializers import FactAIQIFMappingEditSerializer
        fact, mapping = _expert_mapping(request, pk, indicator_code)
        body = FactAIQIFMappingEditSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            edit_tag(mapping, request.user, indicator_code=data.get('indicator_code') or None,
                     relationship=data.get('relationship') or None, note=data['note'], decision=data.get('decision') or None)
        except TaggingError as exc:
            raise ValidationError({'detail': str(exc)})
        return _after_tag_change(request, fact)


class FactAIQIFMappingReopenView(APIView):
    """POST /facts/<id>/aiqif-mappings/<indicator_code>/reopen {reason} -- Super Admin only. Sends a decided tag
    back to the sprint's AI-QIF expert queue; the earlier decision stays in the fact's review history."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk, indicator_code):
        from .aiqif_tagging import TaggingError, reopen_tag
        fact, mapping = _expert_mapping(request, pk, indicator_code)
        try:
            reopen_tag(mapping, request.user, (request.data.get('reason') or '').strip())
        except TaggingError as exc:
            raise ValidationError({'detail': str(exc)})
        return _after_tag_change(request, fact)


class FactKindView(APIView):
    """POST /facts/<id>/fact-kind {fact_kind, note} -- Super Admin only. Decides what the fact is for (AI
    evidence / context / profile); re-extraction keeps the decision. Recalculates the CRI."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        from apps.scoring.services import run_scoring_engine

        from .aiqif_tagging import decide_kind
        from .serializers import FactKindSerializer
        fact = get_object_or_404(ExtractedFact, pk=pk)
        require_institution_access(request.user, fact)
        body = FactKindSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        decide_kind(fact, request.user, body.validated_data['fact_kind'], body.validated_data['note'])
        run_scoring_engine(fact.sprint, triggered_by=request.user)
        fact = ExtractedFact.objects.prefetch_related('aiqif_mappings').get(pk=fact.pk)
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class SprintAIQIFSummaryView(APIView):
    """GET /sprints/<id>/aiqif-summary -- for everyone on the sprint (the sales view): how many facts are AI
    evidence / context / profile / not classified, and how many items wait for a Super Admin. No indicator
    codes; nothing to choose."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        from django.db.models import Count

        from .aiqif_tagging import queue_counts
        sprint = get_authorized_sprint(request.user, sprint_id)
        facts = ExtractedFact.objects.filter(sprint=sprint).exclude(status=ExtractedFact.Status.REJECTED)
        kinds = dict(facts.values_list('fact_kind').annotate(n=Count('id')))
        queue = queue_counts(sprint)
        return Response({
            'facts': facts.count(),
            'ai_evidence': kinds.get(ExtractedFact.FactKind.AI_EVIDENCE, 0),
            'context': kinds.get(ExtractedFact.FactKind.CONTEXT, 0),
            'profile': kinds.get(ExtractedFact.FactKind.PROFILE, 0),
            'not_classified': kinds.get('', 0),
            'expert_queue': queue,
            'coverage_provisional': queue['total'] > 0,
        })


class SprintAIQIFExpertQueueView(APIView):
    """GET /sprints/<id>/aiqif-expert-queue -- Super Admin only: the AI-QIF items waiting for an expert --
    AI tags not accepted automatically, and facts whose kind needs a decision (possibly AI evidence filed as
    context/profile, AI evidence with no indicator, not classified)."""
    permission_classes = [IsSuperAdmin]

    def get(self, request, sprint_id):
        from .aiqif_tagging import needs_expert_q, queued_tags_q
        sprint = get_authorized_sprint(request.user, sprint_id)
        tag_fact_ids = (FactAIQIFMapping.objects.filter(queued_tags_q(), fact__sprint=sprint)
                        .values_list('fact_id', flat=True))
        facts = (ExtractedFact.objects.filter(sprint=sprint).exclude(status=ExtractedFact.Status.REJECTED)
                 .filter(needs_expert_q() | Q(id__in=tag_fact_ids))
                 .select_related('document', 'source_document').prefetch_related(
                     Prefetch('aiqif_mappings', queryset=FactAIQIFMapping.objects.select_related('reviewed_by', 'pending_by')))
                 .order_by('pillar', 'field_key'))
        from apps.scoring.constants import AIQIF_INDICATORS
        rows = ExtractedFactSerializer(facts, many=True, context={'request': request}).data
        return Response({'count': len(rows), 'facts': rows,
                         'indicators': [{'code': code, 'criterion': criterion, 'name': name}
                                        for code, (criterion, name) in AIQIF_INDICATORS.items()]})


class SprintAIQIFAutoCheckView(APIView):
    """POST /sprints/<id>/aiqif-expert-queue/auto-check -- Super Admin only. Decides what it can of the waiting
    AI-QIF tags without a person: earlier expert decisions on the same field now, the AI second opinion in the
    background (aiqif_tagging rule 4). Everything decided stays reversible in the Reviewed tab."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, sprint_id):
        from apps.scoring.services import run_scoring_engine

        from .aiqif_tagging import auto_check_sprint, queue_counts
        from .tasks import run_aiqif_auto_check
        sprint = get_authorized_sprint(request.user, sprint_id)
        result = auto_check_sprint(sprint, ai=False)
        if result['precedent_decisions']:
            run_scoring_engine(sprint, triggered_by=request.user)
        ai = 'off'
        if settings.AIQIF_AI_CHECK_ENABLED and queue_counts(sprint)['tags']:
            try:
                run_aiqif_auto_check.delay(str(sprint.id))
                ai = 'queued'
            except Exception:  # no broker: the precedents above still apply
                ai = 'unavailable'
        return Response({**result, 'ai_check': ai, 'expert_queue': queue_counts(sprint)})


class SprintProfileSuggestionView(APIView):
    """GET /sprints/<id>/profile-suggestion -- the benchmark profile as read from the sprint's profile facts
    (apps/facts/profile_suggestion.py), with conflicts and the closed option lists.
    POST {institution_type, autonomous_status, approval_bodies, programmes} -- saves it as confirmed (InGage
    staff, like the profile itself: it decides which indicators apply) and recalculates the CRI."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        from .profile_suggestion import suggestion
        return Response(suggestion(get_authorized_sprint(request.user, sprint_id)))

    def post(self, request, sprint_id):
        from apps.accounts.models import User
        from apps.assessments.services import AssessmentError

        from .profile_suggestion import confirm, suggestion
        sprint = get_authorized_sprint(request.user, sprint_id)
        if request.user.role not in (User.Role.SUPER_ADMIN, User.Role.CONSULTANT):
            raise PermissionDenied('Only InGage staff can confirm the profile (it decides which indicators apply).')
        try:
            confirm(sprint, request.user, request.data)
        except AssessmentError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response(suggestion(sprint))


class FactAssignView(APIView):
    """POST /facts/<id>/assign {assigned_to: <user id> | null, due_date?, note?} -- coordinators assign,
    reassign or unassign a fact to someone who may act on it (ownership.py); kept in its review history."""
    permission_classes = [CanReviewFacts]

    def post(self, request, pk):
        from .serializers import AssignSerializer
        fact = get_object_or_404(ExtractedFact.objects.select_related('sprint'), pk=pk)
        require_institution_access(request.user, fact)
        body = AssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            ownership.assign(fact, request.user, assigned_to=body.validated_data.get('assigned_to'),
                             due_date=body.validated_data.get('due_date'), note=body.validated_data['note'])
        except ownership.OwnershipError as exc:
            raise ValidationError({'detail': str(exc)})
        fact = ExtractedFact.objects.select_related('sprint', 'assigned_to').get(pk=pk)
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


class SprintWorkSummaryView(APIView):
    """GET /sprints/<id>/work-summary -- outstanding confirmation work across the WHOLE sprint (every
    owner role), by role and by assignee, and whether it is ready for baseline review. Readiness never
    depends on who is looking."""

    def get(self, request, sprint_id):
        from .work_summary import work_summary
        sprint = get_authorized_sprint(request.user, sprint_id)
        return Response(work_summary(sprint))
