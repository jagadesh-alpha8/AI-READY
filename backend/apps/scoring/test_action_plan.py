"""Priority plan (capability/action_plan.py): ranking, prerequisites, projections and provisional tiers."""
from django.test import SimpleTestCase, override_settings

from .capability import action_plan
from .capability.engine import LEVELS, documented, release


def record(cid, credit=0.0, state=None, reason='Not established in the supplied passages.', parts=None):
    return {'condition_id': cid, 'credit': credit, 'state': state or ('met' if credit >= 1 else 'unknown'),
            'reason': reason, 'citations': [], 'parts': parts or []}


class TierTests(SimpleTestCase):
    def test_default_bands_on_the_final_score(self):
        self.assertEqual(action_plan.tier_for(59.9)['current'], None)
        self.assertEqual((action_plan.tier_for(59.9)['next'], action_plan.tier_for(59.9)['points_to_next']),
                         ('Silver', 0.1))
        self.assertEqual(action_plan.tier_for(60)['current'], 'Silver')
        self.assertEqual(action_plan.tier_for(75)['current'], 'Gold')
        self.assertEqual((action_plan.tier_for(85)['current'], action_plan.tier_for(85)['next']), ('Platinum', 'Diamond'))
        self.assertEqual((action_plan.tier_for(95)['current'], action_plan.tier_for(95)['next']), ('Diamond', None))
        self.assertTrue(action_plan.tier_for(10)['provisional'])

    @override_settings(CAPABILITY_PROVISIONAL_TIERS='Bronze:50, Silver:75, broken, Gold:x')
    def test_bands_come_from_settings(self):
        self.assertEqual([t['name'] for t in action_plan.tier_for(0)['thresholds']], ['Bronze', 'Silver'])
        self.assertEqual(action_plan.tier_for(60)['current'], 'Bronze')


class GapTests(SimpleTestCase):
    def test_the_gap_decides_the_action(self):
        self.assertEqual(action_plan.gap_of(record('X', 1.0)), 'strength')
        self.assertEqual(action_plan.gap_of(record('X', 0.25)), 'complete')
        self.assertEqual(action_plan.gap_of(record('X', 0.0)), 'establish')
        self.assertEqual(action_plan.gap_of(record('X', 0.0, state='conflicting')), 'reconcile')
        self.assertEqual(action_plan.gap_of(record('X', 0.0, reason='No readable source context. Capability is unknown.')),
                         'rerun')
        self.assertEqual(action_plan.gap_of({'condition_id': 'X', 'state': 'met', 'reason': 'ok'}), 'strength')


class PlanTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.ids = [c['id'] for i in self.rubric['indicators'] for c in i['conditions']]
        self.level = {c['id']: c['level'] for i in self.rubric['indicators'] for c in i['conditions']}
        self.indicator = {c['id']: i['code'] for i in self.rubric['indicators'] for c in i['conditions']}

    def test_short_plan_reaches_the_next_step_of_the_shown_score(self):
        plan = action_plan.build(self.rubric, [record(cid) for cid in self.ids])
        self.assertEqual((plan['score'], plan['target']), (0.0, 10))
        self.assertTrue(plan['reaches_target'])
        self.assertLessEqual(len(plan['actions']), action_plan.MAX_ACTIONS)
        self.assertLessEqual(len(plan['condition_ids']), action_plan.MAX_CONDITIONS)
        planned = {cid: 1.0 if cid in plan['condition_ids'] else 0.0 for cid in self.ids}
        self.assertEqual(plan['projected_score'], round(documented(planned, self.rubric)['overall'], 2))
        self.assertAlmostEqual(sum(a['score_gain'] for a in plan['actions']), plan['projected_score'], places=1)

    def test_provision_before_activity_before_outcomes(self):
        plan = action_plan.build(self.rubric, [record(cid) for cid in self.ids])
        chosen = set(plan['condition_ids'])
        for cid in chosen:
            level = LEVELS.index(self.level[cid])
            if level:
                before = [c for c in chosen if self.indicator[c] == self.indicator[cid]
                          and self.level[c] == LEVELS[level - 1]]
                self.assertTrue(before, f'{cid} planned without any {LEVELS[level - 1]} requirement in its indicator')

    def test_completing_partial_credit_comes_first_and_names_what_is_missing(self):
        target = next(cid for cid in self.ids if self.level[cid] == 'F')
        parts = [{'id': 'p1', 'credited_as': 'full', 'citations': []},
                 {'id': 'p2', 'credited_as': 'not_found', 'citations': []}]
        records = [record(cid) for cid in self.ids if cid != target] + [record(target, 0.25, parts=parts)]
        plan = action_plan.build(self.rubric, records)
        self.assertEqual(plan['condition_ids'][0], target)
        first = next(c for a in plan['actions'] for c in a['conditions'] if c['condition_id'] == target)
        self.assertEqual(first['gap'], 'complete')
        self.assertEqual(len(first['missing_parts']), 1)

    def test_strengths_are_listed_and_built_on(self):
        strong = [c['id'] for c in self.rubric['indicators'][0]['conditions'] if c['level'] == 'F']
        records = [record(cid, 1.0 if cid in strong else 0.0) for cid in self.ids]
        plan = action_plan.build(self.rubric, records)
        self.assertEqual({s['condition_id'] for s in plan['strengths']}, set(strong))
        self.assertTrue(set(strong).isdisjoint(plan['condition_ids']))
        same = [a for a in plan['actions'] if a['indicator'] == self.rubric['indicators'][0]['code']]
        if same:
            self.assertTrue(set(same[0]['builds_on']) & set(strong))

    def test_reruns_and_conflicts_stay_out_of_the_plan(self):
        rerun = self.ids[0]
        conflict = self.ids[1]
        records = [record(cid) for cid in self.ids[2:]] + [
            record(rerun, reason='No readable source context. Capability is unknown.'),
            record(conflict, state='conflicting')]
        plan = action_plan.build(self.rubric, records)
        self.assertNotIn(rerun, plan['condition_ids'])
        self.assertNotIn(conflict, plan['condition_ids'])
        totals = {k: sum(r[k] for r in plan['remaining']) for k in ('rerun', 'reconcile')}
        self.assertEqual(totals, {'rerun': 1, 'reconcile': 1})

    def test_full_score_needs_no_plan(self):
        plan = action_plan.build(self.rubric, [record(cid, 1.0) for cid in self.ids])
        self.assertEqual((plan['score'], plan['target'], plan['actions']), (100.0, None, []))
        self.assertEqual(plan['tier']['current'], 'Diamond')
