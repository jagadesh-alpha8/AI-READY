from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanReviewFacts, IsInstitutionMember, require_institution_access
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from .filters import ExtractedFactFilter
from .models import ExtractedFact, FactReviewHistory
from .serializers import (
    ExtractedFactDetailSerializer,
    ExtractedFactSerializer,
    FactConfirmSerializer,
    FactCorrectSerializer,
    FactEvidenceRequestSerializer,
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
        return ExtractedFact.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related('source_document')


class FactDetailView(generics.RetrieveAPIView):
    """Read-only. A fact's value/status only ever changes through the
    confirm/correct/reject/request-evidence actions below, so every change
    is captured in FactReviewHistory -- there's no generic PATCH here to
    bypass that."""
    queryset = ExtractedFact.objects.select_related('source_document')
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
        fact = get_object_or_404(ExtractedFact, pk=pk)
        require_institution_access(request.user, fact)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.resolved_reason()
        new_value = self.get_new_value(serializer) if self.changes_value else None

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

        return Response(ExtractedFactDetailSerializer(fact).data)


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


class FactRequestEvidenceView(BaseFactActionView):
    serializer_class = FactEvidenceRequestSerializer
    action_name = FactReviewHistory.Action.EVIDENCE_REQUESTED
    new_status = ExtractedFact.Status.EVIDENCE_REQUESTED

    @extend_schema(request=FactEvidenceRequestSerializer, responses=ExtractedFactDetailSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


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
