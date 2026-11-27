"""Tenant-scoped API. Reads never create runs, dispatch work or spend model credits."""
import logging
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint, IsInGageStaff
from apps.scoring.models import CapabilityExecution
from apps.sprints.access import get_authorized_sprint
from config.pagination import DefaultPageNumberPagination
from .execution import finish, start
from .engine import DEFAULT_METHODOLOGY, ENGINE_VERSION
from .evaluation import PROMPT_VERSION, RETRIEVAL_VERSION

logger = logging.getLogger(__name__)


class StartSerializer(serializers.Serializer):
    confirmed_source_institution = serializers.CharField(max_length=250, required=False)
    population = serializers.CharField(max_length=2000, required=False)
    reference_period = serializers.CharField(max_length=200, required=False)
    scope_mode = serializers.ChoiceField(choices=['default', 'custom'], required=False)
    refines_run_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        from .scope import intent
        try:
            intent(**attrs)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        return attrs


def summary(execution, view=None):
    """One run as the run list shows it, from its display copy (run_view.py): never the run's inputs or events."""
    if view is None:
        # Taken from select_related('run__view') where the caller used it; never by loading the run itself.
        run = execution._state.fields_cache.get('run')
        view = run._state.fields_cache.get('view') if run is not None else None
    if view is None:
        from .run_view import ensure
        view = ensure(execution.run_id, complete=False)
    final = view.stage == 'final'
    # A final run (second layer) is published whole, without per-indicator checkpoints.
    done = 36 if final and execution.status == 'completed' else view.indicators_done
    if execution.status == 'completed' and not final and view.event_id is None:
        # The copy was not stored when the run completed (logged; run_view._safely): count from the events instead.
        from .run_view import _indicator_count
        done = _indicator_count(execution.run_id)
    return {'id': str(execution.run_id), 'status': execution.status, 'completed_indicators': done,
            'stage': 'final' if final else 'provisional',
            'provisional_run_id': view.provisional_run_id or None if final else None,
            'total_indicators': 36, 'requests_reserved': execution.requests_reserved,
            'reserved_cost_usd': str(execution.usd_reserved), 'created_at': execution.created_at,
            'heartbeat_at': execution.heartbeat_at,
            'stalled': _stalled(execution),
            'rubric_version': view.rubric_version or None,
            'current_rubric_version': DEFAULT_METHODOLOGY,
            'current_assessment_protocol': {'engine_version': ENGINE_VERSION, 'prompt_version': PROMPT_VERSION, 'retrieval_version': RETRIEVAL_VERSION},
            'assessment_protocol_current': (view.engine_version == ENGINE_VERSION and view.prompt_version == PROMPT_VERSION
                                            and view.retrieval_version == RETRIEVAL_VERSION),
            'reference_period': view.reference_period,
            'refines_run_id': view.refines_run_id or None}


def _scope(run_id):
    from .run_view import inputs_part
    return (inputs_part(run_id, 'scope') or {}).get('scope')


def _stalled(execution):
    return execution.status in {'queued', 'running'} and execution.heartbeat_at < (
        timezone.now() - timedelta(seconds=settings.CAPABILITY_STALE_SECONDS))


class CapabilityRunsView(APIView):
    permission_classes = [CanManageSprint]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        # Never the run's inputs (every frozen page's text) or its events: the list reads the display copies.
        rows = (CapabilityExecution.objects.filter(sprint=sprint).select_related('run', 'run__view')
                .defer('run__inputs').order_by('-created_at', '-run_id'))
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([summary(row) for row in page])
        response.data['enabled'] = settings.CAPABILITY_ASSESSMENT_ENABLED
        # The result the college sees (publication.py), wherever it sits in the list: the screens show this run, not
        # the newest completed one.
        from .publication import automatic, current, describe
        response.data['published'] = describe(current(sprint.pk))
        response.data['auto_publish'] = automatic()   # results publish themselves once their reports are ready
        # The review questions' count is its own call now (ReviewStatusView): it rebuilt the whole review queue,
        # which re-reads every page of the sprint, on every run-list call.
        return response

    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        serializer = StartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 100 or not all(c.isalnum() or c in '-_.' for c in key):
            raise serializers.ValidationError({'Idempotency-Key': 'Supply a unique key of 1–100 letters, digits, dots, dashes or underscores.'})
        execution, created = start(sprint=sprint, user=request.user, idempotency_key=key,
                                   **serializer.validated_data)
        execution.refresh_from_db()
        # The run's resolved scope (who and which period it assesses, the identity decision) stays in this answer;
        # only the list leaves it out.
        return Response({**summary(execution), 'scope': _scope(execution.run_id), 'reused': not created},
                        status=202 if created else 200)


