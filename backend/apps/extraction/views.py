import datetime
import logging

from celery.exceptions import Retry as CeleryRetry
from celery import current_app
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsConsultant, IsInstitutionMember, IsSuperAdmin
from apps.documents.models import Document
from apps.sprints.access import get_authorized_sprint
from apps.sprints.models import Sprint

from .models import AIUsage, ExtractionJob
from .serializers import ExtractionJobCreateSerializer, ExtractionJobSerializer
from .tasks import run_extraction_job
from .usage import billing_rows, summarize_usage

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = [ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING]


class SprintExtractionJobListCreateView(generics.ListCreateAPIView):
    serializer_class = ExtractionJobSerializer

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return ExtractionJob.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related('document').annotate(
            ai_input_tokens=Sum('ai_usage__input_tokens'),
            ai_output_tokens=Sum('ai_usage__output_tokens'),
            ai_cost_usd=Sum('ai_usage__cost_usd'),
        )

    @extend_schema(request=ExtractionJobCreateSerializer, responses=ExtractionJobSerializer(many=True))
    def create(self, request, *args, **kwargs):
        sprint = get_authorized_sprint(request.user, self.kwargs['sprint_id'])

        body = ExtractionJobCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        document_id = body.validated_data.get('document_id')
        document_ids = set(body.validated_data.get('document_ids') or [])

        if document_id:
            documents = list(Document.objects.filter(id=document_id, sprint=sprint))
            if not documents:
                raise NotFound('Document not found in this sprint.')
        elif document_ids:
            selected = Document.objects.filter(id__in=document_ids, sprint=sprint)
            if selected.count() != len(document_ids):
                raise NotFound('One or more selected documents were not found in this sprint.')
            # Skip any selected document that is already mid-extraction, so a
            # double click can't queue the same document twice.
            active_document_ids = ExtractionJob.objects.filter(
                sprint=sprint, status__in=ACTIVE_STATUSES,
            ).values_list('document_id', flat=True)
            documents = list(selected.exclude(id__in=active_document_ids))
        else:
            documents = list(self._eligible_documents(sprint))

        # Flip the sprint to 'processing' *before* dispatching: with
        # CELERY_TASK_ALWAYS_EAGER (as in tests, and possible in a
        # synchronous worker setup) `.delay()` below runs the task inline,
        # and the task's own "advance to reviewing once nothing's left
        # active" check only fires while the sprint is 'processing'. Setting
        # it after dispatch would race an eagerly-completed job.
        if documents and sprint.status == Sprint.Status.COLLECTING:
            sprint.status = Sprint.Status.PROCESSING
            sprint.save(update_fields=['status', 'updated_at'])

        created_jobs = [self._create_and_dispatch(sprint, document) for document in documents]

        return Response(ExtractionJobSerializer(created_jobs, many=True).data, status=201)

    @staticmethod
    def _eligible_documents(sprint):
        """Every document ready to (re)process and not already mid-flight."""
        active_document_ids = ExtractionJob.objects.filter(
            sprint=sprint, status__in=ACTIVE_STATUSES,
        ).values_list('document_id', flat=True)
        return sprint.documents.filter(
            status__in=[Document.Status.UPLOADED, Document.Status.FAILED],
        ).exclude(id__in=active_document_ids)

    @staticmethod
    def _create_and_dispatch(sprint, document):
        job = ExtractionJob.objects.create(sprint=sprint, document=document)
        return dispatch_job(job)


def dispatch_job(job):
    """Queue `job` on Celery and record its task id -- shared by a new run and
    by re-processing an existing failed/stopped job."""
    try:
        result = run_extraction_job.delay(str(job.id))
        job.celery_task_id = result.id
        job.save(update_fields=['celery_task_id'])
        # With CELERY_TASK_ALWAYS_EAGER, the line above just ran the
        # task inline against a separately-fetched row -- reload so the
        # response reflects what actually happened, not this stale
        # in-memory copy from right after create().
        job.refresh_from_db()
    except CeleryRetry:
        # Only reachable with CELERY_TASK_ALWAYS_EAGER (tests, or a
        # synchronous worker setup), where `.delay()` runs the task
        # inline: the task itself already recorded the retry (status,
        # retry_count, backoff) before raising this. In real deployments
        # `.delay()` only publishes to the broker and returns
        # immediately, so this is never raised here.
        job.refresh_from_db()
    except Exception as exc:
        logger.error('extraction.dispatch.broker_unreachable job_id=%s error=%s', job.id, exc)
        job.status = ExtractionJob.Status.FAILED
        job.error_message = f'Could not reach the Celery broker: {exc}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    return job


