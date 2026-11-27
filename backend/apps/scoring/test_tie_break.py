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
    def test_mean_of_three_with_parts(self):
        # mean-credit-of-three-v1 (27 Nov 2026): the third pass is averaged in, not left to decide alone.
        records, trace, service = run({A: ['met', 'unknown', 'met'], B: ['unknown', 'met', 'met'],
                                       C: ['met', 'unknown', 'not_met']}, parts=True)
        self.assertEqual(records[A]['credit'], 0.6667)        # (1 + 0 + 1) / 3
        self.assertEqual(records[B]['credit'], 0.6667)
        self.assertEqual(records[C]['credit'], 0.3333)
        # Met only when all three passes say met; a split with no majority other than met goes to review.
        self.assertEqual(records[A]['state'], 'unknown')
        self.assertEqual(records[A]['cause'], 'assessor_disagreement')
        self.assertEqual(records[C]['state'], 'unknown')
        self.assertEqual(records[C]['cause'], 'assessor_disagreement')
        self.assertEqual(records[A]['agreement'], 'mean of three passes')
        self.assertEqual(sorted(service.calls[2]), sorted([A, B, C]))
        self.assertEqual(trace['agreement_audit']['passes'], 3)
        self.assertEqual(records[A]['pass_credits'], [1.0, 0.0, 1.0])
        self.assertEqual(trace['agreement_audit']['tie_break']['rule'], 'mean-credit-of-three-v1')
        # All three passes stay on the parts, so the credit can be recomputed from them (layer 2 does).
        from .capability.layer2 import _recredit
        for cid in (A, B, C):
            self.assertIn('third_credited_as', records[cid]['parts'][0])
            self.assertAlmostEqual(_recredit(records[cid]['parts'], cid), records[cid]['credit'], places=3)
        # Each pass's own proposals are kept, not only the validated records (test 13: why a second pass's
        # quotations failed could not be seen).
        audit = trace['agreement_audit']
        second = audit['second_response_audit']['model_response']['conditions']   # keyed by condition id
        self.assertIn('findings', second[A])
        self.assertEqual(audit['second_parts'][A]['credit'], 0.0)
        third = audit['tie_break']
        self.assertIn('findings', third['response_audit']['model_response']['conditions'][A])
        self.assertEqual(sorted(third['parts']), sorted([A, B, C]))

    def test_one_outlying_pass_moves_a_condition_by_a_third(self):
        records, trace, service = run({A: ['unknown', 'met', 'unknown']}, parts=True)
        self.assertEqual((records[A]['state'], records[A]['credit']), ('unknown', 0.3333))
        self.assertNotEqual(records[A].get('cause'), 'assessor_disagreement')   # two passes agree on unknown

    def test_three_passes_that_all_say_met_stay_met(self):
        records, trace, service = run({A: ['met', 'unknown', 'met']}, parts=True)
        self.assertEqual(records[A]['state'], 'unknown')
        records, trace, service = run({A: ['met', 'met', 'met']}, parts=True)
        self.assertEqual((records[A]['state'], records[A]['credit']), ('met', 1.0))


class TieBreakPolicyTests(SimpleTestCase):
    def test_needs_two_passes_and_gets_room_for_its_requests(self):
        from .capability.execution import AssessmentDisabled, policy
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30'):
            self.assertEqual(policy()['tie_break'], 'mean-credit-of-three-v1')  # part judgment is the default
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30', CAPABILITY_JUDGMENT='conditions'):
            self.assertEqual(policy()['tie_break'], 'majority-of-three-v1')
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=False, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30', CAPABILITY_PART_QUOTE_REPAIR=False):
            with self.assertRaises(AssessmentDisabled):
                policy()
        # The quotation repair is frozen into the policy and gets room for its requests too.
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=180,
                               CAPABILITY_MAX_COST_USD='30', CAPABILITY_PART_QUOTE_REPAIR=True):
            self.assertEqual(policy()['part_quote_repair'], 'quote-repair-v1')
        with override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=140,
                               CAPABILITY_MAX_COST_USD='30', CAPABILITY_JUDGMENT='conditions',
                               CAPABILITY_PART_QUOTE_REPAIR=True):
            self.assertNotIn('part_quote_repair', policy())   # part judgment only
        with override_settings(CAPABILITY_AGREEMENT_PASSES=1, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=40,
                               CAPABILITY_MAX_COST_USD='30'):
            with self.assertRaises(AssessmentDisabled):
                policy()
        with self.assertRaisesRegex(ValueError, 'two agreement passes'):
            evaluate(SOURCES, service=None, population='S', reference_period='2024', agreement_passes=1, tie_break=True)


