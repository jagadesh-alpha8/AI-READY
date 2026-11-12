"""Tie-break pass: conditions two passes disagree on get a third judgment and the majority state stands."""
import json

from django.test import SimpleTestCase, override_settings

from .capability.engine import release
from .capability.evaluation import evaluate

TEXT = ('The institution runs an ERP digital service for admissions and examinations; its purpose is to process '
        'admission records for every programme. The Registrar office is the responsible owner of the ERP. ') * 6
SOURCES = [{'id': 'p1', 'document_id': 'ssr', 'page_number': 1, 'text': TEXT, 'retrieval_hints': []}]
CODE = 'AIQIF-C8.1'
A, B, C = 'AIQIF-C8.1.F1', 'AIQIF-C8.1.F2', 'AIQIF-C8.1.A1'


def rubric():
    full = release()
    return {**full, 'indicators': [i for i in full['indicators'] if i['code'] == CODE]}


class Script:
    """Answers by pass number: `plan[condition][pass]` is the state ('met', 'unknown' or 'not_met')."""
    def __init__(self, plan, parts=False):
        self.plan, self.parts, self.calls = plan, parts, []

    def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name):
        payload = json.loads(user_content)
        conditions = payload['indicator']['conditions']
        self.calls.append([c['id'] for c in conditions])
        attempt = len(self.calls) - 1
        window = next(s for s in payload['sources'] if s.get('evidence_role') != 'report_timestamp')
        cite = [{'source_id': window['id'], 'quote': 'runs an ERP digital service for admissions'}]
        rows = {}
        for c in conditions:
            state = self.plan.get(c['id'], ['unknown'] * 3)[attempt]
            if self.parts:
                finding = {'met': 'full', 'unknown': 'not_found', 'not_met': 'contradicted'}[state]
                rows[c['id']] = {'reason': 'Scripted.', 'scope_supported': True, 'period_supported': True,
                                 'findings': [{'part_id': p['id'], 'finding': finding,
                                               'citations': cite if finding != 'not_found' else []} for p in c['parts']]}
            else:
                rows[c['id']] = {'state': state, 'reason': 'Scripted.', 'scope_supported': True, 'period_supported': True,
                                 'citations': cite if state != 'unknown' else []}
        return {'conditions': rows}


def run(plan, *, parts=False, tie_break=True):
    service = Script(plan, parts=parts)
    result = evaluate(SOURCES, service=service, population='Students', reference_period='2023-24', rubric=rubric(),
                      retrieval_policy={'mode': 'bm25'}, agreement_passes=2, judgment='parts' if parts else 'conditions',
                      tie_break=tie_break)
    return {r['condition_id']: r for r in result['records']}, result['traces'][0], service


class ConditionTieBreakTests(SimpleTestCase):
    PLAN = {A: ['met', 'unknown', 'met'],          # third agrees with the first
            B: ['unknown', 'met', 'met'],          # third agrees with the second: credit the first pass missed
            C: ['met', 'unknown', 'not_met']}      # no majority

    def test_majority_of_three_decides_only_disagreed_conditions(self):
        records, trace, service = run(self.PLAN)
        self.assertEqual(records[A]['state'], 'met')
        self.assertEqual(records[B]['state'], 'met')
        self.assertTrue(records[B]['citations'])
        self.assertEqual(records[C]['state'], 'unknown')
        self.assertEqual(records[C]['cause'], 'assessor_disagreement')
        # The third request carried only the three disagreed conditions.
        self.assertEqual(len(service.calls), 3)
        self.assertEqual(sorted(service.calls[2]), sorted([A, B, C]))
        audit = trace['agreement_audit']
        self.assertEqual(audit['passes'], 3)
        self.assertEqual(sorted(audit['tie_break']['resolved']), sorted([A, B]))

    def test_without_tie_break_a_disagreement_stays_unknown(self):
        records, trace, service = run(self.PLAN, tie_break=False)
        for cid in (A, B, C):
            self.assertEqual(records[cid]['state'], 'unknown')
        self.assertEqual(len(service.calls), 2)

    def test_no_disagreement_means_no_third_request(self):
        records, trace, service = run({A: ['met', 'met', 'met']})
        self.assertEqual(len(service.calls), 2)
        self.assertNotIn('tie_break', trace['agreement_audit'])


class PartTieBreakTests(SimpleTestCase):
    def test_majority_of_three_with_parts(self):
        records, trace, service = run({A: ['met', 'unknown', 'met'], B: ['unknown', 'met', 'met'],
                                       C: ['met', 'unknown', 'not_met']}, parts=True)
        self.assertEqual(records[A]['state'], 'met')
        self.assertEqual(records[A]['credit'], 1.0)          # the two agreeing passes, averaged
        self.assertEqual(records[B]['state'], 'met')
        self.assertEqual(records[B]['credit'], 1.0)
        self.assertEqual(records[C]['state'], 'unknown')
        self.assertEqual(records[C]['cause'], 'assessor_disagreement')
        self.assertEqual(sorted(service.calls[2]), sorted([A, B, C]))
        self.assertEqual(trace['agreement_audit']['passes'], 3)
        self.assertEqual(records[A]['pass_credits'], [1.0, 0.0, 1.0])
        self.assertEqual(trace['agreement_audit']['tie_break']['rule'], 'median-credit-of-three-v1')

    def test_one_outlying_pass_cannot_move_a_condition(self):
        records, trace, service = run({A: ['unknown', 'met', 'unknown']}, parts=True)
        self.assertEqual((records[A]['state'], records[A]['credit']), ('unknown', 0.0))


class TieBreakPolicyTests(SimpleTestCase):
    def test_needs_two_passes_and_gets_room_for_its_requests(self):
        from .capability.execution import AssessmentDisabled, policy
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30'):
            self.assertEqual(policy()['tie_break'], 'median-credit-of-three-v1')  # part judgment is the default
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30', CAPABILITY_JUDGMENT='conditions'):
            self.assertEqual(policy()['tie_break'], 'majority-of-three-v1')
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=False, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30'):
            with self.assertRaises(AssessmentDisabled):
                policy()
        with override_settings(CAPABILITY_AGREEMENT_PASSES=1, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=40,
                               CAPABILITY_MAX_COST_USD='30'):
            with self.assertRaises(AssessmentDisabled):
                policy()
        with self.assertRaisesRegex(ValueError, 'two agreement passes'):
            evaluate(SOURCES, service=None, population='S', reference_period='2024', agreement_passes=1, tie_break=True)
