"""Explicit generation POST, read-only snapshots, independent user workflow PATCH."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint
from apps.sprints.access import get_authorized_sprint
from apps.scoring.models import CapabilityRun, RecommendationExecution, RecommendationActionState
from config.pagination import DefaultPageNumberPagination
from .recommendation_execution import start, finish, summary, enabled


class RecommendationBase(APIView):
    permission_classes = [CanManageSprint]

    def run(self, request, sprint_id, run_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        return get_object_or_404(CapabilityRun, pk=run_id, sprint=sprint)

    def execution(self, request, sprint_id, run_id, snapshot_id):
        run = self.run(request, sprint_id, run_id)
        return get_object_or_404(RecommendationExecution.objects.select_related('snapshot'), run=run, snapshot_id=snapshot_id)


class RecommendationsView(RecommendationBase):
    def get(self, request, sprint_id, run_id):
        run = self.run(request, sprint_id, run_id)
        rows = RecommendationExecution.objects.filter(run=run).order_by('-created_at', '-snapshot_id')
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([summary(row) for row in page])
        response.data['enabled'] = enabled()
        return response

    def post(self, request, sprint_id, run_id):
        run = self.run(request, sprint_id, run_id)
        if request.data:
            raise serializers.ValidationError('This endpoint takes an empty body; inputs come from the frozen assessment.')
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 100 or not all(c.isalnum() or c in '-_.' for c in key):
            raise serializers.ValidationError({'Idempotency-Key': 'Supply a unique key of 1–100 letters, digits, dots, dashes or underscores.'})
        execution, created = start(run=run, user=request.user, key=key)
        execution.refresh_from_db()
        return Response({**summary(execution), 'reused': not created}, status=202 if created else 200)


class RecommendationDetailView(RecommendationBase):
    def get(self, request, sprint_id, run_id, snapshot_id):
        execution = self.execution(request, sprint_id, run_id, snapshot_id)
        snapshot = execution.snapshot
        completed = snapshot.events.filter(payload__kind='completed').last()
        terminal = snapshot.events.filter(payload__kind='terminal').last()
        inputs = snapshot.inputs
        return Response({**summary(execution), 'inputs_hash': snapshot.inputs_hash,
            'assessment_event_id': snapshot.assessment_event_id,
            'plan': {k: v for k, v in inputs.items() if k != 'execution_policy'},
            'tailoring': completed.payload if completed else None,
            'fallback': completed is None or completed.payload['mode'] == 'deterministic',
            'error': terminal.payload if terminal else None,
            'action_states': list(snapshot.action_states.order_by('condition_id').values(
                'condition_id', 'owner', 'feasibility', 'status', 'updated_at'))})


class RecommendationCancelView(RecommendationBase):
    def post(self, request, sprint_id, run_id, snapshot_id):
        execution = self.execution(request, sprint_id, run_id, snapshot_id)
        changed = finish(snapshot_id, 'cancelled', 'cancelled_by_user')
        execution.refresh_from_db()
        return Response({**summary(execution), 'changed': changed,
                         'note': 'An in-flight call may finish and be billed; no further calls will start.'})


class ActionStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationActionState
        fields = ['owner', 'feasibility', 'status']

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'fields': 'Only owner, feasibility and status may be changed.'})
        return super().to_internal_value(data)


class RecommendationActionView(RecommendationBase):
    def patch(self, request, sprint_id, run_id, snapshot_id, condition_id):
        execution = self.execution(request, sprint_id, run_id, snapshot_id)
        if condition_id not in {a['id'] for a in execution.snapshot.inputs['actions']}:
            raise serializers.ValidationError('Condition is not an action in this snapshot.')
        serializer = ActionStateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        state, _ = RecommendationActionState.objects.update_or_create(snapshot=execution.snapshot,
            condition_id=condition_id, defaults={**serializer.validated_data, 'updated_by': request.user})
        return Response({'condition_id': condition_id, **ActionStateSerializer(state).data,
                         'note': 'Workflow updated. Assessment scores are unchanged; reassess new evidence.'})