class RunView(APIView):
    permission_classes = [CanManageSprint]

    def authorized(self, request, sprint_id, run_id):
        """The run's execution, for a user who may read it: a college login reads a completed run only once it is
        published to it (publication.require_visible)."""
        from .publication import require_visible
        sprint = get_authorized_sprint(request.user, sprint_id)
        execution = get_object_or_404(CapabilityExecution.objects.select_related('run'), run_id=run_id, sprint=sprint)
        require_visible(request.user, execution)
        return execution

    def get(self, request, sprint_id, run_id):
        """The run detail every screen reads (issue 60). By default it is served from the run's display copy
        (run_view.py): the assessment without the model traces, and without the reviewed evidence and scope (about
        3 MB that no screen reads). ?full=1 returns those as well (the earlier response); ?traces=1 also returns the
        traces. The version marker is sent as `version` and as the ETag: with If-None-Match the answer is 304 while
        nothing the response depends on has changed."""
        from .run_view import ensure, marker
        sprint = get_authorized_sprint(request.user, sprint_id)
        execution = get_object_or_404(CapabilityExecution.objects.select_related('run', 'run__view').defer('run__inputs'),
                                      run_id=run_id, sprint=sprint)
        from .publication import is_staff, require_visible
        require_visible(request.user, execution)   # before the 304: a college never learns an unpublished version
        staff = is_staff(request.user)
        # The full detail and the model traces are for InGage staff, like the JSON export (audit, 26 Nov): a college
        # login asking for them gets the screens' detail.
        traces = staff and request.query_params.get('traces') in ('1', 'true')
        full = staff and (traces or request.query_params.get('full') in ('1', 'true'))
        view = ensure(execution.run_id)
        stalled = _stalled(execution)
        version = marker(execution, view, stalled, 'traces' if traces else 'full' if full else 'light')
        headers = {'ETag': f'"{version}"', 'Cache-Control': 'private, no-cache'} if not full else {
            'Cache-Control': 'private, no-cache'}
        # Only the screens' detail is answered 304: the full detail's review_changes_since_assessment depends on the
        # sprint's current facts, which the marker does not follow.
        if not full and version in _etags(request.headers.get('If-None-Match', '')):
            return Response(status=304, headers=headers)
        if full or (view.event_id is not None and not view.verified):
            # An unverified copy goes the earlier way, which checks the run's integrity and fails as it always did.
            body = self.full(execution, view, traces)
        else:
            body = self.light(execution, view)
        if not staff and body.get('partial_decisions'):
            # A run still going (or stopped) has no published result: its judgments so far are for staff only. The
            # screens show progress from completed_indicators, never these (audit, 26 Nov).
            body['partial_decisions'] = []
        return Response({**body, 'version': version}, headers=headers)

    def light(self, execution, view):
        from .explanations import attach
        from .run_view import closed, explanation_row, inputs_part, plan
        run = execution.run
        parts = inputs_part(run.pk, 'population', 'profile', 'manifest', 'rubric', 'reference_period', 'retrieval_policy')
        # The key is tested here, not in SQL: there the database would unpack every event's payload to test it.
        terminal = next((e for e in run.events.filter(state__in=['failed', 'cancelled']).order_by('-id')
                         if 'error_code' in (e.payload or {})), None)
        assessment = deterministic = partial = None
        if view.event_id is not None:
            row = explanation_row(run.pk, view.event_id)
            assessment = attach(view.assessment, row['payload'] if row else None, closed=closed(view))
            deterministic = plan(run, view, parts)
            partial = []
        else:
            partial = [r for records in run.events.filter(payload__kind='indicator').order_by('id')
                       .values_list('payload__records', flat=True) for r in records or []]
        steps = _next_steps(run.pk, view.event_id, assessment, parts['manifest'], parts['profile'], deterministic,
                            view.stage == 'final', view.provisional_run_id)
        return {**summary(execution, view), 'deterministic_plan': deterministic, 'next_steps': steps,
                'standard': _standard(execution.run_id),
                'diagnostics': view.diagnostics if view.event_id is not None else None,
                'inputs_hash': run.inputs_hash, 'population': parts['population'], 'profile': parts['profile'],
                'source_manifest': parts['manifest'], 'assessment': assessment, 'partial_decisions': partial,
                'error': terminal.payload if terminal else None}

    def full(self, execution, view, traces):
        """The response as it was before the display copies (plus `version`): reads the whole run."""
        run = execution.run
        # One completion event owns every output. Partial runs never expose a headline score.
        completed = run.events.filter(state='completed', payload__result__isnull=False).last()
        terminal = run.events.filter(state__in=['failed', 'cancelled'], payload__error_code__isnull=False).last()
        indicators = run.events.filter(payload__kind='indicator')
        from .recommendations import build_inputs
        plan = build_inputs(run, completed, {}) if completed else None
        from .diagnostics import explain
        from .explanations import attach, latest
        from .layer2_service import stage_closed
        from .reviewed_evidence import snapshot
        from .storage import digest
        saved_review = run.inputs.get('reviewed_evidence')
        current_review = snapshot(execution.sprint)
        assessment = (attach(completed.payload, latest(run), closed=stage_closed(run))
                      if completed else None)
        if assessment is not None and not traces:
            # The model packets (about 40 MB in test 13) are for audits and the JSON report. ?traces=1 keeps them.
            assessment = {k: v for k, v in assessment.items() if k != 'traces'}
        steps = _next_steps(run.pk, completed.pk if completed else None, assessment, run.inputs['manifest'],
                            run.inputs['profile'], plan, view.stage == 'final', view.provisional_run_id)
        return {**summary(execution, view), 'scope': run.inputs.get('scope'), 'deterministic_plan': plan,
            'next_steps': steps, 'standard': _standard(execution.run_id),
            'diagnostics': explain(run.inputs, completed.payload) if completed else None,
            'reviewed_evidence': saved_review,
            'review_changes_since_assessment': digest(saved_review) != digest(current_review),
            'inputs_hash': run.inputs_hash,
            'population': run.inputs['population'], 'profile': run.inputs['profile'],
            'source_manifest': run.inputs['manifest'],
            'assessment': assessment,
            'partial_decisions': [] if completed else [r for event in indicators for r in event.payload['records']],
            'error': terminal.payload if terminal else None}


