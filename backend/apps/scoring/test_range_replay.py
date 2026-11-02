"""Generic wide-range arithmetic tests; no institutional assessment data."""
import copy
from fractions import Fraction
from unittest import TestCase

from .capability.engine import assess, release
from .capability.experimental_ladder import compare_source_export


class RangeReplayTests(TestCase):
    def report(self):
        rubric = release()
        records = [{'condition_id': c['id'], 'state': 'unknown', 'reason': 'Unresolved evidence.',
                    'validation_issue': ''} for i in rubric['indicators'] for c in i['conditions']]
        by_id = {r['condition_id']: r for r in records}
        by_id['AIQIF-C1.1.F1']['state'] = 'met'
        by_id['AIQIF-C2.1.A1']['reason'] = 'Condition decision missing or duplicated.'
        by_id['AIQIF-C1.2.F1']['reason'] = 'Quote does not match a supplied source passage.'
        result = assess({r['condition_id']: r['state'] for r in records}, rubric)
        return {'rubric': rubric, 'assessment': {'records': records, 'result': result}}

    def test_one_positive_assertion_does_not_complete_its_companion_gate(self):
        result = compare_source_export(self.report())
        self.assertTrue(result['source_replay_matches_saved'])
        self.assertEqual(result['source_range_diagnostics']['decision_states']['unknown'], len(self.report()['assessment']['records']) - 1)
        self.assertTrue(result['candidate_retrieval_revalidation_required'])
        self.assertEqual(result['source_bounds'], {'lower': 0, 'upper': 100})
        self.assertEqual(result['source_range_diagnostics']['full_width_indicators'], 36)
        self.assertEqual(result['source_range_diagnostics']['foundation_states']['unknown'], 71)
        self.assertEqual(Fraction(result['independent_components']['components']['F']['lower']), Fraction(100, 72))
        project = next(i for i in result['per_indicator_arithmetic'] if i['indicator'] == 'AIQIF-C1.1')
        self.assertEqual(project['source_bounds']['lower'], 0)
        self.assertEqual(project['independent_components']['F']['lower'], '50')
        self.assertFalse(result['candidate_rubric_rescored'])

    def test_two_optimistic_validator_changes_leave_other_foundations_unresolved(self):
        report = self.report()
        before = copy.deepcopy(report)
        result = compare_source_export(report)
        counter = result['optimistic_validator_counterfactual']
        self.assertEqual(len(counter['changed_condition_ids']), 2)
        self.assertEqual(counter['source_bounds'], {'lower': 0, 'upper': 100})
        for stage, count in (('F', 2), ('A', 1), ('O', 0)):
            self.assertEqual(Fraction(counter['independent_components'][stage]['lower']), Fraction(100 * count, 72))
        self.assertEqual(report, before)

    def test_arbitrary_model_prose_is_not_counted_as_validator_failure(self):
        report = self.report()
        for record in report['assessment']['records']:
            record['reason'] = 'The model found no suitable evidence.'
        result = compare_source_export(report)
        self.assertEqual(result['optimistic_validator_counterfactual']['changed_condition_ids'], [])

    def test_counterfactual_does_not_overwrite_negative_findings(self):
        report = self.report()
        record = next(r for r in report['assessment']['records'] if r['condition_id'] == 'AIQIF-C1.2.F1')
        record['state'] = 'not_met'
        result = compare_source_export(report)
        self.assertNotIn(record['condition_id'], result['optimistic_validator_counterfactual']['changed_condition_ids'])
        self.assertEqual(result['source_range_diagnostics']['negative_decisions'], 1)
        self.assertFalse(result['source_replay_matches_saved'])
