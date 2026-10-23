from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanResolveGaps, IsInstitutionMember, require_institution_access
from apps.facts import ownership
from apps.sprints.access import get_authorized_sprint
from config.pagination import DefaultPageNumberPagination, OptionalPageNumberPagination

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
    ordering = ['-created_at', 'id']
    # Always paginated (50 per page, at most 100): a sprint has hundreds of gaps.
    pagination_class = DefaultPageNumberPagination

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return GapItem.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related(
            'sprint', 'source_fact__source_document', 'source_fact__document', 'related_document',
            'conflict_fact_b__source_document', 'conflict_fact_b__document', 'assigned_to',
        ).prefetch_related(
            GapItemSerializer.EVIDENCE_REQUESTS_PREFETCH,
            # Upload Evidence state (gaps/evidence_upload.evidence_state): documents and their jobs, batched.
            'evidence_documents__extraction_jobs',
        )


class SprintGapFacetsView(APIView):
    """GET /sprints/<id>/gaps/facets -- how many gaps have each filter value over the whole sprint: the Gap
    Dashboard's filter options and totals. Type / priority / status are database aggregates; owner and source
    are derived per gap (GapItemSerializer), so they are counted from one narrow query, never from serialized rows."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        from collections import Counter

        from django.db.models import Count

        from apps.facts.ownership import checklist_owner_role

        from .services import missing_document_type
        sprint = get_authorized_sprint(request.user, sprint_id)
        gaps = GapItem.objects.filter(sprint=sprint)

        def counts(field):
            return {r[field]: r['n'] for r in gaps.values(field).annotate(n=Count('id')).order_by()}

        owners, sources = Counter(), Counter()
        for gap in gaps.select_related('source_fact__source_document', 'source_fact__document', 'related_document').only(
                'id', 'gap_type', 'title', 'description', 'source_fact__owner_role',
                'source_fact__source_document__original_filename', 'source_fact__document__original_filename',
                'related_document__owner_role', 'related_document__original_filename', 'related_document__document_type'):
            fact, doc = gap.source_fact, gap.related_document
            owner = fact.owner_role if fact else (doc.owner_role if doc else (
                checklist_owner_role(missing_document_type(gap)) if gap.gap_type == GapItem.GapType.MISSING_DOCUMENT else ''))
            source_doc = (fact.source_document or fact.document) if fact else doc
            if owner:
                owners[owner] += 1
            if source_doc is not None and source_doc.original_filename:
                sources[source_doc.original_filename] += 1
        status_counts = counts('status')
        return Response({
            'total': sum(status_counts.values()),
            'open': sum(n for s, n in status_counts.items() if s in GapItem.ACTIVE_STATUSES),
            'gap_type': counts('gap_type'),
            'priority': counts('priority'),
            'status': status_counts,
            'owner_role': dict(owners),
            'source_document': dict(sources),
        })


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


class GapUploadEvidenceView(APIView):
    """POST /gaps/<id>/upload-evidence (multipart: file, document_type?) -- Missing Document / Low Confidence gaps.
    Stores the file in the gap's sprint, links it to the gap and queues its processing there. It never confirms a
    fact or resolves the gap (gaps/evidence_upload.py). Only people who may act on the gap (ownership.py)."""
    permission_classes = [CanResolveGaps]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        from .evidence_upload import EvidenceUploadError, upload_for_gap
        gap = get_object_or_404(GapItem.objects.select_related('sprint', 'source_fact'), pk=pk)
        require_institution_access(request.user, gap)
        allowed, why = ownership.check_gap(request.user, gap)
        if not allowed:
            raise PermissionDenied(why)
        try:
            document, reused = upload_for_gap(gap, request.user, request.data.get('file'),
                                              document_type=(request.data.get('document_type') or '').strip())
        except EvidenceUploadError as exc:
            return Response({'detail': str(exc)}, status=400)
        gap.refresh_from_db()
        data = GapItemSerializer(gap, context={'request': request}).data
        return Response({'gap': data, 'document_id': str(document.id), 'reused': reused}, status=201)


class GapChooseConflictValueView(APIView):
    """POST /gaps/<id>/choose-value {fact_id, reason?} -- settle a conflict: confirm the chosen value, reject the
    competing ones, close the conflict, recalculate the CRI (services.choose_conflict_value). Only the gap's owner
    role of its own college, or a Super Admin (ownership.check_conflict_choice)."""
    permission_classes = [CanResolveGaps]

    def post(self, request, pk):
        from .services import ConflictChoiceError, choose_conflict_value
        gap = get_object_or_404(GapItem.objects.select_related('sprint', 'source_fact', 'conflict_fact_b',
                                                               'related_document'), pk=pk)
        require_institution_access(request.user, gap)
        allowed, why = ownership.check_conflict_choice(request.user, gap)
        if not allowed:
            raise PermissionDenied(why)
        fact_id = request.data.get('fact_id')
        if not fact_id:
            raise ValidationError({'fact_id': 'Choose the fact whose value is correct.'})
        try:
            choose_conflict_value(gap, request.user, fact_id, request.data.get('reason') or '')
        except ConflictChoiceError as exc:
            raise ValidationError({'detail': str(exc)})
        gap.refresh_from_db()
        return Response(GapItemDetailSerializer(gap, context={'request': request}).data)
