"""Pure offline candidate tests; no database or model calls."""
import itertools
import json
from fractions import Fraction
from pathlib import Path
from unittest import TestCase

from .capability.experimental_ladder import component_bounds
from .capability.engine import assess, release


class IndependentComponentTests(TestCase):
    def run_case(self, decisions):
        return component_bounds([
            {'id': 'f1', 'stage': 'F'}, {'id': 'f2', 'stage': 'F'},
            {'id': 'a1', 'stage': 'A'}, {'id': 'o1', 'stage': 'O'},
        ], decisions, methodology_id='fixture-1')

    def test_partial_foundation_credit_without_badge_or_headline(self):
        result = self.run_case({'f1': 'met'})
        self.assertEqual(result['components']['F']['lower'], '50')
        self.assertEqual(result['components']['F']['upper'], '100')
        self.assertIsNone(result['headline_score'])
        self.assertEqual(result['badge_status'], 'not_assessed')

    def test_observed_activity_survives_missing_foundation(self):
        result = self.run_case({'f1': 'not_met', 'a1': 'met'})
        self.assertEqual(result['components']['A']['lower'], '100')
        self.assertEqual(result['components']['F']['lower'], '0')
        self.assertEqual(result['components']['F']['upper'], '50')

    def test_all_unknown_and_conflicting_retain_full_uncertainty(self):
        for decisions in ({}, {'f1': 'conflicting', 'f2': 'conflicting'}):
            result = self.run_case(decisions)['components']['F']
            self.assertEqual((result['lower'], result['upper']), ('0', '100'))
            self.assertEqual(result['resolved'], 0)

    def test_bounds_equal_enumerated_possible_worlds(self):
        for pair in itertools.product(('met', 'not_met', 'unknown', 'conflicting'), repeat=2):
            values = []
            choices = [[1] if s == 'met' else [0] if s == 'not_met' else [0, 1] for s in pair]
            for world in itertools.product(*choices):
                values.append(Fraction(100 * sum(world), 2))
            actual = self.run_case(dict(zip(('f1', 'f2'), pair)))['components']['F']
            self.assertEqual(Fraction(actual['lower']), min(values))
            self.assertEqual(Fraction(actual['upper']), max(values))

    def test_rejects_unknown_ids_states_and_duplicate_requirements(self):
        for bad in ({'f1': 'not_applicable'}, {'alien': 'met'}):
            with self.assertRaises(ValueError):
                self.run_case(bad)
        with self.assertRaises(ValueError):
            component_bounds([{'id': 'x', 'stage': 'F'}] * 2, {}, methodology_id='x')

    def test_input_identity_and_no_mutation(self):
        decisions = {'f1': 'met', 'a1': 'unknown'}
        a = self.run_case(decisions)
        b = self.run_case(dict(reversed(list(decisions.items()))))
        self.assertEqual(a['input_hash'], b['input_hash'])
        self.assertNotEqual(a['input_hash'], self.run_case({'f1': 'not_met'})['input_hash'])
        self.assertEqual(decisions, {'f1': 'met', 'a1': 'unknown'})

    def test_review_covers_exactly_72_sources_with_new_candidate_ids(self):
        root = Path(__file__).resolve().parents[3]
        candidate = json.loads((root / 'docs/capability/ladder_foundations_candidate_v0_1.json').read_text())
        rows = candidate['foundations']
        expected = {c['id'] for i in release('AIQIF-CAP-0.2')['indicators'] for c in i['conditions'] if c['level'] == 'F'}
        self.assertEqual(len(rows), 72)
        self.assertEqual({r['source_condition_id'] for r in rows}, expected)
        self.assertEqual(len({r['candidate_id'] for r in rows}), 72)
        self.assertTrue(all(r['re_adjudication_required'] for r in rows))
        self.assertTrue(all(r['candidate_id'] != r['source_condition_id'] for r in rows))

    def test_source_engine_is_unchanged_and_difference_is_explicit(self):
        rubric = release('AIQIF-CAP-0.2')
        item = rubric['indicators'][0]
        decision = {item['conditions'][0]['id']: 'met'}
        original = assess(decision, rubric)
        self.assertEqual(original['indicators'][0]['lower'], 0)
        candidate = component_bounds([
            {'id': c['id'], 'stage': c['level']} for c in item['conditions']
        ], decision, methodology_id='source-wording-arithmetic-only')
        self.assertEqual(candidate['components']['F']['lower'], '50')

    def test_source_comparison_rejects_missing_or_duplicate_decisions(self):
        from .capability.experimental_ladder import compare_source_export
        rubric = release('AIQIF-CAP-0.2')
        records = [{'condition_id': c['id'], 'state': 'unknown'}
                   for i in rubric['indicators'] for c in i['conditions']]
        report = {'rubric': rubric, 'assessment': {'records': records, 'result': assess({}, rubric)}}
        comparison = compare_source_export(report)
        self.assertTrue(comparison['source_replay_matches_saved'])
        self.assertFalse(comparison['candidate_rubric_rescored'])
        for broken in (records[:-1], records + [records[0]]):
            with self.assertRaises(ValueError):
                compare_source_export({'rubric': rubric, 'assessment': {'records': broken}})

    def test_malformed_shapes_fail_with_value_error(self):
        for requirements, decisions in ((None, {}), ([None], {}), ([{}], {}),
                                        ([{'id': 'x', 'stage': 'F'}], []),
                                        ([{'id': 'x', 'stage': 'F'}], {'x': []})):
            with self.assertRaises(ValueError):
                component_bounds(requirements, decisions, methodology_id='fixture')
