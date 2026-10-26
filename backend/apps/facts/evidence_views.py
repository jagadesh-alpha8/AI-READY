from datetime import date

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import (
    CanContribute,
    CanReviewFacts,
    get_accessible_institution_ids,
    require_institution_access,
)
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from . import evidence_requests as svc
from .evidence_serializers import (
    AssigneeSerializer,
    EvidenceAssignSerializer,
    EvidenceCommentSerializer,
    EvidenceRequestDetailSerializer,
    EvidenceRequestSerializer,
    EvidenceReviewSerializer,
    EvidenceSubmitSerializer,
)
from .models import EvidenceRequest


def _scoped(user):
    qs = EvidenceRequest.objects.select_related(
        'fact', 'sprint__institution', 'requested_by', 'assigned_to', 'resolved_by').prefetch_related('evidence')
    allowed = get_accessible_institution_ids(user)
    return qs if allowed is None else qs.filter(sprint__institution_id__in=allowed)


def _filter(qs, params, user):
    """?status=open,returned  ?unresolved=true  ?overdue=true  ?assigned_to=me|<uuid>  ?sprint=<uuid>"""
    if params.get('status'):
        qs = qs.filter(status__in=[s for s in params['status'].split(',') if s])
    if params.get('unresolved') == 'true':
        qs = qs.filter(status__in=EvidenceRequest.UNRESOLVED)
    if params.get('overdue') == 'true':
        qs = qs.filter(status__in=EvidenceRequest.UNRESOLVED, due_date__lt=date.today())
    assigned = params.get('assigned_to')
    if assigned == 'me':
        qs = qs.filter(assigned_to=user)
    elif assigned == 'none':
        qs = qs.filter(assigned_to__isnull=True)
    elif assigned:
        qs = qs.filter(assigned_to_id=assigned)
    sprint = _requested_sprint(params, user)
    if sprint is not None:
        qs = qs.filter(sprint=sprint)
    return qs


def _requested_sprint(params, user):
    """?sprint=<uuid> -> that sprint, after checking the user may open it (404 / 403 otherwise, never an empty
    list that hides a wrong id). Missing or "all" -> None: every sprint the user's institution scope allows."""
    import uuid

    from rest_framework.exceptions import NotFound

    value = (params.get('sprint') or '').strip()
    if not value or value == 'all':
        return None
    try:
        uuid.UUID(value)
    except ValueError:
        raise NotFound('Unknown sprint.')
    return get_authorized_sprint(user, value)


def _get(user, pk):
    request = get_object_or_404(_scoped(user), pk=pk)
    require_institution_access(user, request)
    return request


def _detail(request_obj):
    fresh = (EvidenceRequest.objects.select_related('fact', 'sprint__institution', 'requested_by', 'assigned_to',
                                                    'resolved_by')
             .prefetch_related('evidence__document', 'evidence__submitted_by', 'evidence__reviewed_by',
                               'events__user').get(pk=request_obj.pk))
    return Response(EvidenceRequestDetailSerializer(fresh).data)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.EvidenceRequestError as exc:
        raise ValidationError({'detail': str(exc)})


class EvidenceRequestListView(generics.ListAPIView):
    """Every evidence request the user can see (their college's, or all for InGage staff). The in-app task
    list: `?assigned_to=me&unresolved=true` is what is waiting on the current user."""
    serializer_class = EvidenceRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        return _filter(_scoped(self.request.user), self.request.query_params, self.request.user)


class SprintEvidenceRequestListView(EvidenceRequestListView):
    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return super().get_queryset().filter(sprint_id=self.kwargs['sprint_id'])


