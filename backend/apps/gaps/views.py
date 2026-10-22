from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanResolveGaps, IsInstitutionMember, require_institution_access
from apps.facts import ownership
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from .filters import GapItemFilter
from .models import GapEvent, GapItem
from .services import close_block, resolve_block
from .serializers import (
    GapItemDetailSerializer,
    GapItemSerializer,
    GapMarkUnavailableSerializer,
    GapResolveSerializer,
    GapSkipSerializer,
)


class SprintGapListView(generics.ListAPIView):
    """Read-only: gaps are only ever created by the automatic generation
    services in apps.gaps.services, never by a generic client POST."""
    serializer_class = GapItemSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = GapItemFilter
    ordering_fields = ['created_at', 'updated_at', 'priority', 'resolved_at']
    ordering = ['-created_at']
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return GapItem.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related(
            'sprint', 'source_fact__source_document', 'source_fact__document', 'related_document',
            'conflict_fact_b__source_document', 'conflict_fact_b__document', 'assigned_to',
        ).prefetch_related(GapItemSerializer.EVIDENCE_REQUESTS_PREFETCH)


class GapDetailView(generics.RetrieveAPIView):
    """Read-only, with the gap's history (assignments, closes and why). A gap's status only ever changes
    through the actions below, or automatically when the underlying fact / document review fixes it."""
    queryset = GapItem.objects.select_related('sprint', 'source_fact', 'related_document', 'assigned_to')
    serializer_class = GapItemDetailSerializer
    lookup_field = 'pk'
    permission_classes = [IsInstitutionMember]


def _gap_for_action(request, pk):
    gap = get_object_or_404(GapItem.objects.select_related(
        'sprint', 'source_fact__sprint', 'related_document', 'conflict_fact_b', 'assigned_to'), pk=pk)
    require_institution_access(request.user, gap)
    allowed, why = ownership.check_gap(request.user, gap)
    if not allowed:  # the owner role, an Institution Admin or InGage staff only (apps/facts/ownership.py)
        raise PermissionDenied(why)
    return gap


class BaseGapActionView(APIView):
    permission_classes = [CanResolveGaps]
    serializer_class = None
    new_status = None
    event_action = None

    def check_allowed(self, gap, resolution):
        """Closing a gap without fixing it needs a reason, and never goes around an open evidence
        request (services.close_block)."""
        block = close_block(gap, resolution)
        if block:
            raise ValidationError({'detail': block})

    def post(self, request, pk):
        gap = _gap_for_action(request, pk)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        resolution = serializer.resolved_resolution().strip()
        self.check_allowed(gap, resolution)

        with transaction.atomic():
            gap.status = self.new_status
            gap.resolution = resolution
            gap.resolved_by = request.user
            gap.resolved_at = timezone.now()
            gap.save(update_fields=['status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'])
            GapEvent.objects.create(gap=gap, action=self.event_action, user=request.user, note=resolution)

        return Response(GapItemSerializer(gap, context={'request': request}).data)


class GapResolveView(BaseGapActionView):
    """Resolve once the underlying issue is fixed (services.resolve_block): the fact confirmed/corrected,
    a conflict's values reconciled, the missing or updated document reviewed, a rejected value replaced,
    a low-confidence value verified. Those fixes close the gap by themselves; this is for the rest."""
    serializer_class = GapResolveSerializer
    new_status = GapItem.Status.RESOLVED
    event_action = GapEvent.Action.RESOLVED

    def check_allowed(self, gap, resolution):
        block = resolve_block(gap)
        if block:
            raise ValidationError({'detail': block})
        if gap.gap_type == GapItem.GapType.LOW_CONFIDENCE and gap.source_fact_id and not resolution:
            raise ValidationError({'detail': 'Explain why this low-confidence gap is being closed.'})

    @extend_schema(request=GapResolveSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class GapMarkUnavailableView(BaseGapActionView):
    serializer_class = GapMarkUnavailableSerializer
    new_status = GapItem.Status.UNAVAILABLE
    event_action = GapEvent.Action.MARKED_UNAVAILABLE

    @extend_schema(request=GapMarkUnavailableSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class GapSkipView(BaseGapActionView):
    serializer_class = GapSkipSerializer
    new_status = GapItem.Status.SKIPPED
    event_action = GapEvent.Action.SKIPPED

    @extend_schema(request=GapSkipSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class GapAssignView(APIView):
    """POST /gaps/<id>/assign {assigned_to: <user id> | null, due_date?, note?} -- coordinators assign,
    reassign or unassign a gap to someone who may settle it (apps/facts/ownership.py)."""
    permission_classes = [CanResolveGaps]

    def post(self, request, pk):
        from apps.facts.serializers import AssignSerializer
        gap = get_object_or_404(GapItem.objects.select_related('sprint', 'source_fact', 'related_document'), pk=pk)
        require_institution_access(request.user, gap)
        body = AssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            ownership.assign(gap, request.user, assigned_to=body.validated_data.get('assigned_to'),
                             due_date=body.validated_data.get('due_date'), note=body.validated_data['note'])
        except ownership.OwnershipError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response(GapItemDetailSerializer(GapItem.objects.get(pk=pk), context={'request': request}).data)
