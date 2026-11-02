"""Inference-free presentation of a frozen assessment, never a new scoring method.

This module does not read live facts, infer missing activity or change advice. It
groups existing follow-ups for readers; strategic initiative planning is separate.
"""
from collections import Counter
import re


PILLARS = {
    'AIQIF-C1': 'Leadership and investment',
    'AIQIF-C2': 'Responsible and safe AI',
    'AIQIF-C3': 'Curriculum and teaching',
    'AIQIF-C4': 'Faculty and staff',
    'AIQIF-C5': 'Student skills and careers',
    'AIQIF-C6': 'Technology and data',
    'AIQIF-C7': 'Research and innovation',
    'AIQIF-C8': 'Services and partnerships',
    'AIQIF-C9': 'Measurement and improvement',
}
AREA_TITLES = {
    'AIQIF-C1.1': 'AI strategy and priorities', 'AIQIF-C1.2': 'Decision-making and accountability',
    'AIQIF-C1.3': 'Funding and resource planning', 'AIQIF-C1.4': 'Adoption and staff support',
    'AIQIF-C2.1': 'Responsible-use guidance', 'AIQIF-C2.2': 'Privacy and risk management',
    'AIQIF-C2.3': 'Oversight of AI systems and data', 'AIQIF-C2.4': 'Human review and appeals',
    'AIQIF-C3.1': 'AI learning within programmes', 'AIQIF-C3.2': 'AI literacy across disciplines',
    'AIQIF-C3.3': 'AI in teaching and assessment', 'AIQIF-C3.4': 'Applied AI learning',
    'AIQIF-C4.1': 'Faculty AI literacy', 'AIQIF-C4.2': 'Role-specific faculty skills',
    'AIQIF-C4.3': 'AI in academic work', 'AIQIF-C4.4': 'Staff development and support',
    'AIQIF-C5.1': 'Student AI literacy and access', 'AIQIF-C5.2': 'Advanced student skills',
    'AIQIF-C5.3': 'Student projects and portfolios', 'AIQIF-C5.4': 'Internships and career progression',
    'AIQIF-C6.1': 'Computing access and AI suitability', 'AIQIF-C6.2': 'Usable institutional data',
    'AIQIF-C6.3': 'Security and recovery', 'AIQIF-C6.4': 'Accessible AI learning environments',
    'AIQIF-C7.1': 'AI research and applied inquiry', 'AIQIF-C7.2': 'Innovation and mentoring support',
    'AIQIF-C7.3': 'Funding, intellectual property and enterprise', 'AIQIF-C7.4': 'Research collaboration and public benefit',
    'AIQIF-C8.1': 'Digital services and AI operations', 'AIQIF-C8.2': 'Industry collaboration',
    'AIQIF-C8.3': 'Employment and enterprise pathways', 'AIQIF-C8.4': 'Measuring educational and business benefits',
    'AIQIF-C9.1': 'Institutional measurement and review', 'AIQIF-C9.2': 'Traceable institutional evidence',
    'AIQIF-C9.3': 'Keeping assessments up to date', 'AIQIF-C9.4': 'Testing, feedback and improvement',
}
STAGES = {'F': 'Starting capability', 'A': 'Repeated use', 'O': 'Results and review'}
STATE_LABELS = {'met': 'Demonstrated', 'not_met': 'Documented shortfall',
                'unknown': 'Not established', 'conflicting': 'Contradictory evidence'}
CODE = re.compile(r'AIQIF-C\d+\.\d+(?:\.[FAO]\d+)?')


def readable(value):
    """Translate generated references, never modify original source quotations."""
    def label(match):
        code = match.group()
        parts = code.split('.')
        title = AREA_TITLES.get('.'.join(parts[:2]), 'the relevant assessment area')
        return title + (f" ({STAGES.get(parts[2][0], 'requirement').lower()})" if len(parts) > 2 else '')
    return CODE.sub(label, str(value or ''))


def score_label(lower, upper):
    if lower == upper:
        return f'{lower:g} / 100'
    return 'Not established'


def bounds_note(lower, upper):
    if lower == upper:
        return 'Single value under the recorded capability method.'
    if lower == 0 and upper == 100:
        return 'The unresolved evidence does not support a useful numerical estimate.'
    return f'The recorded method permits {lower:g} to {upper:g} / 100; this is a range, not an estimated score.'


def finding(counts):
    if counts['conflicting']:
        return 'Some evidence is contradictory and needs reconciliation.'
    if counts['not_met']:
        return 'At least one requirement has a documented shortfall.'
    if counts['unknown']:
        return ('Some requirements are demonstrated; others remain unresolved.' if counts['met'] else
                'The evidence assessed does not establish this capability.')
    return 'The requirements are demonstrated under the recorded method.'