class ExtractionJobDetailView(generics.RetrieveDestroyAPIView):
    queryset = ExtractionJob.objects.select_related('sprint', 'document')
    serializer_class = ExtractionJobSerializer
    lookup_field = 'pk'
    permission_classes = [IsInstitutionMember]

    def perform_destroy(self, instance):
        if instance.status != ExtractionJob.Status.FAILED:
            raise ValidationError(
                f"Cannot delete a job in '{instance.status}' status. Only failed jobs can be deleted.",
            )
        instance.delete()


#: A job the user can run again with the Process button.
REPROCESSABLE_STATUSES = [ExtractionJob.Status.FAILED, ExtractionJob.Status.CANCELLED]


def _cancel_job(job):
    """Stop one job. A queued job is skipped by the worker when it reaches it;
    a running one stops at its next checkpoint (between steps or AI calls) --
    see ExtractionCancelled. No hard kill: terminating a worker mid-write
    could leave half-saved facts. Returns False if the job wasn't active."""
    now = timezone.now()
    stopped = ExtractionJob.objects.filter(id=job.id, status__in=ACTIVE_STATUSES).update(
        status=ExtractionJob.Status.CANCELLED, completed_at=now, updated_at=now,
    )
    if not stopped:
        return False
    if job.celery_task_id:
        try:
            current_app.control.revoke(job.celery_task_id)
        except Exception as exc:  # broker hiccup: the DB status still stops it
            logger.warning('extraction.cancel.revoke_failed job_id=%s error=%s', job.id, exc)
    return True


def _settle_sprint_after_stop(sprint):
    """Nothing left running: leave 'processing' so the sprint isn't stuck."""
    still_active = ExtractionJob.objects.filter(sprint=sprint, status__in=ACTIVE_STATUSES).exists()
    if not still_active and sprint.status == Sprint.Status.PROCESSING:
        sprint.status = Sprint.Status.COLLECTING
        sprint.save(update_fields=['status', 'updated_at'])


def _requeue(job):
    """Reset a failed/stopped job and run it again, keeping it as one row."""
    if ExtractionJob.objects.filter(
        document_id=job.document_id, status__in=ACTIVE_STATUSES,
    ).exclude(id=job.id).exists():
        raise ValidationError({'detail': f"'{job.document.original_filename}' is already being processed."})
    job.status = ExtractionJob.Status.PENDING
    job.current_step = ''
    job.progress_percentage = 0
    job.error_message = ''
    job.retry_count = 0
    job.started_at = None
    job.completed_at = None
    job.celery_task_id = ''
    job.save()
    sprint = job.sprint
    if sprint.status in (Sprint.Status.COLLECTING, Sprint.Status.REVIEWING):
        # Back to 'processing' so the end-of-batch gap pass runs again once
        # this finishes (it is idempotent -- no duplicate gaps).
        sprint.status = Sprint.Status.PROCESSING
        sprint.save(update_fields=['status', 'updated_at'])
    return dispatch_job(job)


class SprintExtractionCancelView(APIView):
    """Stop Processing: stop every queued/running job in the sprint."""
    permission_classes = [IsInstitutionMember]

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        cancelled_count = sum(
            _cancel_job(job) for job in ExtractionJob.objects.filter(sprint=sprint, status__in=ACTIVE_STATUSES)
        )
        _settle_sprint_after_stop(sprint)
        return Response({'cancelled_count': cancelled_count}, status=status.HTTP_200_OK)


