from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from django.db.models import Prefetch
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanReviewFacts, IsInstitutionMember, require_institution_access
from apps.gaps.services import after_fact_review
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from .filters import ExtractedFactFilter
from . import evidence_requests, ownership
from .evidence_serializers import EvidenceRequestCreateSerializer
from .models import EvidenceRequest, ExtractedFact, FactAIQIFMapping, FactReviewHistory
from .serializers import (
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
    ordering = ['-created_at']
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return (
            ExtractedFact.objects.filter(sprint_id=self.kwargs['sprint_id'])
            .select_related('source_document', 'sprint', 'assigned_to', 'reviewed_by').prefetch_related(
                'aiqif_mappings',
                Prefetch('evidence_requests', to_attr='open_evidence_requests',
                         queryset=EvidenceRequest.objects.filter(status__in=EvidenceRequest.UNRESOLVED)
                         .select_related('assigned_to')),
            )
        )


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

    A reviewer confirms or rejects one of the AI's AI-QIF tags on a fact. Only confirmed tags on
    confirmed/corrected facts count toward AI-QIF evidence coverage (scoring/services/coverage.py);
    the decision takes effect at the next CRI recalculation. Reprocessing keeps reviewed tags."""
    permission_classes = [CanReviewFacts]

    @extend_schema(request=FactAIQIFMappingReviewSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk, indicator_code):
        fact = get_object_or_404(ExtractedFact, pk=pk)
        require_institution_access(request.user, fact)
        mapping = get_object_or_404(FactAIQIFMapping, fact=fact, indicator_code=indicator_code)
        serializer = FactAIQIFMappingReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mapping.review_status = (FactAIQIFMapping.ReviewStatus.CONFIRMED
                                 if serializer.validated_data['decision'] == 'confirm'
                                 else FactAIQIFMapping.ReviewStatus.REJECTED)
        mapping.reviewed_by = request.user
        mapping.reviewed_at = timezone.now()
        mapping.review_note = serializer.validated_data['note'].strip()
        mapping.save(update_fields=['review_status', 'reviewed_by', 'reviewed_at', 'review_note'])
        fact = ExtractedFact.objects.prefetch_related('aiqif_mappings').get(pk=fact.pk)
        return Response(ExtractedFactDetailSerializer(fact, context={'request': request}).data)


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