def advisory_state(recommendation):
    if recommendation is None:
        return {'kind': 'basic', 'status': 'not_requested', 'label': 'Basic assessment report',
                'explanation': 'No tailored recommendation version was selected. Follow-ups come from the stored assessment requirements.'}
    status = recommendation['status']
    tailoring = recommendation.get('tailoring')
    if (status == 'completed' and tailoring and tailoring.get('mode') == 'tailored'
            and any(a.get('origin') != 'deterministic_evidence_request' for a in tailoring.get('advice', []))):
        return {'kind': 'tailored', 'status': status, 'label': 'Assessment with tailored advice',
                'explanation': 'Advice is linked to the selected saved assessment. Some unresolved requirements may still use basic evidence guidance.'}
    explanations = {
        'queued': 'Tailored advice is queued. This export contains basic assessment follow-ups.',
        'running': 'Tailored advice is still being generated. This export contains basic assessment follow-ups.',
        'failed': 'Tailored advice could not be completed. This export retains the assessment and basic follow-ups.',
        'cancelled': 'Tailored advice was cancelled. This export retains the assessment and basic follow-ups.',
    }
    return {'kind': 'basic', 'status': status, 'label': 'Basic assessment report',
            'explanation': explanations.get(status, 'The selected version contains basic guidance; bespoke institutional advice is not established.')}