def _standard(run_id):
    """The standard version the run was scored under, and the older-version line (standard.for_run). Reads only
    the run's frozen standard, not its inputs."""
    from apps.scoring.models import CapabilityRun
    from .standard import for_run
    frozen = CapabilityRun.objects.filter(pk=run_id).values_list('inputs__standard', flat=True).first()
    return for_run({'standard': frozen} if frozen else {})


def _next_steps(run_id, event_id, assessment, manifest, profile, plan, final, provisional_run_id):
    """The written next steps and the checklist (next_steps.for_screens), or None for a run not completed. A failure
    here leaves the screens on their own fallback and never fails the detail."""
    if assessment is None:
        return None
    from .next_steps import for_screens
    try:
        return for_screens(run_id, event_id, assessment, manifest, profile, plan, final, provisional_run_id)
    except Exception:
        logger.exception('next steps could not be shaped for run %s', run_id)
        return None


def _etags(header):
    """The entity tags in an If-None-Match header, weak or strong (nginx marks an ETag weak when it gzips)."""
    tags = set()
    for part in header.split(','):
        part = part.strip()
        if part.startswith('W/'):
            part = part[2:]
        if len(part) >= 2 and part[0] == part[-1] == '"':
            tags.add(part[1:-1])
    return tags


class ReviewStatusView(APIView):
    """How many of line 1's review questions (before a run) still await an answer. Its own call: building the review
    queue re-reads every page of the sprint, and it ran on every run-list call (issue 60)."""
    permission_classes = [CanManageSprint]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        from apps.facts.review_queue import view as review_view
        review = review_view(sprint)
        return Response({'review_questions_awaiting': sum(1 for c in review['cases'] if c['state'] == 'awaiting')})


