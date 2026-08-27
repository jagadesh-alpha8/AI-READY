import logging

from celery.exceptions import Retry as CeleryRetry
from celery import current_app
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsInstitutionMember
from apps.documents.models import Document
from apps.sprints.access import get_authorized_sprint
from apps.sprints.models import Sprint

from .models import ExtractionJob
from .serializers import ExtractionJobCreateSerializer, ExtractionJobSerializer
from .tasks import run_extraction_job

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = [ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING]


class SprintExtractionJobListCreateView(generics.ListCreateAPIView):
    serializer_class = ExtractionJobSerializer

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return ExtractionJob.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related('document')

    @extend_schema(request=ExtractionJobCreateSerializer, responses=ExtractionJobSerializer(many=True))
    def create(self, request, *args, **kwargs):
        sprint = get_authorized_sprint(request.user, self.kwargs['sprint_id'])

        body = ExtractionJobCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        document_id = body.validated_data.get('document_id')

        if document_id:
            documents = list(Document.objects.filter(id=document_id, sprint=sprint))
            if not documents:
                raise NotFound('Document not found in this sprint.')
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


class SprintExtractionCancelView(APIView):
    permission_classes = [IsInstitutionMember]

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        active_jobs = ExtractionJob.objects.filter(
            sprint=sprint,
            status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING],
        )

        cancelled_count = 0
        for job in active_jobs:
            if job.celery_task_id:
                current_app.control.revoke(job.celery_task_id, terminate=True)
            
            job.status = ExtractionJob.Status.CANCELLED
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'completed_at', 'updated_at'])
            
            if job.document.status == Document.Status.PROCESSING:
                job.document.status = Document.Status.UPLOADED
                job.document.save(update_fields=['status', 'updated_at'])
            
            cancelled_count += 1

        if cancelled_count > 0:
            # If we cancelled everything, the sprint shouldn't be 'processing' anymore.
            # Revert it to 'collecting' so they can start again.
            if sprint.status == Sprint.Status.PROCESSING:
                sprint.status = Sprint.Status.COLLECTING
                sprint.save(update_fields=['status', 'updated_at'])

        return Response({'cancelled_count': cancelled_count}, status=status.HTTP_200_OK)