class QuoteRepairTests(SimpleTestCase):
    """quote-repair-v1: a pass whose found parts all failed their quotations is asked once more for those requirements
    (test 13: full credit lost in one pass to quotations alone)."""

    class Service:
        def __init__(self, bad_quote_calls, repair_fixes=True):
            self.bad, self.fixes, self.calls, self.payloads = set(bad_quote_calls), repair_fixes, [], []

        def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name):
            payload = json.loads(user_content)
            self.payloads.append(payload)
            conditions = payload['indicator']['conditions']
            self.calls.append([c['id'] for c in conditions])
            n = len(self.calls) - 1
            window = next(s for s in payload['sources'] if s.get('evidence_role') != 'report_timestamp')
            repair = 'quotation_repair' in payload
            good = not (n in self.bad or (repair and not self.fixes))
            quote = 'runs an ERP digital service for admissions' if good else 'operates an ERP platform serving admissions'
            rows = {}
            for c in conditions:
                found = c['id'] == A
                rows[c['id']] = {'reason': 'Scripted.', 'scope_supported': True, 'period_supported': True,
                                 'findings': [{'part_id': p['id'], 'finding': 'full' if found else 'not_found',
                                               'citations': [{'source_id': window['id'], 'quote': quote}] if found else []}
                                              for p in c['parts']]}
            return {'conditions': rows}

    def judge(self, service, quote_repair=True):
        result = evaluate(SOURCES, service=service, population='Students', reference_period='2023-24', rubric=rubric(),
                          retrieval_policy={'mode': 'bm25'}, agreement_passes=2, judgment='parts', tie_break=True,
                          quote_repair=quote_repair)
        return {r['condition_id']: r for r in result['records']}, result['traces'][0]

    def test_a_second_pass_with_bad_quotations_is_repaired(self):
        service = self.Service(bad_quote_calls={1})
        records, trace = self.judge(service)
        self.assertEqual(records[A]['credit'], 1.0)          # no disagreement: the repaired pass agrees
        self.assertEqual(records[A]['pass_credits'], [1.0, 1.0])
        self.assertEqual(service.calls[2], [A])               # one repair request, for that requirement only
        self.assertIn(A, service.payloads[2]['quotation_repair']['parts'])
        repair = trace['quote_repair_audit'][0]
        self.assertEqual((repair['pass'], repair['repaired'], repair['kept']), ('second', [A], []))
        self.assertNotIn('tie_break', trace['agreement_audit'])

    def test_without_the_repair_the_pass_disagrees(self):
        service = self.Service(bad_quote_calls={1})
        records, trace = self.judge(service, quote_repair=False)
        self.assertEqual(records[A]['pass_credits'][:2], [1.0, 0.0])
        self.assertIn('tie_break', trace['agreement_audit'])
        self.assertNotIn('quote_repair_audit', trace)

    def test_one_bad_quotation_beside_good_ones_is_not_repaired(self):
        """Audit, 23 Nov: the repair is for requirements whose found parts all failed, not for one misquoted part."""
        class Mixed(self.Service):
            def extract_structured_data(self, **kwargs):
                answer = super().extract_structured_data(**kwargs)
                if len(self.calls) == 2:   # the second pass: the first part keeps its good quotation, the rest fail
                    row = answer['conditions'][A]
                    for finding in row['findings'][1:]:
                        for citation in finding['citations']:
                            citation['quote'] = 'operates an ERP platform serving admissions'
                return answer
        service = Mixed(bad_quote_calls=set())
        records, trace = self.judge(service)
        self.assertNotIn('quote_repair_audit', trace)
        self.assertFalse(any('quotation_repair' in p for p in service.payloads))

    def test_a_repair_that_still_fails_keeps_the_pass_as_it_was(self):
        service = self.Service(bad_quote_calls={0}, repair_fixes=False)
        records, trace = self.judge(service)
        repair = trace['quote_repair_audit'][0]
        self.assertEqual((repair['pass'], repair['repaired'], repair['kept']), ('first', [], [A]))
        self.assertEqual(records[A]['pass_credits'][0], 0.0)   # still not found; nothing invented
