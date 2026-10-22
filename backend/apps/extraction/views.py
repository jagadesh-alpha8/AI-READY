import datetime
import logging

from celery.exceptions import Retry as CeleryRetry
from celery import current_app
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanContribute, IsConsultant, IsInstitutionMember, IsSuperAdmin
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
    permission_classes = [CanContribute]

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
            documents = list(selected)
        else:
            documents = list(self._eligible_documents(sprint))

        # Flip the sprint to 'processing' *before* dispatching: with
        # CELERY_TASK_ALWAYS_EAGER (as in tests, and possible in a
        # synchronous worker setup) `.delay()` below runs the task inline,
        # and the task's own "advance to reviewing once nothing's left
        # active" check only fires while the sprint is 'processing'. Setting
        # it after dispatch would race an eagerly-completed job.
        # One explicitly chosen document (Upload Data Pack's "Process again", whatever its status) is run
        # again even when complete -- as its existing job row, so it never gets a second processing record.
        jobs = self._prepare_jobs(sprint, documents, rerun_completed=bool(document_id))
        if jobs and sprint.status in (Sprint.Status.COLLECTING, Sprint.Status.REVIEWING):
            sprint.status = Sprint.Status.PROCESSING
            sprint.save(update_fields=['status', 'updated_at'])

        created_jobs = [dispatch_job(job) for job in jobs]

        return Response(ExtractionJobSerializer(created_jobs, many=True).data, status=201)

    @staticmethod
    def _eligible_documents(sprint):
        """Every non-rejected sprint document without a completed or active job.

        This deliberately does not filter on Document.status: legacy documents
        can say PROCESSED without having a sprint-specific ExtractionJob. They
        still need a job and fresh facts in this sprint. Failed/stopped jobs are
        reused by _prepare_jobs rather than duplicated.
        """
        handled_document_ids = ExtractionJob.objects.filter(sprint=sprint).filter(
            Q(status__in=ACTIVE_STATUSES) | _COMPLETE_JOB,
        ).values_list('document_id', flat=True)
        # A version replaced by a newer upload is history: the same set of documents the processing summary
        # counts (services/completeness.included_documents), so "process everything left" never runs an
        # outdated file. One can still be selected explicitly (document_id / document_ids).
        return (sprint.documents.exclude(status=Document.Status.REJECTED).filter(superseded_at__isnull=True)
                .exclude(id__in=handled_document_ids))

    @staticmethod
    def _prepare_jobs(sprint, documents, rerun_completed=False):
        """Create one job per newly included document, or reuse its retryable job.

        The document row is locked and the partial unique constraint is the
        final guard against simultaneous requests. A completed/active job is
        never duplicated by clicking Process again.
        """
        jobs = []
        for candidate in documents:
            try:
                with transaction.atomic():
                    document = Document.objects.select_for_update().get(id=candidate.id, sprint=sprint)
                    queryset = ExtractionJob.objects.select_for_update().filter(document=document)
                    if queryset.filter(status__in=ACTIVE_STATUSES).exists():
                        continue
                    if not rerun_completed and queryset.filter(_COMPLETE_JOB).exists():
                        continue
                    # A failed / stopped / partially extracted attempt is run again as the same row.
                    retryable = (_RETRYABLE_JOB | Q(status=ExtractionJob.Status.COMPLETED)) if rerun_completed else _RETRYABLE_JOB
                    job = queryset.filter(retryable).order_by('-created_at').first()
                    if job is not None:
                        _reset(job)
                        job.save()
                    else:
                        job = ExtractionJob.objects.create(sprint=sprint, document=document)
                    jobs.append(job)
            except (Document.DoesNotExist, IntegrityError):
                # A concurrent request may have queued this document while we
                # waited. It is already represented by its active job.
                continue
        return jobs


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
    permission_classes = [CanContribute, IsInstitutionMember]

    def perform_destroy(self, instance):
        if instance.status != ExtractionJob.Status.FAILED:
            raise ValidationError(
                f"Cannot delete a job in '{instance.status}' status. Only failed jobs can be deleted.",
            )
        instance.delete()


