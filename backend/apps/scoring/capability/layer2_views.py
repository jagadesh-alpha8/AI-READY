"""Second assessment layer API (skeleton): the questionnaire's second line, one item at a time, and optional
additional evidence. Under /api/v1/sprints/{sprint}/capability-runs/{run}/:

    GET  questions                               next item (a follow-up first, else the next open question) + progress
                                                 ?list=1 also returns every question with its latest answer, in rank
                                                 order (for "Previous" and an overview of the questionnaire)
    POST questions/{question}/responses          {answer, document_ids, skip, choice}: choice = yes | partly | not_yet
                                                 (the answer options; not_yet is recorded like a skip)
    POST questions/{question}/to-check           {to_check: true|false}: "I need to check", a saved mark on an open
                                                 question; it stays open and moves behind the unmarked ones
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
    """A question; a group's lead also lists the questions it answers (\"Also answers: ...\" on the screen: they are
    never served on their own, so without this list the front end could not show them; Jagadesh, 22 Nov)."""
    out = {'id': str(question.pk), 'rank': question.rank, 'kind': question.kind, 'text': question.text,
           'indicator_code': question.indicator_code, 'condition_ids': question.condition_ids,
           'status': question.status, 'points_at_stake': float(question.points_at_stake),
           'to_check': question.to_check, 'to_check_at': question.to_check_at,
           'linked_to': str(question.linked_to_id) if question.linked_to_id else None}
    if question.linked_to_id is None:
        out['linked'] = [{'id': str(q.pk), 'rank': q.rank, 'indicator_code': q.indicator_code,
                          'condition_ids': q.condition_ids, 'status': q.status,
                          'points_at_stake': float(q.points_at_stake), 'text': q.text}
                         for q in question.linked.order_by('rank')]
    return out


def serialize_response(response):
    check = response.support_check or {}
    return {'id': str(response.pk), 'question_id': str(response.question_id),
            'parent_id': str(response.parent_id) if response.parent_id else None, 'kind': response.kind,
            'choice': response.choice or None, 'answer': response.answer, 'document_ids': response.document_ids, 'status': response.status,
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
    # The college's own screens (questions, answers, evidence) follow the result's visibility; the job controls are
    # the operator's and keep working on an unpublished result, which is how its text gets written.
    follows_visibility = True

    def execution(self, request, sprint_id, run_id):
        from .publication import require_visible
        sprint = get_authorized_sprint(request.user, sprint_id)
        execution = get_object_or_404(CapabilityExecution.objects.select_related('run'), run_id=run_id, sprint=sprint)
        # The follow-up stage belongs to a result the college can see: a college login gets no questions, answers or
        # jobs for a Stage 1 result that is not published to it (staff: every run).
        if self.follows_visibility:
            require_visible(request.user, execution)
        return execution

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
                                      skip=flag(request.data.get('skip')), parent=parent, user=request.user,
                                      choice=str(request.data.get('choice') or ''))
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


NOTICE_VERSION = 'questionnaire-notice-3'


def questionnaire_notice(run):
    """The text shown before the follow-up questions (agreed 23 Nov), with the points the answers can earn back.
    Served with the questions so the screen and the reports use one wording. Once the stage is closed (the final
    result published), `closed` is true and `closed_text` says so; the front end shows it instead of the invitation."""
    from .layer2_service import stage_closed
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    held = ((event.payload.get('result') or {}).get('depth_reserve') or {}) if event else {}
    points = held.get('held_points') or 0
    worth = f', up to {points:g} points in total' if points else ''
    closed = stage_closed(run)
    return {'version': NOTICE_VERSION, 'title': 'Before you start', 'points': points, 'closed': closed,
            'intro': ('These questions follow up on your documents. Part of the score your documents earned is on hold '
                      f'until your answers confirm how far the evidence goes{worth}. The questions come in order of how '
                      'much they are worth, so the first ones matter most, and you can stop whenever you like.'),
            'rules': ['An answer counts only when a document supports it, so attach one wherever you can.',
                      'If something is not in place, say so: "Not yet in place" never lowers your score. '
                      'If you are not sure, choose "I need to check" and come back to it.',
                      'Please answer as accurately as you can. If a document you send shows something different from '
                      'what we credited, we adjust that part of the score, up or down. Accurate answers also make '
                      'your improvement plan more useful.'],
            **({'closed_text': 'The follow-up stage is closed and your final AI-READY Score has been published.'}
               if closed else {})}


class QuestionsView(_RunScoped):
    def get(self, request, sprint_id, run_id):
        execution = self.execution(request, sprint_id, run_id)
        run_ref = str(execution.run_id)
        item = service.next_item(run_ref)
        next_payload = None
        if item is not None:
            next_payload = {'type': item['type'], 'text': item['text'], 'question': serialize_question(item['question']),
                            'response_id': str(item['response'].pk) if item['response'] is not None else None}
        body = {'next': next_payload, 'progress': service.progress(run_ref),
                'notice': questionnaire_notice(execution.run)}
        if flag(request.query_params.get('list')):
            # Every question the college sees (linked members are answered through their lead), with its latest
            # top-level answer, so the screen can go back to an earlier question and show what was sent.
            questions = (DepthQuestion.objects.filter(run_ref=run_ref, linked_to__isnull=True)
                         .prefetch_related('linked').order_by('rank'))
            latest = {}
            for r in DepthResponse.objects.filter(question__run_ref=run_ref, parent__isnull=True).order_by('created_at'):
                latest[r.question_id] = r
            body['questions'] = [{**serialize_question(q), 'response': serialize_response(latest[q.pk])
                                  if q.pk in latest else None} for q in questions]
        return Response(body)


class QuestionResponsesView(_RunScoped):
    def post(self, request, sprint_id, run_id, question_id):
        execution = self.execution(request, sprint_id, run_id)
        question = get_object_or_404(DepthQuestion, pk=question_id, run_ref=str(execution.run_id))
        return self.answer(request, execution, question)


class ToCheckView(_RunScoped):
    def post(self, request, sprint_id, run_id, question_id):
        execution = self.execution(request, sprint_id, run_id)
        question = get_object_or_404(DepthQuestion, pk=question_id, run_ref=str(execution.run_id))
        try:
            question = service.mark_to_check(question, flag(request.data.get('to_check', True)), user=request.user)
        except Layer2Error as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serialize_question(question))


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
    follows_visibility = False
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
    follows_visibility = False
    def get(self, request, sprint_id, run_id, job_id):
        execution = self.execution(request, sprint_id, run_id)
        return Response(jobs.summary(get_object_or_404(SecondLayerJob, pk=job_id, run=execution.run)))


class JobCancelView(_RunScoped):
    follows_visibility = False
    def post(self, request, sprint_id, run_id, job_id):
        execution = self.execution(request, sprint_id, run_id)
        job = get_object_or_404(SecondLayerJob, pk=job_id, run=execution.run)
        changed = jobs.finish(job.pk, 'cancelled', 'cancelled_by_user')
        job.refresh_from_db()
        return Response({**jobs.summary(job), 'changed': changed,
                         'note': 'A call already in flight may finish and be billed; no further calls start and '
                                 'nothing more is saved.'})