class EvidenceRequestSummaryView(APIView):
    """Counts for the sidebar badge: unresolved requests assigned to me (and how many are overdue)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scoped = _scoped(request.user)
        sprint = _requested_sprint(request.query_params, request.user)  # ?sprint=<uuid>: that sprint only
        if sprint is not None:
            scoped = scoped.filter(sprint=sprint)
        mine = scoped.filter(assigned_to=request.user, status__in=EvidenceRequest.UNRESOLVED)
        return Response({
            'assigned_to_me': mine.exclude(status__in=[EvidenceRequest.Status.SUBMITTED,
                                                       EvidenceRequest.Status.PROCESSING,
                                                       EvidenceRequest.Status.READY_FOR_REVIEW]).count(),
            'assigned_to_me_overdue': mine.filter(due_date__lt=date.today()).count(),
            'awaiting_my_review': scoped.filter(
                requested_by=request.user,
                status__in=[EvidenceRequest.Status.SUBMITTED, EvidenceRequest.Status.READY_FOR_REVIEW]).count(),
        })


class SprintEvidenceAssigneesView(APIView):
    """Who a request in this sprint can be assigned to: active, non-viewer users of the college."""
    permission_classes = [IsAuthenticated]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        return Response(AssigneeSerializer(svc.eligible_assignees(sprint), many=True).data)


class EvidenceRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=EvidenceRequestDetailSerializer)
    def get(self, request, pk):
        return _detail(_get(request.user, pk))


class EvidenceRequestAssignView(APIView):
    permission_classes = [CanContribute]

    @extend_schema(request=EvidenceAssignSerializer, responses=EvidenceRequestDetailSerializer)
    def post(self, request, pk):
        obj = _get(request.user, pk)
        body = EvidenceAssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _run(svc.assign, obj, request.user, body.validated_data['assigned_to'], body.validated_data['note'])
        return _detail(obj)


class EvidenceRequestCommentView(APIView):
    permission_classes = [CanContribute]

    @extend_schema(request=EvidenceCommentSerializer, responses=EvidenceRequestDetailSerializer)
    def post(self, request, pk):
        obj = _get(request.user, pk)
        body = EvidenceCommentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _run(svc.comment, obj, request.user, body.validated_data['note'])
        return _detail(obj)


class EvidenceRequestSubmitView(APIView):
    """The assigned person uploads a file (multipart `file`) or names an existing sprint document."""
    permission_classes = [CanContribute]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(request=EvidenceSubmitSerializer, responses=EvidenceRequestDetailSerializer)
    def post(self, request, pk):
        obj = _get(request.user, pk)
        body = EvidenceSubmitSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        _run(svc.submit_evidence, obj, request.user, document_id=d.get('document_id'), file=d.get('file'),
             submitted_text=d.get('submitted_text', ''), source_context=d.get('source_context', ''),
             document_type=d['document_type'], source_page=d['source_page'], source_snippet=d['source_snippet'],
             note=d['note'], run_extraction=d['run_extraction'])
        return _detail(obj)


class EvidenceRequestReviewView(APIView):
    """A reviewer's decision: accept | accept_corrected | reject | withdraw."""
    permission_classes = [CanReviewFacts]

    @extend_schema(request=EvidenceReviewSerializer, responses=EvidenceRequestDetailSerializer)
    def post(self, request, pk):
        obj = _get(request.user, pk)
        body = EvidenceReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        _run(svc.review, obj, request.user, d['decision'], evidence_id=d.get('evidence_id'), reason=d['reason'],
             corrected_value=d.get('corrected_value'), has_corrected_value='corrected_value' in request.data,
             source_page=d.get('source_page'), source_snippet=d.get('source_snippet'),
             return_to_assignee=d['return_to_assignee'])
        return _detail(obj)


class EvidenceAssessmentRetryView(APIView):
    """POST /evidence-requests/<id>/evidence/<evidence_id>/retry-assessment -- a reviewer retries a failed AI
    assessment of that submission (no re-upload, no extraction). 409 while one is already queued or running."""
    permission_classes = [CanReviewFacts]

    @extend_schema(request=None, responses=EvidenceRequestDetailSerializer)
    def post(self, request, pk, evidence_id):
        obj = _get(request.user, pk)
        try:
            svc.request_assessment_retry(obj, request.user, evidence_id)
        except svc.RetryInProgress as exc:  # nothing new started; the current state comes back
            return Response({**_detail(obj).data, 'detail': str(exc), 'code': 'retry_in_progress'}, status=409)
        except svc.EvidenceRequestError as exc:
            raise ValidationError({'detail': str(exc)})
        return _detail(obj)
