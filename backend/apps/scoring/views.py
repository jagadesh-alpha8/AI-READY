from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanApproveBaseline, CanManageSprint
from apps.gaps.models import GapItem
from apps.gaps.serializers import GapItemSerializer
from apps.sprints.access import get_authorized_sprint
from apps.sprints.models import Sprint
from config.pagination import OptionalPageNumberPagination

from .models import Pillar, ScoringRun
from .serializers import (
    BaselineActionSerializer,
    BaselineSerializer,
    PillarConfigSerializer,
    ScoringRunSerializer,
    SprintScoreSerializer,
)
from .services import (
    approve_baseline,
    approve_baseline_provisional,
    build_score_snapshot,
    get_or_create_pending_baseline,
    return_baseline_for_correction,
    run_scoring_engine,
)


class SprintScoreView(APIView):
    """GET returns the sprint's current, explainable CRI score -- computing
    it once, on first access, if the sprint has never been scored. POST
    forces a fresh recalculation from the sprint's current fact/gap data."""
    permission_classes = [CanManageSprint]

    @extend_schema(responses=SprintScoreSerializer)
    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        snapshot = build_score_snapshot(sprint)
        return Response(SprintScoreSerializer(snapshot).data)

    @extend_schema(request=None, responses=SprintScoreSerializer)
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        if sprint.status in Sprint.BASELINE_LOCKED_STATUSES:
            raise ValidationError(
                f"This sprint's baseline is already '{sprint.status}' -- an approved baseline's score is "
                'locked and cannot be recalculated. Return the baseline for correction first if the '
                'underlying data needs to change.'
            )
        run_scoring_engine(sprint, triggered_by=request.user)
        if sprint.status == Sprint.Status.REVIEWING:
            sprint.status = Sprint.Status.SCORING
            sprint.save(update_fields=['status', 'updated_at'])
        snapshot = build_score_snapshot(sprint)
        return Response(SprintScoreSerializer(snapshot).data)


class SprintScoreHistoryView(generics.ListAPIView):
    """The audit trail of every past scoring run for a sprint, most recent
    first -- each entry is frozen as of when it ran (see
    ScoringRun.pillar_snapshot), unlike GET .../score/ which always reflects
    the latest run's PillarScore rows."""
    serializer_class = ScoringRunSerializer
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return ScoringRun.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related('triggered_by')


class SprintBaselineView(APIView):
    """GET returns the sprint's current baseline decision-cycle, the score
    it's pinned to, and the gaps standing in the way of full approval --
    bootstrapping a PENDING baseline (and advancing the sprint to
    baseline_pending) on first access, the same pattern SprintScoreView uses
    to bootstrap a ScoringRun on first access."""
    permission_classes = [CanApproveBaseline]

    @extend_schema(responses=None)
    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        baseline = get_or_create_pending_baseline(sprint, triggered_by=request.user)
        snapshot = build_score_snapshot(sprint, bootstrap=False)

        blocking_gaps = sprint.gaps.filter(status__in=GapItem.ACTIVE_STATUSES, priority=GapItem.Priority.BLOCKING)
        high_priority_gaps = sprint.gaps.filter(
            status__in=GapItem.ACTIVE_STATUSES,
            priority__in=[GapItem.Priority.BLOCKING, GapItem.Priority.HIGH],
        ).order_by('priority', '-created_at')

        return Response({
            'baseline': BaselineSerializer(baseline).data,
            'score': SprintScoreSerializer(snapshot).data if snapshot else None,
            'high_priority_gaps': GapItemSerializer(high_priority_gaps, many=True).data,
            'can_approve': not blocking_gaps.exists(),
        })


class BaseBaselineActionView(APIView):
    permission_classes = [CanApproveBaseline]

    def perform_action(self, sprint, *, user, comments):
        raise NotImplementedError

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        serializer = BaselineActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        baseline = self.perform_action(sprint, user=request.user, comments=serializer.validated_data['comments'])
        return Response(BaselineSerializer(baseline).data)


class SprintBaselineApproveView(BaseBaselineActionView):
    """POST .../baseline/approve/ -- full approval; refused server-side
    while any blocking gap is unresolved (see approve_baseline)."""

    @extend_schema(request=BaselineActionSerializer, responses=BaselineSerializer)
    def post(self, request, sprint_id):
        return super().post(request, sprint_id)

    def perform_action(self, sprint, *, user, comments):
        return approve_baseline(sprint, user=user, comments=comments)


class SprintBaselineApproveProvisionalView(BaseBaselineActionView):
    """POST .../baseline/approve-provisional/ -- allowed even with
    unresolved blocking gaps; the baseline stays labeled 'provisional'
    rather than 'approved' downstream (see approve_baseline_provisional)."""

    @extend_schema(request=BaselineActionSerializer, responses=BaselineSerializer)
    def post(self, request, sprint_id):
        return super().post(request, sprint_id)

    def perform_action(self, sprint, *, user, comments):
        return approve_baseline_provisional(sprint, user=user, comments=comments)


class SprintBaselineReturnView(BaseBaselineActionView):
    """POST .../baseline/return/ -- sends the sprint back to reviewing;
    `comments` (the reason) is required (see return_baseline_for_correction)."""

    @extend_schema(request=BaselineActionSerializer, responses=BaselineSerializer)
    def post(self, request, sprint_id):
        return super().post(request, sprint_id)

    def perform_action(self, sprint, *, user, comments):
        return return_baseline_for_correction(sprint, user=user, comments=comments)


class ScoringConfigView(generics.ListAPIView):
    """The live, database-backed scoring configuration: every active pillar
    and its criteria, with current weights -- what actually drives the
    engine, not a hardcoded snapshot of it."""
    serializer_class = PillarConfigSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active']

    def get_queryset(self):
        return Pillar.objects.prefetch_related('criteria').order_by('display_order', 'key')