def build_report_view(report, actions):
    result = report['assessment']['result']
    decisions = {r['condition_id']: r for r in report['assessment']['records']}
    action_by_id = {a['id']: a for a in actions}
    state = advisory_state(report.get('recommendation'))
    source_labels = {str(p['page_id']): f"{d['filename']}, page {p.get('number', '?')}"
                     for d in report['source_manifest'] for p in d.get('pages', [])}
    areas, followups = [], []
    for order, indicator in enumerate(result['indicators']):
        rows = [decisions[c['id']] for c in indicator['conditions']]
        counts = Counter(row['state'] for row in rows)
        stage_results = []
        for stage, title in STAGES.items():
            states = [decisions[c['id']]['state'] for c in indicator['conditions'] if c['level'] == stage]
            status = ('conflicting' if 'conflicting' in states else 'not_met' if 'not_met' in states
                      else 'unknown' if 'unknown' in states else 'met')
            stage_results.append({'title': title, 'status': STATE_LABELS[status]})
        available = [action_by_id[c['id']] for c in indicator['conditions'] if c['id'] in action_by_id]
        # Earlier steps precede advanced outcomes. Weight/code-order score optimisation
        # is deliberately not used as an institutional strategy.
        available.sort(key=lambda a: ('FAO'.index(a['id'].rsplit('.', 1)[-1][0]),
                                      {'conflicting': 0, 'not_met': 1, 'unknown': 2}.get(a['state'], 3)))
        first = available[0] if available else None
        title = AREA_TITLES.get(indicator['code'], readable(indicator['name']))
        area = {'key': indicator['code'], 'pillar_key': indicator['pillar'], 'title': title,
                'score': score_label(indicator['lower'], indicator['upper']),
                'score_explanation': bounds_note(indicator['lower'], indicator['upper']),
                'finding': finding(counts), 'stages': stage_results,
                'next_step': 'Maintain the demonstrated capability and retain supporting evidence.'}
        if first:
            advice = first.get('advice')
            prefixes = {'unknown': 'Check whether existing records establish: ',
                        'conflicting': 'Reconcile the evidence for: ',
                        'not_met': 'Address the documented requirement: '}
            initial = prefixes.get(first['state'], '') + readable(first['requirement'])
            area['next_step'] = initial
            followups.append({
                'title': title, 'area_key': indicator['code'], 'condition_id': first['id'],
                'linked_requirement_ids': [a['id'] for a in available],
                'reason': area['finding'], 'next_step': initial,
                'steps': [readable(s) for s in advice['steps']] if advice else [initial],
                'suggested_role': readable(advice['suggested_role']) if advice else 'Relevant institutional lead (suggested)',
                'effort': {'small': 'Small', 'medium': 'Medium', 'large': 'Large', 'unknown': 'Not estimated'}.get(
                    advice.get('effort') if advice else 'unknown', 'Not estimated'),
                'completion': readable(advice['completion_evidence'] if advice else first['completion_evidence']),
                'dependencies': list(dict.fromkeys(readable(d) for d in advice.get('dependencies', []))) if advice else [],
                'sources': [{'label': source_labels.get(str(c['source_id']), 'Saved source reference'),
                             'quote': c['quote']} for c in (advice.get('basis', []) if advice else first.get('citations', []))],
                'guidance': ('Tailored suggestion' if state['kind'] == 'tailored' and advice and
                             advice.get('origin') != 'deterministic_evidence_request' else 'Basic assessment follow-up'),
                '_sort': ('FAO'.index(first['id'].rsplit('.', 1)[-1][0]),
                          {'conflicting': 0, 'not_met': 1, 'unknown': 2}.get(first['state'], 3), order),
            })
        areas.append(area)
    followups.sort(key=lambda a: a['_sort'])
    for row in followups:
        row.pop('_sort')
    pillars = []
    for pillar in result['pillars']:
        children = [a for a in areas if a['pillar_key'] == pillar['code']]
        followup = next((a for a in followups if any(c['key'] == a['area_key'] for c in children)), None)
        pillars.append({'title': PILLARS.get(pillar['code'], 'Assessment area'),
                        'score': score_label(pillar['lower'], pillar['upper']),
                        'score_explanation': bounds_note(pillar['lower'], pillar['upper']),
                        'areas': children, 'next_step': followup['next_step'] if followup else
                        'Maintain demonstrated capability and review new evidence.'})
    counts = Counter(row['state'] for row in decisions.values())
    diagnostics = report['diagnostics']
    scope = report.get('scope') or {}
    scope_notices = [{k: question[k] for k in ('code', 'severity', 'message')}
                     for question in scope.get('questions', [])]
    if scope.get('mode') == 'default':
        scope_notices.insert(0, {'code': 'default_source_specific_scope', 'severity': 'limitation',
            'message': 'This is an institutional overview using source-specific populations and periods. Universal coverage and current-year activity are not presumed.'})
    if report.get('refines_run_id'):
        scope_notices.append({'code': 'scope_refinement', 'severity': 'limitation',
            'message': 'This is a refined assessment scope. A result change from an earlier scope does not by itself show institutional improvement.'})
    needs_scope_review = any(q['severity'] == 'review' for q in scope_notices)
    return {
        'version': 'readable-assessment-0.2', 'institution': scope.get('institution', {}).get('assessed_name') or report['profile']['name'],
        'population': report['population'], 'period': report['reference_period'],
        'scope_notices': scope_notices,
        'methodology': result['methodology'], 'methodology_status': result['methodology_status'],
        'methodology_notice': ('This report uses independent assertion credit under the experimental readiness method. Source-period findings do not prove current operation. Achievement levels are not calibrated.' if result.get('aggregation') == 'independent_conditions' else 'This report uses its recorded historical capability method. Start a new assessment to use the revised readiness method. Experimental results do not constitute accreditation.'),
        'score': score_label(result['lower'], result['upper']),
        'score_explanation': bounds_note(result['lower'], result['upper']),
        'assessment_state': 'Provisional findings' if counts['unknown'] or counts['conflicting'] or needs_scope_review else 'Assessment completed',
        'advisory': state, 'pillars': pillars, 'areas': areas, 'priorities': followups[:5],
        'followup_count': len(followups),
        'priority_note': 'These starting points use the earliest unresolved capability steps, with contradictions first within each step. Institutional benefit, cost and feasibility have not been assessed. All areas remain available in the detail.',
        'evidence_summary': (f"{diagnostics['source_documents']} source "
                             f"{'document' if diagnostics['source_documents'] == 1 else 'documents'} and "
                             f"{diagnostics['readable_pages']} readable "
                             f"{'page' if diagnostics['readable_pages'] == 1 else 'pages'} were included in this saved assessment."),
        'limitations': [
            'Missing or unreadable records do not establish that an activity is absent.',
            'Findings apply only to the recorded population and period; historical evidence does not establish current performance.',
            'Human review decisions influence these findings only if included in the saved assessment inputs. This export does not rerun that integration.',
            'Completing a suggested task does not change the score. New supporting evidence must be assessed in a new version.',
            'These explanations summarise saved decisions and do not independently verify their factual accuracy.',
        ] + [q['message'] for q in scope_notices] + ([scope['limitations']] if scope.get('limitations') else []) + (['Some source pages were unreadable or unavailable. Check the supporting evidence inventory.']
             if diagnostics['unreadable_or_unavailable_pages'] else []) +
            (['Some requirement decisions could not be validated and remain unresolved. See the supporting evidence.']
             if diagnostics['validation_issues'] else []) +
            ([f"{diagnostics['indicators_with_bounded_context']} assessment areas used selected subsets of source passages. This is not a complete page-by-page review; missing support in a selected passage does not prove absence from all documents."]
             if diagnostics.get('indicators_with_bounded_context') else []),
    }
