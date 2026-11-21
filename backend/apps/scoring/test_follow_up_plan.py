"""questions-0.2 and the depth reserve (21 Nov 2026), from the test 13 audit
(claude/ai-ready-follow-up-questions-audit.md): every key indicator asked about, questions spread across areas, plain
missing-evidence items in stage order, a share of credit held for depth and earned back by answers."""
from fractions import Fraction

from django.test import SimpleTestCase, TestCase, override_settings

from .capability import depth, reserve
from .capability.engine import documented, release
from .capability.layer2_service import already_counted, better_follow_up

QUOTE = 'The finance committee approved Rs 4 lakh for the AI lab on 12 June 2024, for 300 students in two departments.'


def records(credited, rubric=None):
    rubric = rubric or release()
    out = []
    for indicator in rubric['indicators']:
        for c in indicator['conditions']:
            credit = credited.get(c['id'], 0)
            out.append({'condition_id': c['id'], 'state': 'met' if credit == 1 else 'unknown', 'credit': credit,
                        'parts': [{'id': 'p1', 'credited_as': 'full' if credit else 'not_found',
                                   'citations': [{'source_id': 's1', 'quote': QUOTE}] if credit else []}]})
    return out


class Model:
    """Answers the per-indicator plan; behaviour per test."""

    def __init__(self, reply=None):
        self.calls, self.reply = [], reply

    def __call__(self, system, content, schema, name):
        import json
        payload = json.loads(content)
        self.calls.append(payload)
        if self.reply:
            return self.reply(payload)
        return {'answered': [], 'missing_items': [{'condition_id': r['condition_id'], 'text': 'a simple record of it'}
                                                  for r in payload['requirements_not_yet_shown']],
                'questions': [{'condition_id': r['condition_id'], 'dimension_ids': [d['id'] for d in r['dimensions']],
                               'text': 'How much was spent, who approved it and when? Please share the minutes.'}
                              for r in payload['credited_requirements']]}


class ReserveTests(SimpleTestCase):
    def test_factors(self):
        self.assertEqual(reserve.factor('evidenced', '0.25'), Fraction(3, 4))
        self.assertEqual(reserve.factor('substantiated', '0.25'), Fraction(7, 8))
        self.assertEqual(reserve.factor('strong', '0.25'), 1)
        self.assertEqual(reserve.factor('withdrawn', '0.25'), Fraction(3, 4))   # held for review, not zeroed
        self.assertEqual(reserve.factor('evidenced', '0'), 1)
        self.assertEqual(reserve.factor(None, None), 1)   # runs from before the reserve

    def test_the_headline_holds_the_share_and_answers_earn_it_back(self):
        rubric = release()
        code = rubric['indicators'][0]['code']
        ids = [c['id'] for c in rubric['indicators'][0]['conditions']]
        rows = reserve.stamp(records({ids[0]: 1, ids[1]: Fraction(1, 2)}, rubric), Fraction(1, 4))
        raw = documented({r['condition_id']: r['credit'] for r in rows}, rubric)['overall']
        held = reserve.summary(rows, rubric)
        self.assertEqual(held['evidence_score'], raw)
        self.assertAlmostEqual(held['score'], raw * 0.75, delta=0.011)
        self.assertEqual(held['earned_back_points'], 0)
        self.assertEqual(held['credited_requirements_by_level'], {'evidenced': 2, 'substantiated': 0, 'strong': 0})
        deeper = reserve.stamp([dict(r) for r in rows], Fraction(1, 4), {ids[0]: 'strong', ids[1]: 'withdrawn'})
        after = reserve.summary(deeper, rubric)
        self.assertGreater(after['earned_back_points'], 0)
        self.assertEqual(after['held_for_review'], [ids[1]])
        self.assertEqual({r['condition_id']: r['depth_level'] for r in deeper if r['credit']},
                         {ids[0]: 'strong', ids[1]: 'evidenced'})
        self.assertIn(code, ids[0])

    def test_runs_without_the_reserve_are_unchanged(self):
        rows = records({'AIQIF-C1.1.F1': 1})
        self.assertIsNone(reserve.summary(rows, release()))
        self.assertEqual(reserve.scored_credits(rows)['AIQIF-C1.1.F1'], 1)
        self.assertEqual(reserve.stamp(rows, Fraction(0)), rows)

    def test_follow_up_notes(self):
        row = {'credit': 1, 'depth_share': '1/4', 'depth_level': 'evidenced'}
        self.assertIn('held until your follow-up answers', reserve.follow_up_note(row))
        self.assertIn('all of the credit', reserve.follow_up_note({**row, 'depth_level': 'strong'}))
        self.assertIsNone(reserve.follow_up_note({**row, 'credit': 0}))
        self.assertIsNone(reserve.follow_up_note({'credit': 1}))

    @override_settings(DEPTH_CREDIT_MODE='reserve', DEPTH_CREDIT_SHARE='0.25')
    def test_frozen_policy(self):
        policy = reserve.frozen_policy()
        self.assertEqual((policy['mode'], policy['share']), ('reserve', '1/4'))
        self.assertEqual(reserve.run_share({'depth_policy': policy}), Fraction(1, 4))
        self.assertEqual(reserve.run_share({}), 0)

    @override_settings(DEPTH_CREDIT_MODE='', DEPTH_CREDIT_SHARE='0.25')
    def test_switched_off(self):
        self.assertEqual(reserve.frozen_policy()['mode'], 'none')


class PlanTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        # Equal full credit on the first requirement of every key indicator: test 13's tie, everywhere.
        self.firsts = [i['conditions'][0]['id'] for i in self.rubric['indicators']]
        self.rows = reserve.stamp(records({cid: 1 for cid in self.firsts}, self.rubric), Fraction(1, 4))

    def plan(self, model=None, **kwargs):
        return depth.plan_all(self.rows, self.rubric, model or Model(), share=Fraction(1, 4), **kwargs)

    def test_every_key_indicator_is_asked_about_and_nothing_is_cut(self):
        questions, notes, shown = self.plan()
        self.assertEqual({q['condition_ids'][0] for q in questions if q['kind'] == 'depth'}, set(self.firsts))
        self.assertEqual(sum(q['kind'] == 'missing' for q in questions), 36)
        self.assertEqual(len(questions), 72)
        self.assertEqual([q['rank'] for q in questions], list(range(1, 73)))
        self.assertIn('36 model calls', notes[0])

    def test_tied_questions_take_turns_across_areas(self):
        questions, _, _ = self.plan()
        depth_qs = [q for q in questions if q['kind'] == 'depth']
        self.assertEqual(len({q['area'] for q in depth_qs[:9]}), 9)   # nine areas, one each, before any repeats
        points = [q['points_at_stake'] for q in questions]
        self.assertEqual(points, sorted(points, reverse=True))

    def test_points_at_stake(self):
        questions, _, _ = self.plan()
        indicator = self.rubric['indicators'][0]
        depth_q = next(q for q in questions if q['condition_ids'] == [self.firsts[0]])
        self.assertEqual(depth_q['points_at_stake'],
                         float(round(Fraction(1, 4) * Fraction(str(indicator['weight_units'])) / 60, 2)))
        missing_q = next(q for q in questions if q['kind'] == 'missing' and q['indicator'] == indicator['code'])
        self.assertEqual(missing_q['points_at_stake'],
                         float(round(5 * Fraction(3, 4) * Fraction(str(indicator['weight_units'])) / 60, 2)))

    def test_missing_items_are_plain_and_in_stage_order(self):
        questions, _, _ = self.plan()
        level = {c['id']: c['level'] for i in self.rubric['indicators'] for c in i['conditions']}
        for q in questions:
            if q['kind'] == 'missing':
                stages = [level[c] for c in q['condition_ids']]
                self.assertEqual(stages, sorted(stages, key='FAO'.index))
                self.assertIn('1. A simple record of it', q['text'])
                self.assertNotIn('AIQIF', q['text'])

    def test_a_part_credited_requirement_is_also_a_missing_item(self):
        cid = self.rubric['indicators'][0]['conditions'][1]['id']
        rows = reserve.stamp(records({cid: Fraction(1, 2)}, self.rubric), Fraction(1, 4))
        model = Model()
        questions, _, _ = depth.plan_all(rows, self.rubric, model, share=Fraction(1, 4))
        missing_q = next(q for q in questions if q['kind'] == 'missing' and cid in q['condition_ids'])
        self.assertTrue(any(q['condition_ids'] == [cid] for q in questions if q['kind'] == 'depth'))
        sent = next(p for p in model.calls if p['credited_requirements'])
        self.assertTrue(next(r for r in sent['requirements_not_yet_shown'] if r['condition_id'] == cid)['shown_in_part'])
        self.assertIn(cid, missing_q['condition_ids'])

    def test_what_the_model_gets_wrong_falls_back_to_fixed_wording(self):
        def bad(payload):
            return {'answered': [{'condition_id': r['condition_id'], 'dimension_id': r['dimensions'][0]['id'],
                                  'evidence_quote': 'A quote that is not in the evidence at all.'}
                                 for r in payload['credited_requirements']],
                    'questions': [{'condition_id': r['condition_id'], 'dimension_ids': [r['dimensions'][0]['id']],
                                   'text': 'Under AIQIF-C1.1 rubric, give the score.'}
                                  for r in payload['credited_requirements']],
                    'missing_items': [{'condition_id': r['condition_id'], 'text': 'see rubric'}
                                      for r in payload['requirements_not_yet_shown']]}
        questions, notes, shown = self.plan(Model(bad))
        self.assertEqual(shown, [])   # an invented quote answers nothing
        depth_qs = [q for q in questions if q['kind'] == 'depth']
        self.assertEqual({q['condition_ids'][0] for q in depth_qs}, set(self.firsts))
        self.assertTrue(all(q.get('fixed_wording') for q in depth_qs))
        self.assertTrue(all('AIQIF' not in q['text'] for q in questions))
        self.assertTrue(any('fixed wording' in n for n in notes))

    def test_a_malformed_reply_or_the_call_limit_still_asks_everything(self):
        from apps.extraction.exceptions import AIResponseError

        def broken(payload):
            raise AIResponseError('not JSON')
        questions, notes, _ = self.plan(Model(broken))
        self.assertEqual(len(questions), 72)
        self.assertTrue(any('question model failed' in n for n in notes))
        model = Model()
        questions, notes, _ = self.plan(model, max_calls=5)
        self.assertEqual(len(model.calls), 5)
        self.assertEqual(len(questions), 72)
        self.assertTrue(any('past the limit of 5 model calls' in n for n in notes))

    def test_quotes_that_show_every_dimension_need_no_question(self):
        def shown_all(payload):
            return {'answered': [{'condition_id': r['condition_id'], 'dimension_id': d['id'], 'evidence_quote': QUOTE}
                                 for r in payload['credited_requirements'] for d in r['dimensions']],
                    'questions': [], 'missing_items': []}
        questions, _, shown = self.plan(Model(shown_all))
        self.assertEqual(sorted(shown), sorted(self.firsts))
        self.assertFalse([q for q in questions if q['kind'] == 'depth'])

    def test_a_fact_asked_once_is_not_asked_again(self):
        indicator = self.rubric['indicators'][2]   # AI Investment & Resource Planning: F1 and F2 share investment
        f1, f2 = indicator['conditions'][0]['id'], indicator['conditions'][1]['id']
        rows = reserve.stamp(records({f1: 1, f2: 1}, self.rubric), Fraction(1, 4))
        spec = depth.spec()
        shared = set(spec['indicators'][indicator['code']]['conditions'][f1]['dimensions']) & set(
            spec['indicators'][indicator['code']]['conditions'][f2]['dimensions'])
        self.assertTrue(shared)

        def once(declare):
            def reply(payload):
                asked, qs = {}, []
                for r in payload['credited_requirements']:
                    dims = [d['id'] for d in r['dimensions']]
                    for d in [d for d in dims if d in asked]:
                        if declare:
                            asked[d]['also_for'].append(r['condition_id'])
                    new = [d for d in dims if d not in asked]
                    if new:
                        q = {'condition_id': r['condition_id'], 'dimension_ids': new, 'also_for': [],
                             'text': 'How much was spent on the AI lab, and who approved it? Please share the minutes.'}
                        qs.append(q)
                        asked.update({d: q for d in new})
                return {'answered': [], 'questions': qs, 'missing_items': []}
            return reply
        questions, notes, _ = depth.plan_all(rows, self.rubric, Model(once(True)), share=Fraction(1, 4))
        f1_q = next(q for q in questions if q['kind'] == 'depth' and q['condition_ids'][0] == f1)
        self.assertEqual(f1_q['condition_ids'], [f1, f2])   # declared: counts for F2 too
        f2_dims = {d for q in questions if q['condition_ids'][0] == f2 for d in q['dimension_ids']}
        self.assertFalse(f2_dims & shared)   # not asked again for F2, and no fixed-wording repeat
        self.assertFalse([n for n in notes if f2 in n and 'fixed wording' in n and not n.endswith('item.')])
        # Points: each requirement's held credit split over the questions that ask about it.
        worth = Fraction(1, 4) * Fraction(str(indicator['weight_units'])) / 60
        total = sum(Fraction(str(q['points_at_stake'])) for q in questions if q['kind'] == 'depth'
                    and q['indicator'] == indicator['code'])
        self.assertAlmostEqual(float(total), float(2 * worth), delta=0.02)
        # Not declared: the overlap is not assumed; F2 gets its own (fixed-wording) question for the shared fact.
        questions, notes, _ = depth.plan_all(rows, self.rubric, Model(once(False)), share=Fraction(1, 4))
        self.assertEqual(next(q for q in questions if q['kind'] == 'depth' and q['condition_ids'][0] == f1)
                         ['condition_ids'], [f1])
        f2_dims = {d for q in questions if q['condition_ids'][0] == f2 for d in q['dimension_ids']}
        self.assertTrue(shared <= f2_dims)

    def test_what_counts_as_plain(self):
        self.assertTrue(depth._plain_enough('How did student test scores change after the AI tutoring pilot?'))
        self.assertTrue(depth._plain_enough('Which data points does the dashboard track for each department?'))
        for text in ('This would raise your score: please share the minutes.', 'Worth 2.5 points: share the minutes.',
                     'Under the rubric, which body approved the plan?', 'For AIQIF-C1.1, who approved the plan?',
                     'Too short?'):
            self.assertFalse(depth._plain_enough(text), text)

    def test_a_quote_must_say_something(self):
        def dash(payload):
            return {'answered': [{'condition_id': r['condition_id'], 'dimension_id': d['id'], 'evidence_quote': '...'}
                                 for r in payload['credited_requirements'] for d in r['dimensions']],
                    'questions': [], 'missing_items': []}
        _, _, shown = self.plan(Model(dash))
        self.assertEqual(shown, [])

    def test_max_questions_cuts_only_when_set(self):
        questions, notes, _ = self.plan(max_questions=10)
        self.assertEqual(len(questions), 10)
        self.assertTrue(any('left out by DEPTH_MAX_QUESTIONS=10' in n for n in notes))


