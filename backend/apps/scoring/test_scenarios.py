from copy import deepcopy
from django.test import SimpleTestCase
from .capability.engine import release, assess
from .capability.scenarios import evaluate_plan


class ScenarioTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.ids = [c['id'] for c in self.rubric['indicators'][0]['conditions']]
        self.base = {c['id']: 'unknown' for i in self.rubric['indicators'] for c in i['conditions']}

    def mapping(self, cid):
        return dict(condition_id=cid, state='met', phase='implementation', coverage='complete',
            scope_compatible=True, assumptions=['Completed and demonstrated in the recorded scope'], kind='development', action_id='a1')

    def test_coupled_unknown_delta_not_endpoint_subtraction(self):
        before = deepcopy(self.base)
        result = evaluate_plan(self.base, [self.mapping(cid) for cid in self.ids[:2]], self.rubric)
        scenario = result['scenarios']['implementation']
        self.assertGreater(scenario['result']['lower'], 0)
        self.assertEqual(scenario['paired_change']['lower'], 0)
        self.assertGreater(scenario['paired_change']['upper'], 0)
        self.assertEqual(self.base, before)
        self.assertFalse(result['actual_assessment_changed'])

    def test_prerequisites_and_results_separation(self):
        self.base[self.ids[0]] = 'not_met'
        result = evaluate_plan(self.base, [self.mapping(cid) for cid in self.ids[1:]], self.rubric)
        for phase in result['scenarios'].values():
            self.assertEqual(phase['result']['indicators'][0]['lower_level'], 0)
        self.assertNotIn(self.ids[-1], result['scenarios']['implementation']['overlay'])
        self.assertIn(self.ids[-1], result['scenarios']['results']['overlay'])

    def test_duplicate_targets_no_duplicate_credit(self):
        m = self.mapping(self.ids[0])
        once = evaluate_plan(self.base, [m], self.rubric)
        twice = evaluate_plan(self.base, [m, {**m, 'action_id': 'a2'}], self.rubric)
        self.assertEqual(once['scenarios'], twice['scenarios'])
        self.assertEqual(len(twice['accepted']), 1)
        self.assertEqual(twice['accepted'][0]['action_ids'], ['a1', 'a2'])

    def test_partial_clarification_conflicts_and_invalid_ids(self):
        m = self.mapping(self.ids[0])
        for change in [{'coverage': 'partial'}, {'scope_compatible': False}, {'condition_id': 'fake'},
                       {'kind': 'evidence_clarification'}, {'assumptions': []}]:
            result = evaluate_plan(self.base, [{**m, **change}], self.rubric)
            self.assertFalse(result['accepted'])
            self.assertTrue(result['rejected'])
        self.base[self.ids[0]] = 'conflicting'
        result = evaluate_plan(self.base, [m], self.rubric)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['scenarios']['results']['result'], assess(self.base, self.rubric))

    def test_withdrawal_can_reduce_exact_score(self):
        self.base = {k: 'met' for k in self.base}
        m = {**self.mapping(self.ids[0]), 'kind': 'withdrawal', 'state': 'not_met'}
        result = evaluate_plan(self.base, [m], self.rubric)
        delta = result['scenarios']['implementation']['paired_change']
        self.assertLess(delta['upper'], 0)
        self.assertEqual(delta['lower'], delta['upper'])
        self.assertEqual(result['baseline']['exact_score'], 100)

    def test_contradictions_and_wrong_engine_fail_closed(self):
        m = self.mapping(self.ids[0])
        result = evaluate_plan(self.base, [m, {**m, 'kind': 'withdrawal', 'state': 'not_met'}], self.rubric)
        self.assertFalse(result['accepted'])
        with self.assertRaises(ValueError):
            evaluate_plan(self.base, [], self.rubric, engine_version='new')
