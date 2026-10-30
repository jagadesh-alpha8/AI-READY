"""Tenant-scoped API. Reads never create runs, dispatch work or spend model credits."""
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint
from apps.scoring.models import CapabilityExecution
from apps.sprints.access import get_authorized_sprint
from config.pagination import DefaultPageNumberPagination
from .execution import finish, start


class StartSerializer(serializers.Serializer):
    population = serializers.CharField(max_length=2000)
    reference_period = serializers.CharField(max_length=200)


def summary(execution):
    done = execution.run.events.filter(payload__kind='indicator').count()
    return {'id': str(execution.run_id), 'status': execution.status, 'completed_indicators': done,
            'total_indicators': 36, 'requests_reserved': execution.requests_reserved,
            'reserved_cost_usd': str(execution.usd_reserved), 'created_at': execution.created_at,
            'heartbeat_at': execution.heartbeat_at,
            'stalled': execution.status in {'queued', 'running'} and execution.heartbeat_at < (
                timezone.now() - timedelta(seconds=settings.CAPABILITY_STALE_SECONDS)),
            'rubric_version': execution.run.inputs['rubric'].get('version'),
            'reference_period': execution.run.inputs['reference_period']}


class CapabilityRunsView(APIView):
    permission_classes = [CanManageSprint]

    def get(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        rows = CapabilityExecution.objects.filter(sprint=sprint).select_related('run').order_by('-created_at', '-run_id')
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([summary(row) for row in page])
        response.data['enabled'] = settings.CAPABILITY_ASSESSMENT_ENABLED
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
        return Response({**summary(execution), 'reused': not created}, status=202 if created else 200)


class RunView(APIView):
    permission_classes = [CanManageSprint]

    def authorized(self, request, sprint_id, run_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        return get_object_or_404(CapabilityExecution.objects.select_related('run'), run_id=run_id, sprint=sprint)

    def get(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        # One completion event owns every output. Partial runs never expose a headline score.
        completed = execution.run.events.filter(state='completed', payload__result__isnull=False).last()
        terminal = execution.run.events.filter(state__in=['failed', 'cancelled'], payload__error_code__isnull=False).last()
        indicators = execution.run.events.filter(payload__kind='indicator')
        return Response({**summary(execution), 'inputs_hash': execution.run.inputs_hash,
            'population': execution.run.inputs['population'], 'profile': execution.run.inputs['profile'],
            'source_manifest': execution.run.inputs['manifest'],
            'assessment': completed.payload if completed else None,
            'partial_decisions': [] if completed else [r for event in indicators for r in event.payload['records']],
            'error': terminal.payload if terminal else None})


class CancelRunView(RunView):
    def post(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        changed = finish(execution.run_id, 'cancelled', 'cancelled_by_user')
        execution.refresh_from_db()
        return Response({**summary(execution), 'changed': changed,
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
