"""Regression coverage for missing same-page evidence and unhelpful sparse plans."""
from copy import deepcopy
from unittest import TestCase

from .capability.engine import release, assess
from .capability.evaluation import select_context, validate_decisions
from .capability.foundation_plan import build_foundation_plan


class WindowCoverageTests(TestCase):
    def setUp(self):
        self.item = {'code': 'synthetic', 'name': 'Synthetic', 'scoring_mode': 'independent_conditions',
                     'conditions': [{'id': 'a', 'text': 'computing provision computers infrastructure capacity'},
                                    {'id': 'b', 'text': 'measured student competency attainment outcomes improved'}]}
        self.early = 'Computing provision computers infrastructure capacity is documented.'
        self.late = 'Measured student competency attainment outcomes improved after review.'
        self.source = {'id': 'page', 'text': self.early + (' irrelevant spacer.' * 800) + self.late}

    def test_different_requirement_windows_on_one_page_survive_selection_and_validation(self):
        selected = select_context(self.item, [self.source])
        self.assertTrue(any(self.early in w['text'] for w in selected))
        self.assertTrue(any(self.late in w['text'] for w in selected))
        self.assertLessEqual(sum(len(w['text']) for w in selected), 18000)
        self.assertGreater(len(selected), 1)
        for w in selected:
            self.assertEqual(w['text'], self.source['text'][w['text_offset']:w['text_offset'] + len(w['text'])])
        response = {'conditions': [dict(condition_id=cid, state='met', reason='Supported for the dated scope.',
            scope_supported=True, period_supported=True, citations=[{'source_id': 'page', 'quote': quote}])
            for cid, quote in [('a', self.early), ('b', self.late)]]}
        self.assertTrue(all(r['state'] == 'met' for r in validate_decisions(self.item, response, selected)))
        self.assertTrue(all(r['state'] == 'met' for r in validate_decisions(self.item, response, list(reversed(selected)))))

    def test_quotes_cannot_be_joined_across_omitted_gaps(self):
        windows = [{'id': 'page', 'text': self.early}, {'id': 'page', 'text': self.late}]
        response = {'conditions': [dict(condition_id='a', state='met', reason='Claim', scope_supported=True,
            period_supported=True, citations=[{'source_id': 'page', 'quote': self.early + ' ' + self.late}])]}
        rows = validate_decisions(self.item, response, windows)
        self.assertEqual(next(r for r in rows if r['condition_id'] == 'a')['state'], 'unknown')


class FoundationPlanTests(TestCase):
    def setUp(self):
        self.rubric = release()
        self.records = [{'condition_id': c['id'], 'state': 'unknown', 'reason': 'Not established.', 'citations': []}
                        for i in self.rubric['indicators'] for c in i['conditions']]

    def plan(self):
        return build_foundation_plan(self.rubric, self.records,
                                     assess({r['condition_id']: r['state'] for r in self.records}, self.rubric))

    def test_unrestricted_baseline_is_flagged_and_does_not_claim_a_level(self):
        plan = self.plan()
        self.assertEqual(plan['baseline']['status'], 'needs_evidence_review')
        self.assertFalse(plan['achievement_awarded'])
        self.assertEqual(plan['current_level'], 'not_verified')
        self.assertEqual(len(plan['goals']), 6)
        self.assertLessEqual(len(plan['review_questions']), 25)
        self.assertTrue(all(g['conditional'] and not g['automatic_points'] for g in plan['goals']))
        self.assertGreater(plan['other_unresolved_requirements'], 0)

    def test_verified_strengths_are_grounded_and_not_repeated_as_missing(self):
        record = next(r for r in self.records if r['condition_id'] == 'AIQIF-C6.1.F1')
        record.update(state='met', reason='The dated report establishes computing access for learners.',
                      citations=[{'source_id': 'synthetic', 'quote': 'Learners have access to the institutional computers.'}])
        before = deepcopy(self.records)
        plan = self.plan()
        self.assertEqual(plan['baseline']['status'], 'partially_established')
        self.assertTrue(any(g['existing_strengths'] for g in plan['goals']))
        self.assertTrue(all(record['condition_id'] not in g['target_condition_ids'] for g in plan['goals']))
        self.assertEqual(plan['existing_strengths'][0]['basis'], record['citations'])
        self.assertEqual(self.records, before)

    def test_same_remaining_outcomes_at_every_pace_and_no_invented_cost(self):
        plan = self.plan()
        expected = {g['id'] for g in plan['goals']}
        for route in plan['routes']:
            self.assertEqual(set(route['outcomes']), expected)
            self.assertEqual({key for batch in route['batches'] for key in batch}, expected)
            self.assertIsNone(route['cost'])
        self.assertNotEqual(plan['routes'][0]['batches'], plan['routes'][-1]['batches'])

    def test_verified_goals_are_removed_from_routes_without_claiming_achievement(self):
        for record in self.records:
            record['state'] = 'met'
        plan = self.plan()
        self.assertEqual(plan['goals'], [])
        self.assertTrue(all(not route['outcomes'] for route in plan['routes']))
        self.assertFalse(plan['achievement_awarded'])

    def test_explicit_negatives_are_not_mistaken_for_an_unassessed_baseline(self):
        for record in self.records:
            record['state'] = 'not_met'
        plan = self.plan()
        self.assertEqual(plan['baseline']['status'], 'resolved')
        self.assertTrue(all(g['status'] == 'documented_development_need' for g in plan['goals']))