class CancelRunView(RunView):
    def post(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        changed = finish(execution.run_id, 'cancelled', 'cancelled_by_user')
        execution.refresh_from_db()
        return Response({**summary(execution), 'scope': _scope(execution.run_id), 'changed': changed,
                         'note': 'An in-flight provider request may finish and be billed. No further requests will start.'})


class RunEvidenceView(RunView):
    def get(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        run = execution.run
        completed = run.events.filter(state='completed', payload__result__isnull=False).last()
        records = completed.payload['records'] if completed else [
            r for e in run.events.filter(payload__kind='indicator') for r in e.payload['records']]
        condition_id = request.query_params.get('condition_id')
        if condition_id:
            known = {c['id'] for i in run.inputs['rubric']['indicators'] for c in i['conditions']}
            if condition_id not in known:
                raise serializers.ValidationError({'condition_id': 'Unknown requirement in this run rubric.'})
            records = [r for r in records if r['condition_id'] == condition_id]
        cited = {c['source_id'] for r in records for c in r['citations']}
        return Response({'run_id': str(run.pk), 'records': records,
            'sources': [s for s in run.inputs['sources'] if s['id'] in cited],
            'note': 'Frozen assessment excerpts. Original files use the existing authenticated document download endpoint.'})


class PublishSerializer(serializers.Serializer):
    run_id = serializers.UUIDField(allow_null=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PublicationView(APIView):
    """GET: the result the college sees and the history of that choice. POST {run_id, note}: publish a completed run,
    or withdraw the published one with run_id null. InGage staff only (publication.py)."""
    permission_classes = [IsInGageStaff]

    def get(self, request, sprint_id):
        from .publication import current, describe, history
        sprint = get_authorized_sprint(request.user, sprint_id)
        return Response({'published': describe(current(sprint.pk)), 'history': history(sprint.pk)})

    def post(self, request, sprint_id):
        from .publication import PublicationError, describe, history, publish
        sprint = get_authorized_sprint(request.user, sprint_id)
        body = PublishSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        run_id = body.validated_data['run_id']
        try:
            row, changed = publish(sprint, str(run_id) if run_id else None, request.user,
                                   body.validated_data.get('note', ''))
        except PublicationError as exc:
            raise serializers.ValidationError({'run_id': str(exc)})
        if changed:
            logger.info('capability publication: sprint %s now shows %s (by %s)', sprint.pk,
                        row.run_id or 'nothing', request.user.pk)
        return Response({'published': describe(row), 'changed': changed, 'history': history(sprint.pk)})


class ReportReadinessView(RunView):
    """Whether this run's summary and detailed reports are ready for the college (publication.readiness): the
    Reports page marks them Draft for staff, and tells a college they are still being written."""

    def get(self, request, sprint_id, run_id):
        from .publication import readiness
        sprint = get_authorized_sprint(request.user, sprint_id)
        execution = get_object_or_404(CapabilityExecution.objects.select_related('run').defer('run__inputs'),
                                      run_id=run_id, sprint=sprint)
        from .publication import require_visible
        require_visible(request.user, execution)
        return Response({'run_id': str(execution.run_id), **readiness(execution)})
