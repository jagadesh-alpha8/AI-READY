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
from .storage import digest
from .report_projection import build_report_view


class ReportUnavailable(APIException):
    status_code = 409
    default_detail = 'Select a completed assessment to export a capability report.'


class ReportIntegrityError(APIException):
    status_code = 409
    default_detail = 'The saved assessment and advice do not match. Select a matching saved version.'


def validate_report_identity(run, event, snapshot=None, completed=None):
    if digest(run.inputs) != run.inputs_hash or event.payload.get('inputs_hash') != run.inputs_hash:
        raise ReportIntegrityError()
    if snapshot is not None:
        plan = snapshot.inputs
        if (snapshot.run_id != run.pk or snapshot.assessment_event_id != event.pk or digest(plan) != snapshot.inputs_hash
                or plan.get('run_inputs_hash') != run.inputs_hash
                or plan.get('assessment_event_id') != event.pk
                or plan.get('assessment_hash') != digest(event.payload)):
            raise ReportIntegrityError()
        if completed is not None and completed.payload.get('inputs_hash') != snapshot.inputs_hash:
            raise ReportIntegrityError()


def assessment_stage(run, event):
    """Whether this report shows the provisional result (before follow-up questions and additional evidence) or the
    final one published after them (layer2_service.publish_final)."""
    second = (run.inputs or {}).get('second_layer')
    score = event.payload.get('result', {}).get('score')
    if second:
        return {'stage': 'final', 'provisional_run_id': second['provisional_run_id'],
                'provisional_score': second.get('provisional_score'), 'score': score,
                'note': (f"Final result: includes the evidence the institution sent after the provisional score "
                         f"({second.get('provisional_score')} provisional, {score} final).")}
    from .layer2_service import final_run_id
    final = final_run_id(str(run.pk))
    return {'stage': 'provisional', 'final_run_id': final, 'score': score,
            'note': ('Provisional result: a final result that includes later evidence has been published (run '
                     f'{final}).') if final else
                    'Provisional result: follow-up questions and any additional evidence may still change it.'}


class CapabilityReportView(RunView):
    def get(self, request, sprint_id, run_id):
        execution = self.authorized(request, sprint_id, run_id)
        run = execution.run
        event = run.events.filter(state='completed', payload__result__isnull=False).last()
        if event is None:
            raise ReportUnavailable()
        file_format = request.query_params.get('file', 'html')
        if file_format not in {'html', 'json', 'pdf'}:
            raise serializers.ValidationError({'file': 'Choose html, json or pdf.'})
        audience = request.query_params.get('audience', 'leadership')
        if audience not in {'leadership', 'evidence'}:
            raise serializers.ValidationError({'audience': 'Choose leadership or evidence.'})
        advice_id = request.query_params.get('recommendation_id')
        recommendation = None
        snapshot = completed = None
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
        validate_report_identity(run, event, snapshot, completed)
        payload = {'format_version': 'AIQIF-REPORT-0.2', 'exported_at': timezone.now(),
            'run_id': str(run.pk), 'assessment_event_id': event.pk, 'inputs_hash': run.inputs_hash,
            'profile': run.inputs['profile'], 'population': run.inputs['population'], 'rubric': run.inputs['rubric'],
            'reference_period': run.inputs['reference_period'], 'scope': run.inputs.get('scope'),
            'reviewed_evidence': run.inputs.get('reviewed_evidence'),
            'refines_run_id': run.inputs.get('refines_run_id'), 'source_manifest': run.inputs['manifest'],
            'assessment_protocol': run.inputs.get('assessment_protocol'),
            'retrieval_policy': run.inputs.get('retrieval_policy'),
            'assessment': event.payload, 'assessment_stage': assessment_stage(run, event), 'recommendation': recommendation,
            'deterministic_plan': snapshot.inputs if recommendation else build_inputs(run, event, {}),
            'notice': 'Experimental internal methodology, not an external accreditation standard. Unknown evidence is not failure. '
                      'Tier pathways are conditional sufficient scenarios, not optimal or guaranteed. Workflow completion does not change scores; reassessment is required.'}
        from .diagnostics import explain
        payload['diagnostics'] = explain(run.inputs, event.payload)
        records = {r['condition_id']: r for r in event.payload['records']}
        indicators = [{**i, 'requirements': [{**c, 'decision': records[c['id']]} for c in i['conditions']]}
                      for i in event.payload['result']['indicators']]
        plan_actions = payload['deterministic_plan']['actions']
        enriched = {a['condition_id']: a for a in (completed.payload['advice'] if completed else [])}
        actions = [{**a, 'advice': enriched.get(a['id'])} for a in plan_actions]
        payload['report_view'] = build_report_view(payload, actions)
        if file_format == 'json':
            content = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        else:
            # Django autoescape handles all institution/source/model text; no raw HTML is marked safe.
            if file_format == 'pdf':
                if audience == 'leadership':
                    from .leadership_pdf import render_leadership_pdf
                    content = render_leadership_pdf(payload['report_view'])
                else:
                    from .pdf_report import render_pdf
                    content = render_pdf(payload, indicators, actions)
            else:
                template = 'scoring/leadership_report.html' if audience == 'leadership' else 'scoring/capability_report.html'
                content = render_to_string(template, {'report': payload, 'view': payload['report_view'],
                    'result': event.payload['result'], 'indicators': indicators, 'actions': actions})
        response = HttpResponse(content, content_type={'json': 'application/json; charset=utf-8',
            'html': 'text/html; charset=utf-8', 'pdf': 'application/pdf'}[file_format])
        response['Content-Disposition'] = f'attachment; filename="capability-{run.pk}-{audience}.{file_format}"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        return response
