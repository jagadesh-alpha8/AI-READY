"""Known-input capability tests; no model calls or production database required.

python -m unittest apps.scoring.test_capability -v
"""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest

from .capability.engine import LEVELS, STATES, _totals, assess, indicator_bounds, release, validate_release
from .capability.planning import actions_for, roadmap
from .capability.evaluation import evaluate, select_context, validate_decisions


class CapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rubric = release()
        cls.ids = [c['id'] for item in cls.rubric['indicators'] for c in item['conditions']]

    def decisions_at(self, level):
        return {c['id']: 'met' if LEVELS.index(c['level']) < level else 'not_met'
                for item in self.rubric['indicators'] for c in item['conditions']}

    def test_taxonomy_and_integer_weights(self):
        self.assertEqual(len(self.ids), 216)
        self.assertEqual(len(set(self.ids)), 216)
        self.assertEqual(sum(i['weight_units'] for i in self.rubric['indicators']), 1000)
        self.assertEqual(self.rubric['status'], 'experimental_proposed')

    def test_uniform_profiles_and_tiers(self):
        for level, score, tier in [(0, 0, None), (1, 33.33, None), (2, 66.67, 'Gold'), (3, 100, 'Platinum')]:
            with self.subTest(level=level):
                result = assess(self.decisions_at(level), self.rubric)
                self.assertEqual(result['exact_score'], score)
                self.assertEqual(result['highest_demonstrated_tier'], tier)
                self.assertTrue(result['tier_is_certain'])

    def test_missing_is_a_range_not_zero_capability(self):
        result = assess({}, self.rubric)
        self.assertEqual((result['lower'], result['upper']), (0, 100))
        self.assertIsNone(result['exact_score'])
        self.assertEqual(result['assessment_coverage'], 0)
        self.assertTrue(all(t['eligibility'] == 'unresolved' for t in result['tiers']))

    def test_audit_counterexample_keeps_full_denominator(self):
        decisions = self.decisions_at(3)
        for item in self.rubric['indicators']:
            if item['code'].endswith(('.3', '.4')):
                for c in item['conditions']:
                    decisions.pop(c['id'])
        incomplete = assess(decisions, self.rubric)
        self.assertEqual((incomplete['lower'], incomplete['upper']), (50, 100))
        self.assertEqual(incomplete['assessment_coverage'], 50)
        self.assertIsNone(incomplete['exact_score'])
        for item in self.rubric['indicators']:
            if item['code'].endswith(('.3', '.4')):
                for c in item['conditions']:
                    decisions[c['id']] = 'met' if c['level'] == 'F' else 'not_met'
        complete = assess(decisions, self.rubric)
        self.assertEqual(complete['exact_score'], 66.67)
        self.assertGreaterEqual(complete['lower'], incomplete['lower'])
        self.assertLessEqual(complete['upper'], incomplete['upper'])

    def test_failed_gate_caps_tiers_even_with_high_overall(self):
        decisions = self.decisions_at(3)
        decisions['AIQIF-C2.1.F1'] = 'not_met'
        result = assess(decisions, self.rubric)
        self.assertGreater(result['lower'], 90)
        self.assertTrue(all(t['eligibility'] == 'requirements_unmet' for t in result['tiers']))

    def test_exact_tier_does_not_require_all_indicator_scores_resolved(self):
        decisions = self.decisions_at(2)
        for suffix in ['O1', 'O2']:
            decisions['AIQIF-C7.1.' + suffix] = 'unknown'
        result = assess(decisions, self.rubric)
        self.assertLess(result['assessment_coverage'], 100)
        self.assertTrue(result['tier_is_certain'])
        self.assertEqual(result['highest_demonstrated_tier'], 'Gold')

    def test_foundational_failure_preserves_advanced_evidence_but_caps_score(self):
        item = self.rubric['indicators'][0]
        decisions = {c['id']: 'met' for c in item['conditions']}
        decisions[item['conditions'][0]['id']] = 'not_met'
        self.assertEqual(indicator_bounds(item, decisions), (0, 0))
        result = assess(decisions, self.rubric)['indicators'][0]
        self.assertEqual(result['conditions'][-1]['state'], 'met')

    def test_all_4096_condition_patterns_match_explicit_completions(self):
        item = self.rubric['indicators'][0]
        ids = [c['id'] for c in item['conditions']]
        for pattern in product(sorted(STATES), repeat=6):
            unresolved = [n for n, state in enumerate(pattern) if state in ('unknown', 'conflicting')]
            possible_levels = []
            for values in product(('met', 'not_met'), repeat=len(unresolved)):
                completed = list(pattern)
                for n, value in zip(unresolved, values):
                    completed[n] = value
                achieved = 0
                for level in range(1, 4):
                    if all(state == 'met' for state in completed[:level * 2]):
                        achieved = level
                possible_levels.append(achieved)
            self.assertEqual(indicator_bounds(item, dict(zip(ids, pattern))),
                             (min(possible_levels), max(possible_levels)), pattern)

    def test_unknown_condition_id_or_state_rejected(self):
        for decisions in [{'invented': 'met'}, {self.ids[0]: 'not_applicable'}, {self.ids[0]: 'yes'}]:
            with self.assertRaises(ValueError):
                assess(decisions, self.rubric)

    def test_release_validation_and_copy_isolation(self):
        for mutate in [lambda r: r['indicators'].pop(),
                       lambda r: r['indicators'][0].update(weight_units=0),
                       lambda r: r['indicators'][0]['conditions'].pop(),
                       lambda r: r['tiers'][0]['gates'].update({'bad': 1})]:
            bad = deepcopy(self.rubric)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_release(bad)
        fresh = release()
        fresh['indicators'].clear()
        self.assertEqual(len(release()['indicators']), 36)

    def test_condition_progress_and_score_resolution_are_separate(self):
        result = assess({self.ids[0]: 'not_met'}, self.rubric)
        self.assertTrue(result['indicators'][0]['resolved'])
        self.assertLess(result['condition_decision_coverage'], result['assessment_coverage'])

    def test_evidence_and_capability_actions_distinguished(self):
        result = assess({self.ids[0]: 'not_met', self.ids[1]: 'conflicting'}, self.rubric)
        actions = {a['id']: a for a in actions_for(result)}
        self.assertEqual(actions[self.ids[0]]['type'], 'develop_capability')
        self.assertEqual(actions[self.ids[1]]['type'], 'resolve_contradiction')
        self.assertEqual(actions['AIQIF-C1.2.F1']['type'], 'supply_evidence')
        self.assertTrue(all(not a['automatic_points'] for a in actions.values()))

    def test_one_c1_transition_contributes_one_overall_point(self):
        levels = {i['code']: 1 for i in self.rubric['indicators']}
        before, _ = _totals(self.rubric, levels)
        levels['AIQIF-C1.1'] = 2
        after, _ = _totals(self.rubric, levels)
        self.assertEqual(after - before, Fraction(1))

    def test_tier_scenarios_rescore_to_their_claimed_targets(self):
        for base in [{}, self.decisions_at(0), self.decisions_at(1), self.decisions_at(2), self.decisions_at(3)]:
            for tier in ['Silver', 'Gold', 'Platinum']:
                with self.subTest(base_known=bool(base), tier=tier):
                    plan = roadmap(base, tier, self.rubric)
                    self.assertTrue(plan['scenario_sufficient'])
                    self.assertEqual(len(plan['requirement_ids']), len(set(plan['requirement_ids'])))
                    scenario = {**base, **{cid: 'met' for cid in plan['requirement_ids']}}
                    result = assess(scenario, self.rubric)
                    match = next(t for t in result['tiers'] if t['name'] == tier)
                    self.assertEqual(match['eligibility'], 'demonstrated')
                    self.assertEqual(result['lower'], plan['projected_minimum'])

    def test_unknown_baseline_has_no_invented_uplift(self):
        self.assertIsNone(roadmap({}, 'Silver', self.rubric)['conditional_uplift'])

    def test_already_achieved_tier_has_no_new_requirements(self):
        plan = roadmap(self.decisions_at(3), 'Platinum', self.rubric)
        self.assertTrue(plan['already_demonstrated'])
        self.assertEqual(plan['requirement_ids'], [])
        self.assertEqual(plan['conditional_uplift'], 0)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.item = release()['indicators'][0]
        self.sources = [{'id': 'document-a:1', 'text': 'The institution approved an AI strategy for the current academic year.'}]
        self.row = {'condition_id': self.item['conditions'][0]['id'], 'state': 'met',
                    'reason': 'Scoped current evidence supplied.', 'scope_supported': True,
                    'period_supported': True, 'citations': [{'source_id': 'document-a:1',
                    'quote': self.sources[0]['text']}]}

    def validate(self, row):
        return next(r for r in validate_decisions(self.item, {'conditions': [row]}, self.sources)
                    if r['condition_id'] == row['condition_id'])

    def test_matching_citation_passes_grounding_check(self):
        self.assertEqual(self.validate(self.row)['state'], 'met')

    def test_fabricated_quote_page_or_missing_scope_fails_closed(self):
        for mutate in [lambda r: r['citations'][0].update(quote='A quotation invented by the model.'),
                       lambda r: r['citations'][0].update(source_id='other-tenant:9'),
                       lambda r: r.update(scope_supported=False),
                       lambda r: r.update(period_supported=False),
                       lambda r: r.update(state=['met']),
                       lambda r: r.update(citations=[])]:
            row = deepcopy(self.row)
            mutate(row)
            self.assertEqual(self.validate(row)['state'], 'unknown')

    def test_duplicates_and_omissions_are_unknown(self):
        result = validate_decisions(self.item, {'conditions': [self.row, self.row]}, self.sources)
        self.assertTrue(all(r['state'] == 'unknown' for r in result))
        self.assertEqual(len(result), 6)

    def test_conflicting_requires_two_distinct_passages(self):
        self.assertEqual(self.validate({**self.row, 'state': 'conflicting'})['state'], 'unknown')

    def test_empty_sources_complete_all_36_as_unknown_without_model_calls(self):
        class NoCalls:
            def extract_structured_data(self, **kwargs):
                raise AssertionError('Must not be called without evidence')
        result = evaluate([], service=NoCalls(), population='All institution programmes', reference_period='2025-26')
        self.assertEqual(len(result['records']), 216)
        self.assertEqual(result['indicator_calls'], 0)
        self.assertEqual(set(result['decisions'].values()), {'unknown'})

    def test_call_budget_and_provider_failure_keep_remaining_unknown(self):
        class Failing:
            calls = 0
            def extract_structured_data(self, **kwargs):
                self.calls += 1
                raise RuntimeError('private provider message')
        service = Failing()
        result = evaluate(self.sources, service=service, population='All faculty',
                          reference_period='2025-26', max_calls=2)
        self.assertEqual(service.calls, 2)
        self.assertEqual(len(result['traces']), 36)
        self.assertEqual(set(result['decisions'].values()), {'unknown'})
        self.assertNotIn('private provider message', str(result))

    def test_context_is_deterministic_bounded_and_duplicate_ids_rejected(self):
        sources = self.sources + [{'id': 'document-b:1', 'text': 'No AI strategy exists. ' * 10000}]
        selected = select_context(self.item, sources, max_chars=2000)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 2000)
        self.assertEqual(selected, select_context(self.item, list(reversed(sources)), max_chars=2000))
        with self.assertRaises(ValueError):
            select_context(self.item, self.sources * 2)


if __name__ == '__main__':
    unittest.main()
