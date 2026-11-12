"""Tenant-scoped explicit plan requests and inference-free reads/exports."""
import json
from copy import deepcopy
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework import serializers
from rest_framework.response import Response
from config.pagination import DefaultPageNumberPagination
from apps.scoring.models import PlanScenarioExecution
from .views import RunView
from .plan_execution import enabled, start, finish, summary, validate_identity
from .storage import digest
from .execution import AssessmentConflict


class PlanSerializer(serializers.Serializer):
    plan_text = serializers.CharField(max_length=30000, trim_whitespace=False)

    def validate_plan_text(self, value):
        if not value.strip():
            raise serializers.ValidationError('Enter the institution’s proposed plan.')
        return value


class PlanEvaluationsView(RunView):
    def get(self, request, sprint_id, run_id):
        run = self.authorized(request, sprint_id, run_id).run
        rows = PlanScenarioExecution.objects.filter(run=run).order_by('-created_at', '-scenario_id')
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([summary(row) for row in page])
        response.data['enabled'] = enabled()
        return response

    def post(self, request, sprint_id, run_id):
        run = self.authorized(request, sprint_id, run_id).run
        serializer = PlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 100 or not all(c.isalnum() or c in '-_.' for c in key):
            raise serializers.ValidationError({'Idempotency-Key': 'Supply a unique key of 1–100 letters, digits, dots, dashes or underscores.'})
        execution, created = start(run=run, user=request.user, key=key, **serializer.validated_data)
        execution.refresh_from_db()
        return Response({**summary(execution), 'reused': not created}, status=202 if created else 200)


class PlanEvaluationView(RunView):
    def plan_execution(self, request, sprint_id, run_id, scenario_id):
        run = self.authorized(request, sprint_id, run_id).run
        return get_object_or_404(PlanScenarioExecution.objects.select_related(
            'scenario__run', 'scenario__assessment_event', 'scenario__plan'), run=run, scenario_id=scenario_id)

    def payload(self, execution):
        scenario = execution.scenario
        completed = scenario.events.filter(payload__kind='completed').last()
        validate_identity(scenario, completed)
        terminal = scenario.events.filter(payload__kind='terminal').last()
        original_event = scenario.events.filter(payload__kind='stage', payload__stage='original_evaluation').last()
        original_review = completed.payload['comparison']['original'] if completed else None
        if original_review is None and original_event:
            value = original_event.payload['value']
            if (original_event.payload.get('value_hash') != digest(value)
                    or value.get('text') != scenario.plan.text
                    or value.get('text_hash') != scenario.plan.text_hash
                    or not baseline_matches(value.get('evaluation', {}), scenario)):
                raise AssessmentConflict('The saved original plan review failed its identity check.')
            original_review = value
        return {**summary(execution), 'inputs_hash': scenario.inputs_hash,
            'baseline_run_id': str(scenario.run_id), 'baseline_inputs_hash': scenario.run.inputs_hash,
            'assessment_event_id': scenario.assessment_event_id,
            'scope': scenario.inputs['scope'], 'population': scenario.inputs['population'],
            'reference_period': scenario.inputs['reference_period'], 'profile': scenario.inputs['profile'],
            'plan_id': str(scenario.plan_id), 'original_text': scenario.plan.text,
            'completed_stages': list(scenario.events.filter(payload__kind='stage').values_list('payload__stage', flat=True)),
            'comparison': completed.payload['comparison'] if completed else None,
            'original_review': original_review,
            'improved_plan_id': completed.payload['improved_plan_id'] if completed else None,
            'inference': completed.payload['inference'] if completed else None,
            'error': terminal.payload if terminal else None,
            'actual_assessment_changed': False}

    def get(self, request, sprint_id, run_id, scenario_id):
        return Response(self.payload(self.plan_execution(request, sprint_id, run_id, scenario_id)))


def baseline_matches(evaluation, scenario):
    """A saved review belongs to this baseline: its strict result is the stored result's strict part, and its score is
    the scenario's frozen part-credit score (None for runs scored before part credit)."""
    stored = scenario.assessment_event.payload['result']
    baseline = evaluation.get('baseline')
    return (isinstance(baseline, dict) and all(stored.get(k) == v for k, v in baseline.items())
            and evaluation.get('baseline_score') == scenario.inputs.get('baseline_score'))


class CancelPlanEvaluationView(PlanEvaluationView):
    def post(self, request, sprint_id, run_id, scenario_id):
        execution = self.plan_execution(request, sprint_id, run_id, scenario_id)
        changed = finish(scenario_id, 'cancelled', 'cancelled_by_user')
        execution.refresh_from_db()
        return Response({**summary(execution), 'changed': changed,
            'note': 'An in-flight request may still be billed. No actual assessment is changed.'})


class PlanEvaluationReportView(PlanEvaluationView):
    def get(self, request, sprint_id, run_id, scenario_id):
        payload = self.payload(self.plan_execution(request, sprint_id, run_id, scenario_id))
        fmt = request.query_params.get('file', 'html')
        if fmt not in {'html', 'json'}:
            raise serializers.ValidationError({'file': 'Choose html or json.'})
        if fmt == 'json':
            content = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        else:
            from .report_projection import PILLARS, readable
            presentation = deepcopy(payload)
            reviews = ([presentation['comparison'][version] for version in ('original', 'improved')]
                       if presentation['comparison'] else ([presentation['original_review']] if presentation['original_review'] else []))
            for review in reviews:
                evaluation = review['evaluation']
                for scenario in evaluation['scenarios'].values():
                    for pillar in scenario['result']['pillars']:
                        pillar['title'] = PILLARS.get(pillar['code'], pillar['code'])
                    for pillar in (scenario.get('score') or {}).get('pillars', []):
                        pillar['title'] = PILLARS.get(pillar['code'], pillar['code'])
                for mapping in evaluation['accepted']:
                    mapping['title'] = readable(mapping['condition_id'])
                coverage = evaluation.get('priority_coverage')
                if coverage:
                    for key in ('covered', 'missed', 'outside_priority_plan'):
                        coverage[key + '_titles'] = [readable(cid) for cid in coverage[key]]
            content = render_to_string('scoring/plan_comparison.html', {'report': presentation})
        response = HttpResponse(content, content_type='application/json' if fmt == 'json' else 'text/html; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="plan-comparison-{scenario_id}.{fmt}"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        return response
