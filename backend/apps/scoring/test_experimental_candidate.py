import copy
import json
from fractions import Fraction
from pathlib import Path
from unittest import TestCase

from .capability.experimental_candidate import digest, evaluate_candidate

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / 'docs/capability'


class CandidateReviewTests(TestCase):
    def setUp(self):
        self.candidate = json.loads((DOCS / 'ladder_candidate_v0_2.json').read_text())
        self.profiles = json.loads((DOCS / 'ladder_profiles_candidate_v0_1.json').read_text())
        self.context = {'scope_verified': None, 'currency_verified': None,
                        'coverage_verified': None, 'critical_risks': 'unknown'}

    def evaluate(self, decisions=None, **overrides):
        kwargs = dict(profile_id='engineering', gate_context=self.context)
        kwargs.update(overrides)
        return evaluate_candidate(self.candidate, self.profiles, decisions or {}, **kwargs)

    def test_all_216_requirements_reviewed_with_fresh_identities(self):
        rows = self.candidate['requirements']
        self.assertEqual(len(rows), 216)
        self.assertEqual(len({r['candidate_id'] for r in rows}), 216)
        self.assertEqual({s: sum(r['stage'] == s for r in rows) for s in ('F', 'A', 'O')},
                         {'F': 72, 'A': 72, 'O': 72})
        self.assertTrue(all(r['re_adjudication_required'] and r['source_requirement']
                            and r['requirement'] and r['evidence_rule'] for r in rows))

    def test_six_hand_adjudicated_acceptance_cases(self):
        cases = json.loads((DOCS / 'ladder_candidate_acceptance_cases.json').read_text())['cases']
        for case in cases:
            with self.subTest(case=case['id']):
                self.assertEqual(case['candidate_hash'], digest(self.candidate))
                self.assertEqual(case['profile_release_hash'], digest(self.profiles))
                result = self.evaluate(case['decisions'], profile_id=case['profile'], gate_context=case['gate_context'])
                self.assertEqual(result['proposed_silver_gate']['status'], case['expected_gate'])
                for stage in case['positive_components']:
                    self.assertGreater(Fraction(result['components'][stage]['lower']), 0)
                for stage in case['zero_lower_components']:
                    self.assertEqual(Fraction(result['components'][stage]['lower']), 0)
                self.assertIsNone(result['headline_score'])
                self.assertEqual(result['badge_status'], 'not_awarded_uncalibrated')

    def test_overlap_group_has_one_budget_despite_two_indicators(self):
        rows = self.candidate['requirements']
        decisions = {r['candidate_id']: 'met' for r in rows
                     if r['credit_group'] == 'literacy_provision' and r['stage'] == 'F'}
        result = self.evaluate(decisions)
        self.assertEqual(len(decisions), 4)
        self.assertEqual(result['components']['F']['credit_groups'], 32)
        self.assertEqual(Fraction(result['components']['F']['lower']), Fraction(100, 32))
        self.assertEqual(result['groups']['literacy_provision']['F']['lower'], '100')

    def test_all_unknown_retains_uncertainty(self):
        result = self.evaluate()
        for stage in ('F', 'A', 'O'):
            self.assertEqual(result['components'][stage]['lower'], '0')
            self.assertEqual(result['components'][stage]['upper'], '100')

    def test_all_met_all_not_met_and_profiles_preserve_denominator(self):
        for state, value in (('met', '100'), ('not_met', '0')):
            decisions = {r['candidate_id']: state for r in self.candidate['requirements']}
            for profile in self.profiles['profiles']:
                result = self.evaluate(decisions, profile_id=profile)
                for component in result['components'].values():
                    self.assertEqual((component['lower'], component['upper']), (value, value))
                    self.assertEqual(component['credit_groups'], 32)
                self.assertEqual(result['badge_status'], 'not_awarded_uncalibrated')

    def test_critical_risk_or_failed_coverage_blocks_even_with_all_requirements_met(self):
        decisions = {r['candidate_id']: 'met' for r in self.candidate['requirements']}
        clear = {**self.context, 'scope_verified': True, 'currency_verified': True,
                 'coverage_verified': True, 'critical_risks': 'clear'}
        for change in ({'critical_risks': 'open'}, {'coverage_verified': False}):
            result = self.evaluate(decisions, gate_context={**clear, **change})
            self.assertEqual(result['proposed_silver_gate']['status'], 'blocked')

    def test_unknown_risk_or_currency_cannot_pass_checklist(self):
        decisions = {r['candidate_id']: 'met' for r in self.candidate['requirements']}
        clear = {'scope_verified': True, 'currency_verified': True,
                 'coverage_verified': True, 'critical_risks': 'clear'}
        for change in ({'critical_risks': 'unknown'}, {'currency_verified': None}):
            result = self.evaluate(decisions, gate_context={**clear, **change})
            self.assertEqual(result['proposed_silver_gate']['status'], 'unresolved')

    def test_missing_or_negative_alternative_has_correct_gate_state(self):
        rule = self.profiles['profiles']['engineering']['silver_proposal']
        decisions = {i: 'met' for i in rule['all_of']}
        self.assertEqual(self.evaluate(decisions)['proposed_silver_gate']['status'], 'unresolved')
        decisions.update({i: 'not_met' for i in rule['any_of'][0]})
        self.assertEqual(self.evaluate(decisions)['proposed_silver_gate']['status'], 'blocked')

    def test_old_findings_implicit_na_and_missing_context_are_rejected(self):
        for bad in ({'AIQIF-C1.1.F1': 'met'}, {'LADDER-C1.1.F1': 'met'},
                    {'LADDER02-C1.1.F1': 'not_applicable'}):
            with self.assertRaises(ValueError):
                self.evaluate(bad)
        for context in ({}, {**self.context, 'coverage_verified': 1}):
            with self.assertRaises(ValueError):
                self.evaluate(gate_context=context)

    def test_missing_duplicate_mapping_or_invalid_profile_release_rejected(self):
        for change in ('missing', 'duplicate', 'profile'):
            candidate, profiles = copy.deepcopy(self.candidate), copy.deepcopy(self.profiles)
            if change == 'missing': candidate['requirements'].pop()
            if change == 'duplicate': candidate['requirements'][0] = candidate['requirements'][1]
            if change == 'profile': profiles['methodology'] = 'different'
            with self.assertRaises(ValueError):
                evaluate_candidate(candidate, profiles, {}, profile_id='iti', gate_context=self.context)

    def test_reproducibility_includes_profile_scope_and_rubric_and_no_mutation(self):
        before = copy.deepcopy((self.candidate, self.profiles, self.context))
        first = self.evaluate()
        self.assertEqual(first['input_hash'], self.evaluate()['input_hash'])
        self.assertNotEqual(first['input_hash'], self.evaluate(profile_id='iti')['input_hash'])
        self.assertNotEqual(first['input_hash'], self.evaluate(gate_context={**self.context, 'scope_verified': True})['input_hash'])
        self.candidate['requirements'][0]['requirement'] += ' revised'
        self.assertNotEqual(first['candidate_hash'], self.evaluate()['candidate_hash'])
        self.candidate = before[0]
        self.assertEqual((self.candidate, self.profiles, self.context), before)
