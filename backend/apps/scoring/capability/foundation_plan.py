"""Evidence-aware foundation plan proposals; no scores, badges or baseline writes."""
VERSION = 'foundation-path-0.1'

# These are pilot goal templates, not calibrated achievement gates.
GOALS = (
    ('governance', 'Establish safe and accountable AI use',
     ['C1.1.F2', 'C1.2.A1', 'C2.1.F1', 'C2.2.F1', 'C2.3.F1'],
     ['C1.1', 'C1.2', 'C2.1', 'C2.2', 'C9.1'], [], 'Institution sponsor and data lead',
     ['Identify the actual AI uses, responsible people and applicable risks.',
      'If controls are missing, define permitted uses, escalation and data handling before a pilot.']),
    ('resources', 'Make existing resources suitable for a bounded AI workload',
     ['C6.1.F1', 'C6.1.F2', 'C6.2.F1', 'C6.3.F2', 'C6.4.F2'],
     ['C6.1', 'C6.2', 'C6.3', 'C6.4'], [], 'IT and data leads',
     ['Check access, specifications, data permissions and recovery for one named introductory workload.',
      'Reuse suitable existing provision; propose new resources only for a verified shortfall.']),
    ('faculty', 'Prepare faculty for a specific teaching use',
     ['C4.1.F1', 'C4.1.A1', 'C4.2.F2'],
     ['C4.1', 'C4.2', 'C4.3', 'C6.1'], ['governance', 'resources'], 'Academic development lead',
     ['Choose an identified faculty group and a role-relevant practical task.',
      'If the pathway is not already operating, deliver supervised practice and assess the skill; attendance alone is insufficient.']),
    ('students', 'Deliver and assess AI learning for a defined student group',
     ['C3.1.F1', 'C3.3.F2', 'C3.4.F2', 'C5.1.F1', 'C5.1.O1'],
     ['C3.1', 'C3.2', 'C3.4', 'C5.1', 'C5.3', 'C6.1'], ['governance', 'resources'], 'Programme and student learning leads',
     ['Select a programme or cohort, learning objective, mentoring route and acceptable-use instructions.',
      'If delivery is missing, run a bounded learning activity and assess actual work against an explicit criterion.']),
    ('operations', 'Evaluate one safe AI use in an existing service',
     ['C8.1.F2', 'C8.1.A1', 'C8.4.F1', 'C8.4.F2'],
     ['C8.1', 'C8.4', 'C6.1', 'C6.2'], ['governance', 'resources'], 'Service owner',
     ['Select a suitable service and intended outcome; establish a baseline and a human review route.',
      'If a suitable use is not already operating, test a bounded pilot with approved data and review its effects before scaling.']),
    ('review', 'Keep evidence and decisions linked to measured progress',
     ['C9.1.F1', 'C9.2.F1', 'C9.4.F2'],
     ['C9.1', 'C9.2', 'C9.3', 'C9.4'], [], 'Evidence coordinator and programme sponsor',
     ['Maintain source, population, period and owner for each claim used in the baseline.',
      'Review pilot results and update the evidence before reassessment; task completion alone changes no score.']),
)


def baseline_review(records, result):
    decided = sum(r['state'] in ('met', 'not_met') for r in records)
    informative = sum(i['lower'] > 0 or i['upper'] < 100 for i in result['indicators'])
    status = 'needs_evidence_review' if not decided else 'partially_established' if decided < len(records) else 'resolved'
    return {'status': status, 'decided_conditions': decided, 'total_conditions': len(records),
            'informative_indicators': informative,
            'numerical_estimate_available': result['exact_score'] is not None,
            'message': ('No positive or negative requirement has been established. This is an incomplete evidence baseline, not a useful 0–100 readiness estimate.'
                        if not decided else 'The baseline contains supported findings; unresolved requirements remain explicit. A bound is not a point estimate.')}


