from django.db.models import Avg, Count, Prefetch, Q
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import get_accessible_institution_ids
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.reports.models import Report
from apps.sprints.models import Sprint
from config.pagination import OptionalPageNumberPagination

from .serializers import DashboardSprintSerializer

#: A gap item counts as "high priority" for the summary tile if it's
#: unresolved and either blocking or high priority -- the same two
#: priorities apps.recommendations.services treats as worth an immediate
#: recommendation, kept consistent here rather than inventing a separate
#: threshold.
_HIGH_PRIORITY_GAP_PRIORITIES = [GapItem.Priority.BLOCKING, GapItem.Priority.HIGH]
_TERMINAL_SPRINT_STATUSES = [Sprint.Status.COMPLETED, Sprint.Status.ARCHIVED]


class DashboardView(APIView):
    """GET /api/v1/dashboard/ -- the summary tiles + accessible sprint list
    a signed-in user's dashboard needs, computed live from real rows (never
    mock/placeholder values). Scoped by the same institution-access rule as
    every other endpoint (apps.accounts.permissions): cross-institution
    roles (super_admin, consultant) see the whole platform; everyone else
    is confined to their own institution.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=None)
    def get(self, request):
        institution_ids = get_accessible_institution_ids(request.user)  # None = unrestricted

        sprints = Sprint.objects.all()
        gaps = GapItem.objects.filter(status__in=GapItem.ACTIVE_STATUSES, priority__in=_HIGH_PRIORITY_GAP_PRIORITIES)
        facts = ExtractedFact.objects.filter(status=ExtractedFact.Status.EXTRACTED)
        if institution_ids is not None:
            sprints = sprints.filter(institution_id__in=institution_ids)
            gaps = gaps.filter(sprint__institution_id__in=institution_ids)
            facts = facts.filter(sprint__institution_id__in=institution_ids)
            institution_count = len(institution_ids)
        else:
            institution_count = Institution.objects.count()

        # Each of these is its own simple, single-purpose query rather than
        # one query combining multiple reverse-relation Counts -- mixing
        # Count() over more than one reverse FK (gaps, reports, ...) in a
        # single .aggregate() call fans out the join and silently inflates
        # results unless every Count is individually distinct-guarded, so
        # keeping them separate is the safe default, not a missed
        # optimization.
        metrics = {
            'active_sprints': sprints.exclude(status__in=_TERMINAL_SPRINT_STATUSES).count(),
            'completion_percentage': round(sprints.aggregate(avg=Avg('completion_percentage'))['avg'] or 0.0, 1),
            'reports_ready': sprints.filter(reports__status=Report.Status.READY).distinct().count(),
            'pending_confirmations': facts.count(),
            'high_priority_gaps': gaps.count(),
            'sprint_count': sprints.count(),
            'institution_count': institution_count,
        }

        sprint_list = (
            sprints
            .select_related('institution')
            .annotate(
                pending_gaps_count=Count(
                    'gaps', filter=Q(gaps__status__in=GapItem.ACTIVE_STATUSES), distinct=True,
                ),
            )
            .prefetch_related(
                Prefetch('reports', queryset=Report.objects.order_by('-version'), to_attr='ordered_reports'),
            )
            .order_by('-updated_at')
        )

        paginator = OptionalPageNumberPagination()
        page = paginator.paginate_queryset(sprint_list, request, view=self)
        if page is None:
            sprints_payload = DashboardSprintSerializer(sprint_list, many=True).data
        else:
            serialized = DashboardSprintSerializer(page, many=True).data
            sprints_payload = paginator.get_paginated_response(serialized).data

        return Response({**metrics, 'sprints': sprints_payload})