class AnswerHandlingTests(TestCase):
    def test_an_attachment_already_read_is_said_to_be_counted(self):
        attached = [{'id': 'page-1', 'document_id': 'doc-1', 'text': 'The AI policy.'}]
        packet = [{'id': 'page-1', 'document_id': 'doc-1', 'text': 'The AI policy.'}]
        self.assertEqual(already_counted(attached, [], packet), [{'document_id': 'doc-1',
                                                                  'name': 'the document you attached'}])
        self.assertEqual(already_counted(attached, [{'document_id': 'doc-1', 'evidence_role': 'answer_attachment'}],
                                         packet), [])
        self.assertEqual(already_counted(attached, [], []), [])

    def test_a_follow_up_that_repeats_the_question_names_what_is_missing(self):
        asked = 'Which body approved the Strategic Plan, and on what date? Please share the minutes.'
        repeat = 'Which body formally approved the Strategic Plan, on what date, and could you share the minutes?'
        result = {'supported': False, 'dimensions': [{'dimension_id': 'authority', 'support': 'not_supported'}]}
        text = better_follow_up(repeat, asked, result, [], [{'id': 'authority', 'name': 'Authority'}])
        self.assertIn('does not yet show the authority', text)
        self.assertEqual(better_follow_up('Could you also say how many hours it ran?', asked, result, [], []),
                         'Could you also say how many hours it ran?')
        already = [{'document_id': 'd', 'name': 'Criteria 6 (a)'}]
        self.assertTrue(better_follow_up(None, asked, result, already, []).startswith('We had already read Criteria 6 (a)'))
        self.assertIsNone(better_follow_up(None, asked, result, already, [], first=False))


class RescoreTests(SimpleTestCase):
    def test_rescore_keeps_the_held_credit_summary_consistent(self):
        from .management.commands.capability_rescore import rescore
        rubric = release()
        rows = reserve.stamp(records({'AIQIF-C1.1.F1': 1}, rubric), Fraction(1, 4))
        report = {'rubric': rubric, 'assessment': {'records': rows, 'result': {'score': 99, 'documented': {}}}}
        out, _ = rescore(report)
        result = out['assessment']['result']
        self.assertEqual(result['score'], result['depth_reserve']['score'])
        self.assertEqual(result['documented']['overall'], result['score'])
        self.assertGreater(result['depth_reserve']['held_points'], 0)