#: A job the user can run again with the Process button.
REPROCESSABLE_STATUSES = [ExtractionJob.Status.FAILED, ExtractionJob.Status.CANCELLED]
#: Completed AND everything was read -- never queued again by "Process" / "Process incomplete".
_COMPLETE_JOB = Q(status=ExtractionJob.Status.COMPLETED) & ~Q(completeness=ExtractionJob.Completeness.PARTIAL)
#: Failed, stopped, or completed with chunks / pages missing: run again as the same row.
_RETRYABLE_JOB = Q(status__in=REPROCESSABLE_STATUSES) | Q(
    status=ExtractionJob.Status.COMPLETED, completeness=ExtractionJob.Completeness.PARTIAL)


def _is_retryable(job):
    return job.status in REPROCESSABLE_STATUSES or (
        job.status == ExtractionJob.Status.COMPLETED and job.completeness == ExtractionJob.Completeness.PARTIAL)


def _reset(job):
    """Back to pending for another attempt, forgetting the previous attempt's outcome (not its facts:
    those are re-persisted idempotently by field_key, and reviewed ones are never overwritten)."""
    job.status = ExtractionJob.Status.PENDING
    job.current_step = ''
    job.progress_percentage = 0
    job.error_message = ''
    job.retry_count = 0
    job.started_at = None
    job.completed_at = None
    job.celery_task_id = ''
    job.completeness = ''
    job.extraction_warnings = []
    job.chunks_total = job.chunks_completed = 0


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
    _reset(job)
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
    permission_classes = [CanContribute, IsInstitutionMember]

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        cancelled_count = sum(
            _cancel_job(job) for job in ExtractionJob.objects.filter(sprint=sprint, status__in=ACTIVE_STATUSES)
        )
        _settle_sprint_after_stop(sprint)
        return Response({'cancelled_count': cancelled_count}, status=status.HTTP_200_OK)


class ExtractionJobCancelView(APIView):
    """Stop one document's job (the per-row Stop button)."""
    permission_classes = [CanContribute, IsInstitutionMember]

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
    permission_classes = [CanContribute, IsInstitutionMember]

    @extend_schema(request=None, responses=ExtractionJobSerializer)
    def post(self, request, pk):
        job = get_object_or_404(ExtractionJob.objects.select_related('sprint', 'document'), pk=pk)
        get_authorized_sprint(request.user, job.sprint_id)
        if not _is_retryable(job):
            raise ValidationError(
                {'detail': 'Only failed, stopped or partially extracted jobs can be processed again '
                           f'(this one is {job.status}).'},
            )
        return Response(ExtractionJobSerializer(_requeue(job)).data)


class SprintExtractionProcessIncompleteView(APIView):
    """Process all sprint documents without a completed or active job.

    Documents with no job are included too; failed/stopped attempts reuse the
    existing job row so retries do not create duplicate processing history.
    """
    permission_classes = [CanContribute, IsInstitutionMember]

    @extend_schema(request=None, responses=ExtractionJobSerializer(many=True))
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        jobs = SprintExtractionJobListCreateView._prepare_jobs(
            sprint, SprintExtractionJobListCreateView._eligible_documents(sprint),
        )
        if jobs and sprint.status in (Sprint.Status.COLLECTING, Sprint.Status.REVIEWING):
            sprint.status = Sprint.Status.PROCESSING
            sprint.save(update_fields=['status', 'updated_at'])
        dispatched = [dispatch_job(job) for job in jobs]
        return Response(ExtractionJobSerializer(dispatched, many=True).data)


class SprintProcessingSummaryView(APIView):
    """GET: how completely the sprint's included documents are processed -- counts per state (complete,
    partial, failed, active, not processed) and each document's state and warnings
    (services/completeness.py). Read-only; institution-scoped like the sprint itself."""
    permission_classes = [IsInstitutionMember]

    def get(self, request, sprint_id):
        from .services.completeness import describe, processing_summary
        sprint = get_authorized_sprint(request.user, sprint_id)
        summary = processing_summary(sprint)
        return Response({**summary, 'description': describe(summary)})


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
