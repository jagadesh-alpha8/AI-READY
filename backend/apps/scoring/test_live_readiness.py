"""Actual default-release evaluation path using synthetic, scoped evidence only."""
import json
from copy import deepcopy
from fractions import Fraction
from unittest import TestCase

from .capability.engine import assess, indicator_bounds, release, validate_release
from .capability.evaluation import evaluate, select_context, SYSTEM_PROMPT
from .capability.planning import roadmap
from .capability.scenarios import evaluate_plan


class LiveReadinessTests(TestCase):
    def setUp(self):
        self.rubric = release()
        self.item = self.rubric['indicators'][0]

    def test_new_default_is_active_independent_release(self):
        self.assertEqual(self.rubric['version'], 'AIQIF-CAP-0.3')
        self.assertEqual(self.rubric['aggregation'], 'independent_conditions')
        self.assertTrue(all(i['scoring_mode'] == 'independent_conditions' for i in self.rubric['indicators']))

    def test_one_positive_assertion_moves_the_actual_indicator_bound(self):
        result = assess({self.item['conditions'][0]['id']: 'met'})
        self.assertEqual(result['indicators'][0]['lower'], 16.67)
        self.assertGreater(result['lower'], 0)
        self.assertEqual(result['upper'], 100)

    def test_missing_foundation_does_not_erase_supported_activity(self):
        states = {c['id']: 'met' for c in self.item['conditions']}
        states[self.item['conditions'][0]['id']] = 'not_met'
        result = assess(states)
        self.assertEqual(result['indicators'][0]['lower'], 83.33)
        self.assertEqual(result['indicators'][0]['upper'], 83.33)

    def test_unknowns_remain_unknown_and_negative_evidence_reduces_upper(self):
        self.assertEqual((assess({})['lower'], assess({})['upper']), (0, 100))
        cid = self.item['conditions'][0]['id']
        negative = assess({cid: 'not_met'})
        self.assertEqual(negative['lower'], 0)
        self.assertLess(negative['upper'], 100)

    def test_old_release_remains_replayable_with_its_original_gates(self):
        old = release('AIQIF-CAP-0.2')
        cid = old['indicators'][0]['conditions'][0]['id']
        result = assess({cid: 'met'}, old)
        self.assertEqual(result['lower'], 0)
        self.assertEqual(result['engine_version'], 'capability-engine-0.2.0')
        self.assertEqual(result['methodology'], 'AIQIF-CAP-0.2')

    def test_achievement_badges_are_separate_from_numeric_credit(self):
        decisions = {c['id']: 'met' for i in self.rubric['indicators'] for c in i['conditions']}
        result = assess(decisions)
        self.assertEqual(result['exact_score'], 100)
        self.assertIsNone(result['highest_demonstrated_tier'])
        self.assertTrue(all(t['eligibility'] == 'unresolved' for t in result['tiers']))
        self.assertFalse(roadmap(decisions, 'Silver')['scenario_sufficient'])

    def test_shared_budgets_and_mixed_modes_are_validated(self):
        for kind in ('group', 'mode', 'weight', 'shared_weight'):
            bad = deepcopy(self.rubric)
            if kind == 'group': bad['indicators'][0]['credit_group'] = 'new-credit'
            if kind == 'mode': bad['indicators'][0].pop('scoring_mode')
            if kind == 'weight':
                bad['indicators'][0]['weight_units'] += 1
                bad['indicators'][1]['weight_units'] -= 1
            if kind == 'shared_weight':
                members = [i for i in bad['indicators'] if i['credit_group'] == 'literacy_provision']
                members[0]['weight_units'] += 1
                members[1]['weight_units'] -= 1
            with self.assertRaises(ValueError): validate_release(bad)

    def test_scoped_erp_evidence_reaches_new_evaluator_and_receives_partial_credit(self):
        quote = 'The ERP system provides admissions and finance services to staff.'
        sources = [{'id': 'erp', 'page_number': 1, 'text':
                    'Institution name: Example Institute\nReporting period: 2023-24\n' + quote}]
        seen = []
        class Service:
            def extract_structured_data(inner, **kwargs):
                data = json.loads(kwargs['user_content']);indicator = data['indicator'];seen.append(data)
                return {'conditions': [dict(condition_id=c['id'], state='met' if c['id'] == 'AIQIF-C8.1.F1' else 'unknown',
                    reason='The dated report establishes the service purpose for the stated institution.' if c['id'] == 'AIQIF-C8.1.F1' else 'Not established by this evidence.',
                    scope_supported=c['id'] == 'AIQIF-C8.1.F1', period_supported=c['id'] == 'AIQIF-C8.1.F1',
                    citations=[{'source_id': 'erp', 'quote': quote}] if c['id'] == 'AIQIF-C8.1.F1' else [])
                    for c in indicator['conditions']]}
        evaluated = evaluate(sources, service=Service(), population='Institutional overview',
                             reference_period='Source-specific evidence periods')
        result = assess(evaluated['decisions'])
        service = next(i for i in result['indicators'] if i['code'] == 'AIQIF-C8.1')
        self.assertEqual(service['lower'], 16.67)
        self.assertGreater(result['lower'], 0)
        self.assertEqual(len(evaluated['records']), 216)
        self.assertTrue(all(x['indicator']['scoring_mode'] == 'independent_conditions' for x in seen))

    def test_balanced_retrieval_preserves_erp_and_exact_windows(self):
        item = next(i for i in self.rubric['indicators'] if i['code'] == 'AIQIF-C8.1')
        sources = [{'id': 'irrelevant', 'text': 'Artificial intelligence AI AI research conference. ' * 1000},
                   {'id': 'service', 'text': 'ERP admissions finance administration digital service for students.'}]
        selected = select_context(item, sources)
        self.assertIn('service', [s['id'] for s in selected])
        self.assertLessEqual(sum(len(s['text']) for s in selected), 18000)
        by_id = {s['id']: s for s in sources}
        for s in selected:
            self.assertEqual(s['text'], by_id[s['id']]['text'][s['text_offset']:s['text_offset'] + len(s['text'])])

    def test_paired_plan_delta_uses_new_independent_arithmetic(self):
        baseline = {c['id']: 'unknown' for i in self.rubric['indicators'] for c in i['conditions']}
        cid = self.item['conditions'][0]['id']
        mapping = {'condition_id': cid, 'state': 'met', 'phase': 'implementation', 'coverage': 'complete',
                   'scope_compatible': True, 'assumptions': ['Implemented and evidenced'], 'kind': 'development', 'action_id': 'x'}
        result = evaluate_plan(baseline, [mapping], self.rubric)
        scenario = result['scenarios']['implementation']
        self.assertGreater(scenario['result']['lower'], 0)
        self.assertEqual(scenario['paired_change']['lower'], 0)
        self.assertGreater(scenario['paired_change']['upper'], 0)
        self.assertFalse(result['actual_assessment_changed'])

    def test_delivery_credit_and_assessed_competence_keep_distinct_plan_phases(self):
        from .capability.scenarios import result_dependent
        conditions = {c['id']: c for i in self.rubric['indicators'] for c in i['conditions']}
        self.assertFalse(result_dependent(conditions['AIQIF-C5.1.A1']))
        self.assertTrue(result_dependent(conditions['AIQIF-C4.1.A1']))
        self.assertTrue(result_dependent(conditions['AIQIF-C5.1.O1']))
