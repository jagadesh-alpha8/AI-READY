from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from apps.accounts.permissions import (
    CanManageSprint,
    IsInstitutionMember,
    get_accessible_institution_ids,
    user_can_access_institution,
)
from apps.documents.serializers import DocumentSerializer
from apps.extraction.serializers import ExtractionJobSerializer
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.serializers import InstitutionSerializer
from apps.recommendations.serializers import RecommendationSerializer
from apps.reports.serializers import ReportSerializer
from apps.scoring.serializers import SprintScoreSerializer
from apps.scoring.services import build_score_snapshot
from config.pagination import OptionalPageNumberPagination

from .filters import SprintFilter
from .models import Sprint
from .serializers import SprintSerializer

#: A sprint can only be hard-deleted before real work has accumulated on it,
#: or once it's been shelved -- deleting an active in-progress sprint would
#: destroy real collected data. Archive it first.
DELETABLE_STATUSES = {Sprint.Status.DRAFT, Sprint.Status.COMPLETED, Sprint.Status.ARCHIVED}


class SprintViewSet(viewsets.ModelViewSet):
    serializer_class = SprintSerializer
    permission_classes = [CanManageSprint, IsInstitutionMember]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = SprintFilter
    ordering_fields = [
        'created_at', 'updated_at', 'start_date', 'target_completion_date',
        'completion_percentage', 'overall_cri', 'name',
    ]
    ordering = ['-created_at']
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        qs = Sprint.objects.select_related('institution')
        # As in InstitutionViewSet: only 'list' filters by accessible
        # institution. Detail actions (retrieve/update/destroy/overview) use
        # the unscoped queryset so an out-of-scope sprint 403s via
        # IsInstitutionMember instead of 404ing as if it didn't exist.
        if self.action == 'list':
            allowed_ids = get_accessible_institution_ids(self.request.user)
            if allowed_ids is not None:
                qs = qs.filter(institution_id__in=allowed_ids)
        return qs

    def perform_create(self, serializer):
        institution = serializer.validated_data['institution']
        if not user_can_access_institution(self.request.user, institution.id):
            raise PermissionDenied('You cannot create a sprint for an institution you do not belong to.')
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.status not in DELETABLE_STATUSES:
            raise ValidationError(
                f"Cannot delete a sprint in '{instance.status}' status. "
                'Archive it first (or delete it while still a draft).',
            )
        instance.delete()

    @action(detail=True, methods=['get'])
    def overview(self, request, pk=None):
        """Everything the dashboard / sprint-overview screen needs, in one call."""
        sprint = self.get_object()

        documents = sprint.documents.all()
        facts = sprint.facts.all()
        gaps = sprint.gaps.all()
        recommendations = sprint.recommendations.all()
        reports = sprint.reports.all()
        latest_extraction_job = sprint.extraction_jobs.order_by('-created_at').first()
        score_snapshot = build_score_snapshot(sprint, bootstrap=False)

        return Response({
            'sprint': SprintSerializer(sprint).data,
            'institution': InstitutionSerializer(sprint.institution).data,
            'documents': {
                'total': documents.count(),
                'pending': documents.filter(status='pending').count(),
                'uploaded': documents.filter(status='uploaded').count(),
                'processing': documents.filter(status='processing').count(),
                'processed': documents.filter(status='processed').count(),
                'failed': documents.filter(status='failed').count(),
                'rejected': documents.filter(status='rejected').count(),
                'items': DocumentSerializer(documents, many=True, context={'request': request}).data,
            },
            'facts': {
                'total': facts.count(),
                'extracted': facts.filter(status=ExtractedFact.Status.EXTRACTED).count(),
                'confirmed': facts.filter(status=ExtractedFact.Status.CONFIRMED).count(),
                'corrected': facts.filter(status=ExtractedFact.Status.CORRECTED).count(),
                'rejected': facts.filter(status=ExtractedFact.Status.REJECTED).count(),
                'evidence_requested': facts.filter(status=ExtractedFact.Status.EVIDENCE_REQUESTED).count(),
            },
            'gaps': {
                'total': gaps.count(),
                'open': gaps.filter(status=GapItem.Status.OPEN).count(),
                'in_progress': gaps.filter(status=GapItem.Status.IN_PROGRESS).count(),
                'resolved': gaps.filter(status=GapItem.Status.RESOLVED).count(),
                'blocking_open': gaps.filter(
                    status=GapItem.Status.OPEN, priority=GapItem.Priority.BLOCKING,
                ).count(),
            },
            'scorecard': SprintScoreSerializer(score_snapshot).data if score_snapshot else None,
            'recommendations': {
                'total': recommendations.count(),
                'accepted': recommendations.filter(status='accepted').count(),
                'draft': recommendations.filter(status='draft').count(),
                'items': RecommendationSerializer(recommendations, many=True).data,
            },
            'reports': {
                'total': reports.count(),
                'latest': ReportSerializer(reports.first()).data if reports.exists() else None,
            },
            'latest_extraction_job': (
                ExtractionJobSerializer(latest_extraction_job).data if latest_extraction_job else None
            ),
        })
