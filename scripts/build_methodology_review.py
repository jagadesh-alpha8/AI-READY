"""Build a documentation-only condition inventory; never edits the active rubric."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/capability'
RUBRIC = ROOT / 'backend/apps/scoring/capability/rubric_v0_2.json'

SCOPES = {
    'C1': 'Institutional decision-making function; adoption covers actual AI initiatives, with the intended portfolio scope stated.',
    'C2': 'Named AI use cases, systems and affected people; distinguish no deployment from deficient controls on a deployment. Applicability remains to be defined.',
    'C3': 'Identified programmes, courses and eligible learners. A narrow offer does not establish institution-wide delivery.',
    'C4': 'Identified faculty or staff roles and cohorts; reach and competence require appropriate eligible and assessed counts.',
    'C5': 'Identified student cohorts/pathways; universal claims require the complete applicable population and reach evidence.',
    'C6': 'Stated workload, computing environment, datasets and intended users; basic work does not require a GPU by default.',
    'C7': 'Named projects, innovation services and eligible participants; a centre name or agreement alone is insufficient.',
    'C8': 'Named services, partnerships or pathways and their users; link results to the stated intervention without claiming unsupported causation.',
    'C9': 'Institutional AI evaluation/evidence/review practice, including substantive processes outside this product.',
}

REVISIONS = {
    'C9.1.A1': 'Repeated reviews evaluate stated AI initiative objectives using traceable evidence and a disclosed method.',
    'C9.1.A2': 'Reviews distinguish changes in institutional activity from changes in measurement definitions or methods.',
    'C9.1.O1': 'Two comparable completed review cycles use evaluation findings to prioritise and assess improvements.',
    'C9.1.O2': 'Recorded checks of measurement stability and validity lead to justified revisions, with limitations retained.',
    'C9.2.A1': 'Sampled institutional AI evaluation findings trace to stated criteria, decisions and original evidence.',
    'C9.3.A1': 'Change reviews identify affected AI activities, applicable external requirements and evidence needing update.',
    'C9.3.A2': 'Dated reviews explain changes to criteria, practice or evidence without rewriting earlier findings.',
    'C9.3.O1': 'Two completed change-review cycles demonstrate timely identification and appropriate reassessment of material AI-related changes.',
    'C9.3.O2': 'Review findings improve monitoring and reduce unnecessary reassessment, with the comparison method stated.',
}


def build():
    raw = RUBRIC.read_bytes()
    rubric = json.loads(raw)
    foundations = {}
    for line in (DOCS / 'NAAC_RUBRIC_REVISION_DRAFT.md').read_text().splitlines():
        if line.startswith('| C'):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if len(cells) != 5 or cells[0] in foundations:
                raise ValueError('Invalid or duplicate foundation review row.')
            foundations[cells[0]] = cells
    if len(foundations) != 36:
        raise ValueError('Expected 36 foundation review rows.')
    rows = []
    for item in rubric['indicators']:
        short = item['code'].removeprefix('AIQIF-')
        foundation = foundations[short]
        for condition in item['conditions']:
            level = condition['level']
            suffix = condition['id'].rsplit('.', 1)[-1]
            candidate = (foundation[2 if suffix == 'F1' else 3] if level == 'F' else
                         REVISIONS.get(f'{short}.{suffix}', condition['text']))
            if level == 'F':
                construct = 'enabling_capacity' if foundation[1] == 'E' else 'ai_specific_starting_capacity_or_activity'
                counterexample = foundation[4]
                period = 'Policy effective interval, curriculum regulation, plan approval/stage or dated activity period, as applicable; no delivery inferred.'
                stage_review = 'Starting capacity/activity only. Planning credit requires an explicit planning criterion; review cumulative transition to AI-specific adoption.'
            elif level == 'A':
                construct = 'demonstrated_ai_activity'
                counterexample = 'A syllabus, attendance list, equipment inventory, unsigned plan or MoU alone cannot establish the required repeated use or competence.'
                period = 'Actual completed delivery/use in the stated period; record duration and frequency without inventing an annual window.'
                stage_review = 'Require AI-specific use in the stated scope. Participation is not competence; explicit skills requirements need assessed work.'
            else:
                construct = 'ai_results_and_outcome_learning'
                counterexample = 'A one-off event, raw volume count, task completion, forecast or untested revision does not demonstrate sustained benefit or effective learning.'
                period = 'Relevant completed comparable measurement/review cycles where repetition is required; not automatically two academic years.'
                stage_review = 'Keep result evidence separate from a process change. A revision based on results is not itself proof that benefit increased.'
            rows.append({
                'condition_id': condition['id'], 'indicator_title': item['name'],
                'stage': level, 'review_status': 'candidate_not_validated',
                'original_requirement': condition['text'], 'candidate_requirement': candidate,
                'candidate_construct': construct, 'original_scope': condition['scope'],
                'candidate_scope_rule': SCOPES[short.split('.')[0]],
                'original_period_rule': condition['period_rule'], 'candidate_period_rule': period,
                'stage_review': stage_review, 'counterexample_or_insufficiency': counterexample,
                'evidence_rule': 'Every factual finding needs exact provenance and compatible scope/date. Silence, unreadable files and unavailable documents remain unknown. Partial support is explained separately.',
                'declaration_policy': 'Criterion-specific respondent/scope policy required before declarations can satisfy this condition; no blanket activation.',
                'numerical_policy': 'No candidate points or tiers assigned. Existing weights and cumulative arithmetic are recorded only as the source baseline.',
                'source_indicator_weight_units': item['weight_units'],
            })
    ids = [row['condition_id'] for row in rows]
    if len(ids) != 216 or len(set(ids)) != 216:
        raise ValueError('Expected exactly 216 distinct conditions.')
    return {
        'status': 'documentation_only_not_a_scoring_release',
        'source_methodology': rubric['version'],
        'source_rubric_sha256': hashlib.sha256(raw).hexdigest(),
        'headline_direction': 'One eventual readiness headline with visible capacity, activity and results components; numerical rules unresolved.',
        'limitations': ['Candidate text and review rules are not empirical validation.',
                       'No production loading path or score/tier activation.',
                       'Applicability, weights, partial credit and thresholds remain unresolved.'],
        'conditions': rows,
    }


if __name__ == '__main__':
    target = DOCS / 'methodology_review_matrix.json'
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n')
    print(f'Wrote 216 candidate review rows to {target.relative_to(ROOT)}')
