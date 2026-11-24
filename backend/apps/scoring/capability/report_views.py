"""Authenticated, pinned, inference-free capability exports; no baseline approval gate."""
import json
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.scoring.models import RecommendationExecution
from .views import RunView
from .report_projection import held_note
from .recommendations import build_inputs
from .storage import digest
from .report_projection import build_report_view

logger = logging.getLogger(__name__)


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


STAGE_ONE = 'Stage 1 result: Document Review'
FINAL = 'Final AI-READY Score'


def assessment_stage(run, event):
    """Whether this report shows the Stage 1 result (the provisional run: what the documents show before follow-up
    questions and additional evidence) or the final AI-READY Score published after them (layer2_service.publish_final).
    A college sees its tier only on the final score (Siddharth, 23 Nov): before the follow-ups part of the credit is
    held on purpose, so a tier on it would understate the college."""
    second = (run.inputs or {}).get('second_layer')
    result = event.payload.get('result', {})
    score = result.get('score')
    if second:
        lowered = [row['condition_id'] for row in second.get('lowerings') or []]
        unchanged = not second.get('targets') and second.get('provisional_score') == score
        if unchanged:
            note = (f"{FINAL}: the follow-up stage is closed and no answer changed the Stage 1 result "
                    f"({second.get('provisional_score')}). Credit still held for depth stays held.")
        else:
            note = (f"{FINAL}: includes the follow-up answers and evidence the institution sent after the Stage 1 "
                    f"result ({second.get('provisional_score')} at Stage 1, {score} final).")
        if lowered:
            note += (f" {len(lowered)} requirement{'s' if len(lowered) != 1 else ''} went down because documents the "
                     'institution sent show otherwise.')
        return {'stage': 'final', 'label': FINAL, 'tier_shown': True, 'closed': True,
                'provisional_run_id': second['provisional_run_id'],
                'provisional_score': second.get('provisional_score'), 'score': score, 'lowered': lowered,
                'unchanged': unchanged, 'note': note}
    from .layer2_service import final_run_id
    final = final_run_id(str(run.pk))
    held = result.get('depth_reserve') or {}
    up_to = held.get('evidence_score') if held.get('held_points') else None
    if final:
        note = f'{STAGE_ONE}. The final AI-READY Score has been published (run {final}).'
    else:
        note = (f'{STAGE_ONE}: what the documents show before the follow-up questions.'
                + (f' Follow-up answers backed by documents can raise it to {up_to:g}.' if up_to else '')
                + ' The final AI-READY Score and tier are published once the follow-up questions are complete.')
    return {'stage': 'provisional', 'label': STAGE_ONE, 'tier_shown': False, 'closed': bool(final),
            'final_run_id': final, 'score': score,
            'up_to': up_to, 'note': note}