class SamePageConflictTests(TestCase):
    def test_distinct_grounded_same_page_claims_can_be_recorded_as_conflicting(self):
        item = {'conditions': [{'id': 'a'}]}
        quotes = ['The same cohort had ten active computers in this period.',
                  'The same cohort had twenty active computers in this period.']
        row = dict(condition_id='a', state='conflicting', reason='Incompatible values in the same scoped period.',
                   scope_supported=True, period_supported=True,
                   citations=[{'source_id': 'p', 'quote': q} for q in quotes])
        sources = [{'id': 'p', 'text': q} for q in quotes]
        self.assertEqual(validate_decisions(item, {'conditions': [row]}, sources)[0]['state'], 'conflicting')
        row['scope_supported'] = False
        self.assertEqual(validate_decisions(item, {'conditions': [row]}, sources)[0]['state'], 'unknown')
        row['scope_supported'] = True
        row['citations'][1] = row['citations'][0]
        self.assertEqual(validate_decisions(item, {'conditions': [row]}, sources)[0]['state'], 'unknown')

class PublishedEvidencePathTests(TestCase):
    def test_late_skill_evidence_can_move_an_otherwise_all_unknown_assessment(self):
        import json
        from .capability.evaluation import evaluate
        quote = 'During 2024-25 at Synthetic College, an assessed role-relevant task demonstrated a faculty AI skill in lesson review.'
        introduction = 'A faculty AI learning offer targets an identified academic role: this is a proposal awaiting approval, not a delivered offer. '
        source = {'id': 'long-page', 'text': introduction + ('unrelated filler. ' * 800) + quote}
        class EvidenceReader:
            def extract_structured_data(self, **kwargs):
                payload = json.loads(kwargs['user_content'])
                available = any(quote in s['text'] for s in payload['sources'])
                rows = []
                for c in payload['indicator']['conditions']:
                    met = c['id'] == 'AIQIF-C4.2.A1' and available
                    rows.append(dict(condition_id=c['id'], state='met' if met else 'unknown',
                        reason='The scoped assessment record establishes this skill.' if met else 'Not established by the selected evidence.',
                        scope_supported=met, period_supported=met,
                        citations=[{'source_id': 'long-page', 'quote': quote}] if met else []))
                return {'conditions': rows}
        evaluated = evaluate([source], service=EvidenceReader(), population='Faculty at Synthetic College', reference_period='2024-25')
        result = assess(evaluated['decisions'])
        self.assertEqual(evaluated['decisions']['AIQIF-C4.2.A1'], 'met')
        self.assertGreater(result['lower'], 0)
        indicator = next(i for i in result['indicators'] if i['code'] == 'AIQIF-C4.2')
        self.assertEqual(indicator['lower'], 16.67)


class StrengthGroundingTests(TestCase):
    def test_unknown_check_can_reuse_verified_asset_but_cannot_become_development(self):
        from .capability.recommendations import validate_advice
        basis = {'source_id': 'synthetic-page', 'quote': 'Faculty have access to the computing facility.'}
        action = {'id': 'pending', 'operation': 'gather_evidence', 'type': 'supply_evidence', 'citations': []}
        row = dict(condition_id='pending', operation='gather_evidence',
                   steps=['Check the documented facility against the named introductory workload.'],
                   suggested_role='IT lead (suggested)', effort='unknown', dependencies=[],
                   completion_evidence='A scoped technical suitability review.', basis=[basis])
        assets = [{'basis': [basis]}]
        self.assertEqual(validate_advice({'advice': [row]}, [action], assets)[0]['operation'], 'gather_evidence')
        with self.assertRaises(ValueError):
            validate_advice({'advice': [row]}, [action])
        with self.assertRaises(ValueError):
            validate_advice({'advice': [{**row, 'operation': 'develop_and_verify'}]}, [action], assets)
        with self.assertRaises(ValueError):
            validate_advice({'advice': [{**row, 'basis': [{'source_id': 'forged', 'quote': 'invented'}]}]}, [action], assets)
