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
from .plan_execution import enabled, start, finish, summary, usage, validate_identity
from .plan_mapping import MAX_ACTIONS, MAX_PLAN_CHARS, VERSION
from .storage import digest
from .execution import AssessmentConflict


class PlanSerializer(serializers.Serializer):
    plan_text = serializers.CharField(trim_whitespace=False)

    def validate_plan_text(self, value):
        if not value.strip():
            raise serializers.ValidationError('Paste your plan first.')
        if len(value) > MAX_PLAN_CHARS:
            raise serializers.ValidationError(
                f'This plan is {len(value):,} characters long; a check takes up to {MAX_PLAN_CHARS:,} (about 12 '
                'pages). Leave out annexes, budgets tables and background sections, and keep the actions.')
        return value


def limits(sprint_id):
    """What the page shows about the limits: checks used and left in this assessment, and the size of a plan."""
    return {**usage(sprint_id), 'max_chars': MAX_PLAN_CHARS, 'max_actions': MAX_ACTIONS}


class PlanEvaluationsView(RunView):
    def get(self, request, sprint_id, run_id):
        run = self.authorized(request, sprint_id, run_id).run
        rows = PlanScenarioExecution.objects.filter(run=run).order_by('-created_at', '-scenario_id')
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([summary(row) for row in page])
        response.data['enabled'] = enabled()
        response.data['limits'] = limits(run.sprint_id)
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
        return Response({**summary(execution), 'reused': not created, 'limits': limits(run.sprint_id)},
                        status=202 if created else 200)


class PlanEvaluationView(RunView):
    def plan_execution(self, request, sprint_id, run_id, scenario_id):
        run = self.authorized(request, sprint_id, run_id).run
        return get_object_or_404(PlanScenarioExecution.objects.select_related(
            'scenario__run', 'scenario__assessment_event', 'scenario__plan'), run=run, scenario_id=scenario_id)

    def payload(self, execution, staff=True):
        scenario = execution.scenario
        completed = scenario.events.filter(payload__kind='completed').last()
        validate_identity(scenario, completed)
        terminal = scenario.events.filter(payload__kind='terminal').last()
        legacy = scenario.inputs.get('version') != VERSION
        base = {**summary(execution), 'inputs_hash': scenario.inputs_hash, 'version': scenario.inputs.get('version'),
                'legacy': legacy, 'baseline_run_id': str(scenario.run_id), 'baseline_inputs_hash': scenario.run.inputs_hash,
                'assessment_event_id': scenario.assessment_event_id, 'plan_id': str(scenario.plan_id),
                'original_text': scenario.plan.text,
                'completed_stages': list(scenario.events.filter(payload__kind='stage').values_list('payload__stage', flat=True)),
                'improved_plan_id': completed.payload['improved_plan_id'] if completed else None,
                'error': terminal.payload if terminal else None, 'actual_assessment_changed': False}
        if legacy:
            return {**base, **self.legacy_payload(scenario, completed)}
        review = completed.payload['comparison'] if completed else None
        original_review = None
        if review is None:
            saved = scenario.events.filter(payload__kind='stage', payload__stage='original_review').last()
            if saved:
                if saved.payload.get('value_hash') != digest(saved.payload['value']):
                    raise AssessmentConflict('The saved plan review failed its identity check.')
                original_review = saved.payload['value']
        if review is not None and not staff:
            review = {k: v for k, v in review.items() if k != 'traces'}
            review['recommendation'] = {k: v for k, v in review['recommendation'].items() if k != 'internal_notes'}
        return {**base, 'review': review, 'original_review': original_review,
                'page': page_of(execution, review) if review is not None else None,
                'inference': completed.payload['inference'] if completed and staff else None}

    def legacy_payload(self, scenario, completed):
        """A check made before institution-plan-review-1.0: shown as it was saved (JSON only)."""
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
        return {'scope': scenario.inputs['scope'], 'population': scenario.inputs['population'],
                'reference_period': scenario.inputs['reference_period'], 'profile': scenario.inputs['profile'],
                'comparison': completed.payload['comparison'] if completed else None, 'review': None,
                'original_review': original_review, 'inference': completed.payload['inference'] if completed else None}

    def get(self, request, sprint_id, run_id, scenario_id):
        from .publication import is_staff
        return Response(self.payload(self.plan_execution(request, sprint_id, run_id, scenario_id),
                                     staff=is_staff(request.user)))


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
    """Downloads: ?file=pdf (the plan check), docx (the recommended plan, editable), json (InGage staff only), or
    html (the same page as the PDF). A check made before institution-plan-review-1.0 has its old HTML page only."""
    def get(self, request, sprint_id, run_id, scenario_id):
        from .publication import is_staff
        execution = self.plan_execution(request, sprint_id, run_id, scenario_id)
        staff = is_staff(request.user)
        payload = self.payload(execution, staff=staff)
        fmt = request.query_params.get('file', 'pdf' if not payload['legacy'] else 'html')
        if fmt not in {'html', 'json', 'pdf', 'docx'}:
            raise serializers.ValidationError({'file': 'Choose pdf, docx, html or json.'})
        if fmt == 'json' and not staff:
            raise serializers.ValidationError({'file': 'The JSON export is for InGage staff. Download the PDF or the Word file.'})
        if fmt == 'json':
            return self.respond(json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2),
                                'application/json', f'plan-check-{scenario_id}.json')
        if payload['legacy']:
            if fmt != 'html':
                raise serializers.ValidationError({'file': 'This check was made with an earlier version: its HTML page '
                                                           'is all there is. Check the plan again for a PDF.'})
            return self.respond(legacy_html(payload), 'text/html; charset=utf-8', f'plan-comparison-{scenario_id}.html')
        if payload['review'] is None:
            raise serializers.ValidationError({'file': 'This check has not finished, so there is nothing to download yet.'})
        from . import plan_report
        view = plan_report.masked(payload['page'])
        name = plan_report.filename(view['institution'], 'check')
        if fmt == 'docx':
            return self.respond(plan_report.docx(view),
                                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                plan_report.filename(view['institution'], 'recommended') + '.docx')
        page = plan_report.html(view)
        if fmt == 'pdf':
            content = plan_report.pdf(view)
            if content is None:   # no WeasyPrint on this machine: the same page as HTML
                return self.respond(page, 'text/html; charset=utf-8', name + '.html')
            return self.respond(content, 'application/pdf', name + '.pdf')
        return self.respond(page, 'text/html; charset=utf-8', name + '.html')

    def respond(self, content, content_type, filename):
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        from apps.demo_mask import mask
        if mask.active():
            response['X-Name-Mask'] = 'applied'
        return response


def page_of(execution, review):
    """The check as the college reads it (plan_report.build): the same content on the screen, in the PDF and in
    the Word file. API responses are masked by the demo-mask middleware; downloads mask it themselves."""
    from . import plan_report
    inputs = execution.scenario.run.inputs or {}
    institution = ((inputs.get('scope') or {}).get('institution') or {}).get('assessed_name') or \
        (inputs.get('profile') or {}).get('name') or 'Your college'
    return plan_report.build(review, institution=institution,
                             result_kind='final result' if inputs.get('second_layer') else 'Stage 1 result',
                             checked_on=f'{execution.created_at.day} {execution.created_at:%B %Y}')


def legacy_html(payload):
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
    return render_to_string('scoring/plan_comparison.html', {'report': presentation})