def build_foundation_plan(rubric, records, result):
    if rubric.get('aggregation') != 'independent_conditions':
        return None
    conditions = {c['id']: c for i in rubric['indicators'] for c in i['conditions']}
    decisions = {r['condition_id']: r for r in records}
    assets = [{'condition_id': r['condition_id'], 'requirement': conditions[r['condition_id']]['text'],
               'basis': r.get('citations', []), 'reason': r.get('reason', '')}
              for r in records if r['state'] == 'met']
    goals, questions = [], []
    for key, title, suffixes, asset_codes, dependencies, role, steps in GOALS:
        ids = ['AIQIF-' + s for s in suffixes]
        remaining = [cid for cid in ids if decisions[cid]['state'] != 'met']
        if not remaining:
            continue
        unresolved = [cid for cid in remaining if decisions[cid]['state'] in ('unknown', 'conflicting')]
        shortfalls = [cid for cid in remaining if decisions[cid]['state'] == 'not_met']
        related = [a for a in assets if a['condition_id'].rsplit('.', 1)[0] in {'AIQIF-' + code for code in asset_codes}]
        goals.append({'id': key, 'title': title, 'target_condition_ids': remaining,
            'verified_condition_ids': [cid for cid in ids if cid not in remaining],
            'unresolved_condition_ids': unresolved, 'documented_shortfall_ids': shortfalls,
            'existing_strengths': related, 'depends_on': list(dependencies), 'suggested_role': role,
            'status': 'verify_before_implementation' if unresolved else 'documented_development_need',
            'steps': (['First establish which listed practices already operate for the relevant scope and period; reuse them instead of rebuilding.'] if unresolved else []) + list(steps),
            'completion_evidence': [conditions[cid]['completion_evidence'] for cid in remaining],
            'conditional': bool(unresolved), 'automatic_points': False})
        if unresolved:
            questions.append({'id': key, 'title': title, 'condition_ids': unresolved,
                'question': 'Which of these practices already operate, which are explicitly absent, and which cannot yet be established? Provide the scope, period and supporting records.',
                'requirements': [conditions[cid]['text'] for cid in unresolved],
                'answer_policy': 'This is a review prompt, not a scoring input. Only a fresh supported assessment changes the baseline.'})
    active_ids = {g['id'] for g in goals}
    for goal in goals:
        goal['depends_on'] = [d for d in goal['depends_on'] if d in active_ids]
    # Same goals in every pace; neither timing nor completion is promised.
    orders = (
        ('Immediate', '3–6 months', [['governance', 'resources'], ['faculty', 'students'], ['operations'], ['review']]),
        ('Progressive', '6–12 months', [['governance'], ['resources'], ['faculty', 'students'], ['operations'], ['review']]),
        ('Gradual', '12–18 months', [[key] for key, *_ in GOALS]),
    )
    routes = [{'name': name, 'indicative_duration': duration,
               'batches': [[key for key in batch if key in active_ids] for batch in batches if any(key in active_ids for key in batch)],
               'assumptions': ['Illustrative foundation timing only; confirm capacity, safeguards, programme mix and procurement.',
                               'Unresolved prerequisites must be established before dependent implementation.'],
               'cost': None, 'outcomes': [g['id'] for g in goals]} for name, duration, batches in orders]
    covered = {cid for q in questions for cid in q['condition_ids']}
    return {'version': VERSION, 'status': 'pilot_proposal_not_achievement_standard',
        'destination': 'Proposed Silver foundation goals', 'current_level': 'not_verified',
        'achievement_awarded': False, 'baseline': baseline_review(records, result),
        'existing_strengths': assets, 'goals': goals, 'routes': routes,
        'review_questions': questions[:25],
        'other_unresolved_requirements': sum(r['state'] in ('unknown', 'conflicting') and r['condition_id'] not in covered for r in records),
        'limitations': ['This is a proposed foundation pathway, not a calibrated Silver gate or an inferred missing-capability diagnosis.',
                       'Routes contain the same remaining outcomes. Suggested roles and timing require local feasibility review.',
                       'No verified work is repeated. Evidence questions are a prioritised subset, not a complete review of all advanced requirements.']}
