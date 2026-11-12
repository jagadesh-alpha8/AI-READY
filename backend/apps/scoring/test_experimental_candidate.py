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
        self.candidate = json.loads((DOCS / 'ladder_candidate_v0_3.json').read_text())
        self.profiles = json.loads((DOCS / 'ladder_profiles_candidate_v0_2.json').read_text())
        self.context = {'scope_verified': None, 'currency_verified': None,
                        'coverage_verified': None, 'critical_risks': 'unknown', 'consequential_ai_use': None}

    def evaluate(self, decisions=None, **overrides):
        kwargs = dict(profile_id='engineering', gate_context=self.context)
        kwargs.update(overrides)
        return evaluate_candidate(self.candidate, self.profiles, decisions if decisions is not None else {}, **kwargs)

    def test_all_216_requirements_reviewed_with_fresh_identities(self):
        rows = self.candidate['requirements']
        self.assertEqual(len(rows), 216)
        self.assertEqual(len({r['candidate_id'] for r in rows}), 216)
        self.assertEqual({s: sum(r['stage'] == s for r in rows) for s in ('F', 'A', 'O')},
                         {'F': 72, 'A': 72, 'O': 72})
        self.assertTrue(all(r['re_adjudication_required'] and r['source_requirement']
                            and r['requirement'] and r['evidence_rule'] for r in rows))

    def test_seven_hand_adjudicated_acceptance_cases(self):
        cases = json.loads((DOCS / 'ladder_candidate_acceptance_cases_v0_3.json').read_text())['cases']
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
                 'coverage_verified': True, 'critical_risks': 'clear', 'consequential_ai_use': False}
        for change in ({'critical_risks': 'open'}, {'coverage_verified': False}):
            result = self.evaluate(decisions, gate_context={**clear, **change})
            self.assertEqual(result['proposed_silver_gate']['status'], 'blocked')

    def test_unknown_risk_or_currency_cannot_pass_checklist(self):
        decisions = {r['candidate_id']: 'met' for r in self.candidate['requirements']}
        clear = {'scope_verified': True, 'currency_verified': True,
                 'coverage_verified': True, 'critical_risks': 'clear', 'consequential_ai_use': False}
        for change in ({'critical_risks': 'unknown', 'consequential_ai_use': None}, {'currency_verified': None}):
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
                    {'LADDER02-C1.1.F1': 'met'},
                    {'LADDER03-C1.1.F1': 'not_applicable'}):
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

    def complete_gate(self):
        rule = self.profiles['profiles']['engineering']['silver_proposal']
        decisions = {i: 'met' for i in rule['all_of']}
        decisions[rule['any_of'][0][0]] = 'met'
        context = {'scope_verified': True, 'currency_verified': True,
                   'coverage_verified': True, 'critical_risks': 'clear',
                   'consequential_ai_use': False}
        return decisions, context

    def test_student_attainment_inventory_ownership_and_security_are_mandatory(self):
        decisions, context = self.complete_gate()
        for required in ('C5.1.O1', 'C2.3.F1', 'C2.3.F2', 'C2.3.A1', 'C8.1.F2', 'C6.3.A1'):
            missing = dict(decisions)
            missing.pop('LADDER03-' + required)
            self.assertEqual(self.evaluate(missing, gate_context=context)['proposed_silver_gate']['status'], 'unresolved')

    def test_consequential_use_cannot_silently_waive_oversight(self):
        decisions, context = self.complete_gate()
        self.assertEqual(self.evaluate(decisions, gate_context=context)['proposed_silver_gate']['status'], 'satisfied_for_review')
        for flag in (None, True):
            result = self.evaluate(decisions, gate_context={**context, 'consequential_ai_use': flag})
            self.assertEqual(result['proposed_silver_gate']['status'], 'unresolved')
        conditional = self.profiles['profiles']['engineering']['silver_proposal']['conditional_all_of']['consequential_ai_use']
        decisions.update({i: 'met' for i in conditional})
        context['consequential_ai_use'] = True
        self.assertEqual(self.evaluate(decisions, gate_context=context)['proposed_silver_gate']['status'], 'satisfied_for_review')
        decisions[conditional[0]] = 'not_met'
        self.assertEqual(self.evaluate(decisions, gate_context=context)['proposed_silver_gate']['status'], 'blocked')

    def test_group_changes_cannot_silently_change_weights(self):
        for key, value in (('credit_group', 'extra-budget'), ('indicator', 'AIQIF-C9.4')):
            candidate = copy.deepcopy(self.candidate)
            candidate['requirements'][0][key] = value
            with self.assertRaises(ValueError):
                evaluate_candidate(candidate, self.profiles, {}, profile_id='engineering', gate_context=self.context)

    def test_result_nested_lists_are_detached_from_input_profiles(self):
        before = copy.deepcopy(self.profiles)
        result = self.evaluate()
        result['proposed_silver_gate']['alternative_groups'][0]['ids'].append('mutation')
        result['proposed_silver_gate']['conditional_oversight']['ids'].append('mutation')
        result['proposed_silver_gate']['context']['scope_verified'] = True
        self.assertEqual(before, self.profiles)
        self.assertIsNone(self.context['scope_verified'])

    def test_malformed_structures_raise_value_error(self):
        good = [self.candidate, self.profiles, {}, 'engineering', self.context]
        for index, bad in ((0, []), (1, None), (2, []), (2, {'LADDER03-C1.1.F1': []}),
                           (3, []), (4, [])):
            args = list(good)
            args[index] = bad
            with self.assertRaises(ValueError):
                evaluate_candidate(*args[:3], profile_id=args[3], gate_context=args[4])
        for field, bad in (('requirements', None), ('requirements', [{}] * 216)):
            candidate = {**self.candidate, field: bad}
            with self.assertRaises(ValueError):
                evaluate_candidate(candidate, self.profiles, {}, profile_id='engineering', gate_context=self.context)

    def test_malformed_gate_definitions_and_obsolete_releases_rejected(self):
        for field, bad in (('all_of', 'LADDER03-C1.1.F1'), ('any_of', [None]),
                           ('conditional_all_of', {}), ('additional_gate_context', [])):
            profiles = copy.deepcopy(self.profiles)
            profiles['profiles']['engineering']['silver_proposal'][field] = bad
            with self.assertRaises(ValueError):
                evaluate_candidate(self.candidate, profiles, {}, profile_id='engineering', gate_context=self.context)
        old = json.loads((DOCS / 'ladder_candidate_v0_2.json').read_text())
        with self.assertRaises(ValueError):
            evaluate_candidate(old, self.profiles, {}, profile_id='engineering', gate_context=self.context)

    def test_context_rules_prevent_generic_digital_use_being_labelled_ai_activity(self):
        rows = {r['source_condition_id']: r for r in self.candidate['requirements']}
        self.assertIn('Generic digital use', rows['AIQIF-C1.4.A1']['context_rule'])
        self.assertEqual(rows['AIQIF-C4.2.O1']['construct'], 'observed_ai_activity')
        self.assertEqual(rows['AIQIF-C1.3.A1']['construct'], 'observed_enabling_practice')
        self.assertTrue(all(r['context_rule'] for r in rows.values()))

    def test_source_text_mapping_preserves_original_release(self):
        from .capability.engine import release
        source = {c['id']: c['text'] for i in release('AIQIF-CAP-0.2')['indicators'] for c in i['conditions']}
        self.assertEqual({r['source_condition_id']: r['source_requirement']
                          for r in self.candidate['requirements']}, source)
