"""Capability-specific guide projection; legacy guide preferences/records stay intact."""
from apps.scoring.models import CapabilityExecution, RecommendationExecution
from apps.sprints.access import get_authorized_sprint


def capability_guide(data, user):
    sprint_id = data.get('sprint_id')
    sprint = get_authorized_sprint(user, sprint_id) if sprint_id else None
    latest = CapabilityExecution.objects.filter(sprint=sprint).order_by('-created_at').first() if sprint else None
    complete = bool(latest and latest.status == 'completed')
    advice = RecommendationExecution.objects.filter(run_id=latest.run_id).order_by('-created_at').first() if complete else None
    rows = []
    for original in data['steps']:
        row = dict(original)
        step = row['id']
        if step in {'baseline_approval', 'facts_review', 'gaps_evidence'}:
            continue
        if step == 'institution_dna':
            row.update(purpose='Check the institution profile; unknown counts are preserved as unknown. No profile approval is required.')
        if step in {'live_cri', 'recommendations', 'transformation_plan', 'reports'}:
            titles = {'live_cri': 'Capability assessment', 'recommendations': 'Grounded recommendations',
                      'transformation_plan': 'Capability pathways and actions', 'reports': 'Capability report and export'}
            purposes = {'live_cri': 'Explicitly assess readable evidence for all 36 indicators. Model calls use configured credits; viewing history is free.',
                        'recommendations': 'Review evidence requests, contradictions and documented shortfalls. Tailoring requires an explicit request.',
                        'transformation_plan': 'Review conditional sufficient scenarios. Completing tasks never changes scores without reassessment.',
                        'reports': 'Export a completed assessment without baseline approval or model calls.'}
            row.update(title=titles[step], purpose=purposes[step], action_label='Open ' + titles[step].lower(),
                       block_reason=None if sprint else 'Select a sprint first.',
                       details={'workflow': 'capability', 'assessment_status': latest.status if latest else None,
                                'completed_assessment_available': complete},
                       status='not_started')
            if step == 'live_cri':
                row['status'] = 'completed' if complete else 'needs_attention' if latest and latest.status in {'failed', 'cancelled'} else 'in_progress' if latest else 'not_started'
            elif complete:
                row['status'] = 'completed' if step == 'recommendations' and advice and advice.status == 'completed' else 'in_progress'
            elif sprint:
                row['block_reason'] = 'Complete a capability assessment first; no baseline approval is required.'
            if original['status'] == 'skipped':
                row['status'] = 'skipped'
        row['number'] = len(rows) + 1
        rows.append(row)
    data = {**data, 'workflow': 'capability', 'steps': rows}
    current = next((r for r in rows if r['status'] not in {'completed', 'skipped'} and r['is_authorized']), None)
    data.update(current_step=current, current_step_id=current['id'] if current else None,
                current_step_number=current['number'] if current else None,
                completed_count=sum(r['status'] == 'completed' for r in rows),
                skipped_count=sum(r['status'] == 'skipped' for r in rows), total_steps=len(rows))
    return data
