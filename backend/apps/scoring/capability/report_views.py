"""Authenticated, pinned, inference-free capability exports; no baseline approval gate."""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.scoring.models import RecommendationExecution
from .views import RunView
from .recommendations import build_inputs


class ReportUnavailable(APIException):
    status_code = 409
    default_detail = 'Select a completed assessment to export a capability report.'


class CapabilityReportView(RunView):
    def get(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        run = execution.run
        event = run.events.filter(state='completed', payload__result__isnull=False).last()
        if event is None:
            raise ReportUnavailable()
        file_format = request.query_params.get('file', 'html')
        if file_format not in {'html', 'json'}:
            raise serializers.ValidationError({'file': 'Choose html or json.'})
        advice_id = request.query_params.get('recommendation_id')
        recommendation = None
        if advice_id:
            advice_id = serializers.UUIDField().run_validation(advice_id)
            ledger = get_object_or_404(RecommendationExecution.objects.select_related('snapshot'),
                                      run=run, snapshot_id=advice_id)
            snapshot = ledger.snapshot
            completed = snapshot.events.filter(payload__kind='completed').last()
            recommendation = {'id': str(snapshot.pk), 'status': ledger.status, 'inputs_hash': snapshot.inputs_hash,
                'plan': snapshot.inputs, 'tailoring': completed.payload if completed else None,
                'workflow_at_export': list(snapshot.action_states.order_by('condition_id').values(
                    'condition_id', 'owner', 'feasibility', 'status'))}
        payload = {'format_version': 'AIQIF-REPORT-0.1', 'exported_at': timezone.now(),
            'run_id': str(run.pk), 'assessment_event_id': event.pk, 'inputs_hash': run.inputs_hash,
            'profile': run.inputs['profile'], 'population': run.inputs['population'], 'rubric': run.inputs['rubric'],
            'reference_period': run.inputs['reference_period'], 'source_manifest': run.inputs['manifest'],
            'assessment': event.payload, 'recommendation': recommendation,
            'deterministic_plan': snapshot.inputs if recommendation else build_inputs(run, event, {}),
            'notice': 'Experimental internal methodology, not an external accreditation standard. Unknown evidence is not failure. '
                      'Tier pathways are conditional sufficient scenarios, not optimal or guaranteed. Workflow completion does not change scores; reassessment is required.'}
        if file_format == 'json':
            content = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        else:
            records = {r['condition_id']: r for r in event.payload['records']}
            indicators = [{**i, 'requirements': [{**c, 'decision': records[c['id']]} for c in i['conditions']]}
                          for i in event.payload['result']['indicators']]
            plan_actions = payload['deterministic_plan']['actions']
            enriched = {a['condition_id']: a for a in (completed.payload['advice'] if recommendation and completed else [])}
            actions = [{**a, 'advice': enriched.get(a['id'])} for a in plan_actions]
            # Django autoescape handles all institution/source/model text; no raw HTML is marked safe.
            content = render_to_string('scoring/capability_report.html', {'report': payload,
                'result': event.payload['result'], 'indicators': indicators, 'actions': actions})
        response = HttpResponse(content, content_type='application/json; charset=utf-8' if file_format == 'json' else 'text/html; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="capability-{run.pk}.{file_format}"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        return response
