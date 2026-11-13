"""Second assessment layer API (skeleton): the questionnaire's second line, one item at a time, and optional
additional evidence. Under /api/v1/sprints/{sprint}/capability-runs/{run}/:

    GET  questions                               next item (a follow-up first, else the next open question) + progress
    POST questions/{question}/responses          {answer, document_ids, skip}
    GET  responses/{response}                    status, what the check found, the follow-up if one was asked
    POST responses/{response}/follow-up          {answer, document_ids, skip}: the one answer to that follow-up
    GET  additional-evidence                     submissions so far
    POST additional-evidence                     {document_ids, note, picked}: picked = areas, key indicators or
                                                 requirements the documents are for (at least one)

    GET  second-layer/jobs                       the run's background jobs and its second-layer budget
    POST second-layer/jobs                       {operation, options} + Idempotency-Key: questions | checks | depth |
                                                 rejudge (options: questions.replace, rejudge.publish)
    GET  second-layer/jobs/{job}                 one job: status, result, the final run it published
    POST second-layer/jobs/{job}/cancel          no further model calls; nothing more is saved

Documents are uploaded first through the existing document API and referenced by id; they must belong to the sprint.
An answer is checked when its documents have been extracted. With SECOND_LAYER_JOBS_ENABLED (production) a submission
requests a checks job, metered against the run's second-layer budget (second_layer_jobs.py). Without it, the answer is
checked in the request when SECOND_LAYER_CHECK_ON_SUBMIT is on (unmetered; development), otherwise by the
layer2_check_pending command.
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint
from apps.scoring.models import AdditionalEvidence, CapabilityExecution, DepthQuestion, DepthResponse, SecondLayerJob
from apps.sprints.access import get_authorized_sprint

from . import layer2_service as service
from . import second_layer_jobs as jobs
from .layer2 import Layer2Error


ANSWER_CHARS = 4000   # a reply is a claim and a pointer; documents carry the detail
NOTE_CHARS = 2000


def flag(value):
    """A boolean from JSON or a form field: "false", "0" and "" are false (bool("false") would be true)."""
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def serialize_question(question):
    return {'id': str(question.pk), 'rank': question.rank, 'kind': question.kind, 'text': question.text,
            'indicator_code': question.indicator_code, 'condition_ids': question.condition_ids,
            'status': question.status}


def serialize_response(response):
    check = response.support_check or {}
    return {'id': str(response.pk), 'question_id': str(response.question_id),
            'parent_id': str(response.parent_id) if response.parent_id else None, 'kind': response.kind,
            'answer': response.answer, 'document_ids': response.document_ids, 'status': response.status,
            'supported': response.supported, 'follow_up': response.follow_up_text or None,
            'dimensions': [{'dimension_id': d['dimension_id'], 'support': d['support'], 'note': d.get('note', '')}
                           for d in check.get('dimensions', [])],
            'passages_found': len(response.windows or []),
            'search': check.get('search', {}), 'created_at': response.created_at}


def serialize_additional(item):
    return {'id': str(item.pk), 'document_ids': item.document_ids, 'note': item.note, 'picked': item.picked,
            'routed_indicators': item.routing.get('indicators', []), 'unknown_picks': item.routing.get('unknown', []),
            'over_cap': item.routing.get('dropped', []), 'search': item.routing.get('search', {}), 'status': item.status,
            'passages_found': len(item.windows or []), 'created_at': item.created_at}


class _RunScoped(APIView):
    permission_classes = [CanManageSprint]

    def execution(self, request, sprint_id, run_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        return get_object_or_404(CapabilityExecution.objects.select_related('run'), run_id=run_id, sprint=sprint)

    @staticmethod
    def documents(execution, ids):
        """Document ids from the request, all belonging to this sprint, or a 400 response."""
        from apps.documents.models import Document
        ids = [str(i) for i in ids or []]
        clean = [i for i in (service._uuid(i) for i in ids) if i]
        if len(clean) != len(ids) or Document.objects.filter(pk__in=clean, sprint=execution.sprint).count() != len(set(clean)):
            return None, Response({'detail': 'Every document must be uploaded to this sprint first.'},
                                  status=status.HTTP_400_BAD_REQUEST)
        return clean, None

    def answer(self, request, execution, question, parent=None):
        documents, error = self.documents(execution, request.data.get('document_ids'))
        if error is not None:
            return error
        if len(str(request.data.get('answer') or '')) > ANSWER_CHARS:
            return Response({'detail': f'Keep the answer under {ANSWER_CHARS} characters; attach documents for the '
                                       'detail.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            response = service.submit(question, answer=request.data.get('answer') or '', document_ids=documents,
                                      skip=flag(request.data.get('skip')), parent=parent, user=request.user)
        except Layer2Error as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if response.status != DepthResponse.Status.PENDING:
            pass
        elif jobs.enabled():
            jobs.request_checks(execution.run, request.user, f'response-{response.pk}')
        elif settings.SECOND_LAYER_CHECK_ON_SUBMIT:
            from .depth import default_model
            try:
                service.check_response(response, default_model())
            except Exception:  # never surface provider errors; the answer is saved and the command checks it later
                response.refresh_from_db()
        return Response(serialize_response(response), status=status.HTTP_201_CREATED)


class QuestionsView(_RunScoped):
    def get(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        run_ref = str(execution.run_id)
        item = service.next_item(run_ref)
        next_payload = None
        if item is not None:
            next_payload = {'type': item['type'], 'text': item['text'], 'question': serialize_question(item['question']),
                            'response_id': str(item['response'].pk) if item['response'] is not None else None}
        return Response({'next': next_payload, 'progress': service.progress(run_ref)})


class QuestionResponsesView(_RunScoped):
    def post(self, request, sprint_id, run_id, question_id):
        execution = self.execution(request, sprint_id, run_id)
        question = get_object_or_404(DepthQuestion, pk=question_id, run_ref=str(execution.run_id))
        return self.answer(request, execution, question)


class ResponseView(_RunScoped):
    def get(self, request, sprint_id, run_id, response_id):
        execution = self.execution(request, sprint_id, run_id)
        response = get_object_or_404(DepthResponse, pk=response_id, question__run_ref=str(execution.run_id))
        return Response(serialize_response(response))


class FollowUpView(_RunScoped):
    def post(self, request, sprint_id, run_id, response_id):
        execution = self.execution(request, sprint_id, run_id)
        parent = get_object_or_404(DepthResponse.objects.select_related('question'), pk=response_id,
                                   question__run_ref=str(execution.run_id))
        return self.answer(request, execution, parent.question, parent=parent)


class AdditionalEvidenceView(_RunScoped):
    def get(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        items = AdditionalEvidence.objects.filter(run_ref=str(execution.run_id))
        return Response({'results': [serialize_additional(i) for i in items]})

    def post(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        documents, error = self.documents(execution, request.data.get('document_ids'))
        if error is not None:
            return error
        picked = request.data.get('picked') or []
        if not isinstance(picked, list):
            return Response({'detail': 'picked must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(str(request.data.get('note') or '')) > NOTE_CHARS:
            return Response({'detail': f'Keep the note under {NOTE_CHARS} characters.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            item = service.add_evidence(str(execution.run_id), execution.run.inputs['rubric'], document_ids=documents,
                                        note=request.data.get('note') or '', picked=picked, user=request.user)
        except Layer2Error as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if jobs.enabled():
            jobs.request_checks(execution.run, request.user, f'additional-{item.pk}')
        return Response(serialize_additional(item), status=status.HTTP_201_CREATED)


class JobsView(_RunScoped):
    def get(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        rows = SecondLayerJob.objects.filter(run=execution.run)[:100]
        return Response({'enabled': jobs.enabled(), 'budget': jobs.budget_summary(execution.run),
                         'results': [jobs.summary(job) for job in rows]})

    def post(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 100 or not all(c.isalnum() or c in '-_.' for c in key):
            raise serializers.ValidationError({'Idempotency-Key': 'Supply a unique key of 1–100 letters, digits, '
                                                                  'dots, dashes or underscores.'})
        if not isinstance(request.data, dict):
            raise serializers.ValidationError('Send an object: {"operation": ..., "options": {...}}.')
        unknown = set(request.data) - {'operation', 'options'}
        if unknown:
            raise serializers.ValidationError(f'Unknown fields: {", ".join(sorted(unknown))}.')
        job, created = jobs.start(run=execution.run, operation=request.data.get('operation'), user=request.user,
                                  key=key, options=request.data.get('options'))
        job.refresh_from_db()
        return Response({**jobs.summary(job), 'reused': not created}, status=202 if created else 200)


class JobView(_RunScoped):
    def get(self, request, sprint_id, run_id, job_id):
        execution = self.execution(request, sprint_id, run_id)
        return Response(jobs.summary(get_object_or_404(SecondLayerJob, pk=job_id, run=execution.run)))


class JobCancelView(_RunScoped):
    def post(self, request, sprint_id, run_id, job_id):
        execution = self.execution(request, sprint_id, run_id)
        job = get_object_or_404(SecondLayerJob, pk=job_id, run=execution.run)
        changed = jobs.finish(job.pk, 'cancelled', 'cancelled_by_user')
        job.refresh_from_db()
        return Response({**jobs.summary(job), 'changed': changed,
                         'note': 'A call already in flight may finish and be billed; no further calls start and '
                                 'nothing more is saved.'})
