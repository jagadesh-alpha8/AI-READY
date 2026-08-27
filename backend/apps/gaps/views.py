from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanResolveGaps, IsInstitutionMember, require_institution_access
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from .filters import GapItemFilter
from .models import GapItem
from .serializers import (
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
        return GapItem.objects.filter(sprint_id=self.kwargs['sprint_id'])


class GapDetailView(generics.RetrieveAPIView):
    """Read-only. A gap's status only ever changes through the resolve/
    mark-unavailable/skip actions below, which also record who and when."""
    queryset = GapItem.objects.all()
    serializer_class = GapItemSerializer
    lookup_field = 'pk'
    permission_classes = [IsInstitutionMember]


class BaseGapActionView(APIView):
    permission_classes = [CanResolveGaps]
    serializer_class = None
    new_status = None

    def post(self, request, pk):
        gap = get_object_or_404(GapItem, pk=pk)
        require_institution_access(request.user, gap)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        gap.status = self.new_status
        gap.resolution = serializer.resolved_resolution()
        gap.resolved_by = request.user
        gap.resolved_at = timezone.now()
        gap.save(update_fields=['status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'])

        return Response(GapItemSerializer(gap).data)


class GapResolveView(BaseGapActionView):
    serializer_class = GapResolveSerializer
    new_status = GapItem.Status.RESOLVED

    @extend_schema(request=GapResolveSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class GapMarkUnavailableView(BaseGapActionView):
    serializer_class = GapMarkUnavailableSerializer
    new_status = GapItem.Status.UNAVAILABLE

    @extend_schema(request=GapMarkUnavailableSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)


class GapSkipView(BaseGapActionView):
    serializer_class = GapSkipSerializer
    new_status = GapItem.Status.SKIPPED

    @extend_schema(request=GapSkipSerializer, responses=GapItemSerializer)
    def post(self, request, pk):
        return super().post(request, pk)