class ExtractionJobCancelView(APIView):
    """Stop one document's job (the per-row Stop button)."""
    permission_classes = [IsInstitutionMember]

    @extend_schema(request=None, responses=ExtractionJobSerializer)
    def post(self, request, pk):
        job = get_object_or_404(ExtractionJob.objects.select_related('sprint', 'document'), pk=pk)
        get_authorized_sprint(request.user, job.sprint_id)
        if not _cancel_job(job):
            raise ValidationError({'detail': f'This job is already {job.status}; there is nothing to stop.'})
        _settle_sprint_after_stop(job.sprint)
        job.refresh_from_db()
        return Response(ExtractionJobSerializer(job).data)


class ExtractionJobProcessView(APIView):
    """Run a failed or stopped job again (the per-row Process button)."""
    permission_classes = [IsInstitutionMember]

    @extend_schema(request=None, responses=ExtractionJobSerializer)
    def post(self, request, pk):
        job = get_object_or_404(ExtractionJob.objects.select_related('sprint', 'document'), pk=pk)
        get_authorized_sprint(request.user, job.sprint_id)
        if job.status not in REPROCESSABLE_STATUSES:
            raise ValidationError(
                {'detail': f'Only failed or stopped jobs can be processed again (this one is {job.status}).'},
            )
        return Response(ExtractionJobSerializer(_requeue(job)).data)


class SprintExtractionProcessIncompleteView(APIView):
    """Process every not-completed document again: the latest failed/stopped
    job of each document that has no completed or active job."""
    permission_classes = [IsInstitutionMember]

    @extend_schema(request=None, responses=ExtractionJobSerializer(many=True))
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        done_or_active = set(ExtractionJob.objects.filter(
            sprint=sprint, status__in=[*ACTIVE_STATUSES, ExtractionJob.Status.COMPLETED],
        ).values_list('document_id', flat=True))
        latest_per_document = {}
        for job in ExtractionJob.objects.filter(
            sprint=sprint, status__in=REPROCESSABLE_STATUSES,
        ).select_related('sprint', 'document').order_by('-created_at'):
            if job.document_id not in done_or_active:
                latest_per_document.setdefault(job.document_id, job)
        requeued = [_requeue(job) for job in latest_per_document.values()]
        return Response(ExtractionJobSerializer(requeued, many=True).data)


class SprintAIUsageView(APIView):
    """GET: AI tokens and cost for a sprint -- totals, by stage, by model and
    the costliest documents. Optional ?since=YYYY-MM-DD&until=YYYY-MM-DD
    (inclusive dates) to bill a period."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        queryset = AIUsage.objects.filter(sprint=sprint)
        for param, lookup in (('since', 'created_at__date__gte'), ('until', 'created_at__date__lte')):
            value = request.query_params.get(param)
            if value:
                try:
                    queryset = queryset.filter(**{lookup: datetime.date.fromisoformat(value)})
                except ValueError:
                    raise ValidationError({param: 'Use a date like 2026-10-31.'})
        return Response({'sprint_id': str(sprint.id), **summarize_usage(queryset)})


class PlatformAIUsageView(APIView):
    """GET (super admin / InGage consultant only): AI tokens and cost across
    all institutions -- the admin "AI Usage & Billing" page. Totals plus one
    row per institution x sprint x month. Filters: ?since=YYYY-MM-DD,
    ?until=YYYY-MM-DD (inclusive), ?institution=<uuid>."""
    permission_classes = [IsSuperAdmin | IsConsultant]

    def get(self, request):
        queryset = AIUsage.objects.all()
        for param, lookup in (('since', 'created_at__date__gte'), ('until', 'created_at__date__lte')):
            value = request.query_params.get(param)
            if value:
                try:
                    queryset = queryset.filter(**{lookup: datetime.date.fromisoformat(value)})
                except ValueError:
                    raise ValidationError({param: 'Use a date like 2026-10-31.'})
        institution = request.query_params.get('institution')
        if institution:
            queryset = queryset.filter(institution_id=institution)
        totals = summarize_usage(queryset, top_documents=0)
        totals.pop('top_documents', None)
        return Response({**totals, 'rows': billing_rows(queryset)})