def html_to_pdf(html):
    """The PDF of a report page, made from the same HTML (WeasyPrint), or None where WeasyPrint or its system
    libraries are not installed (a Windows machine without GTK): the caller then uses the older PDF renderer."""
    try:
        from weasyprint import HTML
    except Exception:   # ImportError, or OSError when pango is missing
        return None
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None


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
        # summary and detailed: the reports designed for people (23 Nov, presentation.py); leadership and evidence:
        # the earlier reports, kept as InGage's technical appendix.
        if audience not in {'summary', 'detailed', 'leadership', 'evidence'}:
            raise serializers.ValidationError({'audience': 'Choose summary, detailed, leadership or evidence.'})
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
        from .explanations import attach, latest
        explanations = latest(run)   # beside the run, never in it: the integrity hashes above read event.payload
        stage = assessment_stage(run, event)
        pdf_key = pdf_cache_key(run, event, audience, stage, recommendation) if file_format == 'pdf' else None
        cached = cache_get(pdf_key)
        if cached is not None:
            return report_response(cached['content'], 'pdf', run, cached['audience'], cache='hit')
        payload = {'format_version': 'AIQIF-REPORT-0.2', 'exported_at': timezone.now(),
            'run_id': str(run.pk), 'assessment_event_id': event.pk, 'inputs_hash': run.inputs_hash,
            'profile': run.inputs['profile'], 'population': run.inputs['population'], 'rubric': run.inputs['rubric'],
            'reference_period': run.inputs['reference_period'], 'scope': run.inputs.get('scope'),
            'reviewed_evidence': run.inputs.get('reviewed_evidence'),
            'refines_run_id': run.inputs.get('refines_run_id'), 'source_manifest': run.inputs['manifest'],
            'assessment_protocol': run.inputs.get('assessment_protocol'),
            'retrieval_policy': run.inputs.get('retrieval_policy'),
            'assessment': attach(event.payload, explanations, closed=stage['closed']),
            'explanations_version': (explanations or {}).get('version'),
            'assessment_stage': stage, 'recommendation': recommendation,
            'deterministic_plan': snapshot.inputs if recommendation else build_inputs(run, event, {}),
            'notice': 'Experimental internal methodology, not an external accreditation standard. Unknown evidence is not failure. '
                      'Tier pathways are conditional sufficient scenarios, not optimal or guaranteed. Workflow completion does not change scores; reassessment is required.'}
        from .diagnostics import explain
        payload['diagnostics'] = explain(run.inputs, event.payload)
        # From the copy with the explanations attached (payload['assessment']), so the evidence report can print each
        # requirement's and key indicator's explanation; the stored event is unchanged.
        attached = payload['assessment']
        records = {r['condition_id']: r for r in attached['records']}
        indicators = [{**i, 'requirements': [{**c, 'decision': records[c['id']]} for c in i['conditions']]}
                      for i in attached['result']['indicators']]
        result_view = event.payload['result']
        if result_view.get('score') is not None:
            # A single-score (part-credit) run: each key indicator's part-credit score and each requirement's credit
            # label, as the PDF prints them, instead of the strict ranges and states; and the tier as a score band.
            from .action_plan import stars_text, tier_for, tiers
            from .report_projection import CREDIT_LABELS, credit_status
            scores = {i['code']: i['score'] for i in (result_view.get('documented') or {}).get('indicators') or []}
            for indicator in indicators:
                indicator['part_score'] = scores.get(indicator['code'])
                for requirement in indicator['requirements']:
                    decision = requirement['decision']
                    requirement['credit_label'] = (f"{CREDIT_LABELS[credit_status(decision)]} "
                                                   f"(credit {decision.get('credit') or 0:g})")
            band = tier_for(result_view['score'])
            payload['tier_band'] = {**band, 'stars_text': stars_text(band['stars']),
                                    'points_to_next': round(band['points_to_next'], 2),
                                    'bands': ', '.join(f'{name} {value:g}' for name, value in tiers())}
        plan_actions = payload['deterministic_plan']['actions']
        enriched = {a['condition_id']: a for a in (completed.payload['advice'] if completed else [])}
        actions = [{**a, 'advice': enriched.get(a['id'])} for a in plan_actions]
        payload['report_view'] = build_report_view(payload, actions)
        if audience in {'summary', 'detailed'}:
            from .presentation import build
            try:
                view = build(payload)
                payload['presentation'] = view
            except Exception:   # a run shaped in a way the new reports don't expect: serve the older report instead
                logger.exception('presentation failed for run %s; serving the older %s report', run.pk, audience)
                audience = 'leadership' if audience == 'summary' else 'evidence'
        if file_format == 'json':
            content = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        elif audience in {'summary', 'detailed'}:
            template = 'scoring/report_leadership.html' if audience == 'summary' else 'scoring/report_detailed.html'
            content = render_to_string(template, {'v': view, 'exported': payload['exported_at']})
            if file_format == 'pdf':
                pdf = html_to_pdf(content)
                if pdf is None and audience == 'summary':
                    from .leadership_pdf import render_leadership_pdf
                    pdf = render_leadership_pdf(payload['report_view'])
                elif pdf is None:
                    from .pdf_report import render_pdf
                    pdf = render_pdf(payload, indicators, actions)
                content = pdf
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
                    'result': event.payload['result'], 'indicators': indicators, 'actions': actions,
                    'held_note': held_note(event.payload['result'].get('depth_reserve'), closed=stage['closed'])})
        if pdf_key:
            cache_set(pdf_key, {'content': content, 'audience': audience})
        return report_response(content, file_format, run, audience, cache='miss' if pdf_key else None)


def report_response(content, file_format, run, audience, cache=None):
    response = HttpResponse(content, content_type={'json': 'application/json; charset=utf-8',
        'html': 'text/html; charset=utf-8', 'pdf': 'application/pdf'}[file_format])
    response['Content-Disposition'] = f'attachment; filename="capability-{run.pk}-{audience}.{file_format}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    if cache:
        response['X-Report-Cache'] = cache
    return response


# --- the rendered PDFs, kept per run and version (issue 60 follow-up) ----------------------------------------------
# A report PDF took 9-11 s on live (WeasyPrint). It is kept on the server, under a key naming everything it is made
# from that can change: the completed event, the newest stored explanations, the follow-up stage (closed, final run),
# the chosen advice and its workflow states, and the deployed code (run_view.code_fingerprint). A change to any of them
# makes a new PDF. The integrity check above still runs on every request. A kept PDF shows the time it was first made.
PDF_CACHE_SECONDS = 7 * 24 * 3600


def pdf_cache_key(run, event, audience, stage, recommendation):
    from .run_view import _explanation_id, code_fingerprint
    return 'capability-report-pdf:' + digest([str(run.pk), event.pk, audience, str(_explanation_id(run.pk, event.pk)),
                                              stage, recommendation, code_fingerprint()])


def cache_get(key):
    if not key:
        return None
    from django.core.cache import cache
    try:
        return cache.get(key)
    except Exception:   # the cache server is down: render as before
        logger.warning('report cache unavailable', exc_info=True)
        return None


def cache_set(key, value):
    from django.core.cache import cache
    try:
        cache.set(key, value, PDF_CACHE_SECONDS)
    except Exception:
        logger.warning('report cache unavailable', exc_info=True)
