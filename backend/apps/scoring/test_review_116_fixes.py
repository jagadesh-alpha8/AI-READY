"""Fixes for the review of #116, #106, #111 and #115 (27 Nov 2026, claude/ai-ready-review-116-27-nov.md). No model
calls. Each test names the finding it covers."""
from fractions import Fraction

from django.test import SimpleTestCase, TestCase

from apps.evidence_map import learn

from .capability import layer2, part_judgment, reserve
from .capability.engine import release
from .capability.layer2_service import check_response, rejudge_credit, submit
from .models import DepthQuestion
from .test_layer2 import ANNEXURE, CERTIFICATE, NEW_QUOTE, Reply, record

CID = 'AIQIF-C1.1.F2'   # two parts, p1 the subject (test_credit_middle_step)
V4 = {'depth_share': '1/4', 'depth_min_credit': '5/8', 'depth_ramp': True}


def counted(credit, **extra):
    return Fraction(str(credit)) * reserve.record_factor({**V4, 'credit': credit, **extra})


class SmoothHoldTests(SimpleTestCase):
    """Finding 1, Stage 1 half: under v3 a credit of 0.625 counted 0.469 and 0.583 counted 0.583."""

    def test_counted_credit_always_rises_with_credit(self):
        self.assertEqual(reserve.VERSION, 'depth-reserve-v4')
        credits = [0.25, 0.5, 0.583, 0.625, 0.667, 0.75, 0.833, 1.0]
        values = [counted(c) for c in credits]
        self.assertEqual(values, sorted(values))
        self.assertEqual(counted(0.625), Fraction('0.625'))           # nothing held at the line
        self.assertEqual(counted(1.0), Fraction(3, 4))                # full credit holds what v3 held
        self.assertEqual(reserve.record_factor({**V4, 'credit': 1.0, 'depth_level': 'strong'}), 1)

    def test_v3_records_keep_their_step(self):
        v3 = {'depth_share': '1/4', 'depth_min_credit': '5/8', 'credit': 0.625}
        self.assertEqual(reserve.record_factor(v3), Fraction(3, 4))

    def test_new_runs_freeze_the_ramp(self):
        self.assertTrue(reserve.frozen_policy()['ramp'])
        self.assertTrue(reserve.run_ramp({'depth_policy': reserve.frozen_policy()}))
        self.assertFalse(reserve.run_ramp({'depth_policy': {'version': 'depth-reserve-v3', 'share': '0.25'}}))
        rows = reserve.stamp([{'condition_id': CID, 'credit': 1.0}], Fraction(1, 4), min_credit=Fraction(5, 8),
                             ramp=True)
        self.assertTrue(rows[0]['depth_ramp'])


class NoHoldAfterRejudgeTests(SimpleTestCase):
    """Finding 1, follow-up half (compact re-judge decision 5): a requirement a re-judge takes across 5/8 counts in
    full; one held at Stage 1 stays held."""

    def setUp(self):
        self.rubric = release()
        self.indicator = self.rubric['indicators'][0]
        self.code = self.indicator['code']
        self.cid = self.indicator['conditions'][0]['id']
        self.packets = {self.code: [{**ANNEXURE, 'text_offset': 0}]}
        self.new = [record(self.cid, 1, 'full', [{'source_id': 'att-1', 'quote': NEW_QUOTE}])]

    def test_a_rise_from_below_the_line_is_exempt(self):
        provisional = [{**record(self.cid, 0), **V4}]
        merged, audit = layer2.merge_new_evidence(provisional, self.new, self.packets)
        self.assertEqual(audit[0]['decision'], 'replaced')
        self.assertEqual(merged[0]['depth_exempt'], reserve.EXEMPT)
        self.assertEqual(reserve.record_factor({**merged[0], **V4}), 1)
        self.assertFalse(reserve.holds({**merged[0], **V4}))

    def test_a_requirement_held_at_stage_1_stays_held(self):
        provisional = [{**record(self.cid, 0.75), **V4}]
        provisional[0]['parts'][0].update(finding='related', credited_as='related')
        merged, _ = layer2.merge_new_evidence(provisional, self.new, self.packets)
        self.assertNotIn('depth_exempt', merged[0])
        self.assertLess(reserve.record_factor({**merged[0], **V4}), 1)

    def test_a_v3_run_is_unchanged(self):
        provisional = [{**record(self.cid, 0), 'depth_share': '1/4', 'depth_min_credit': '5/8'}]
        merged, _ = layer2.merge_new_evidence(provisional, self.new, self.packets)
        self.assertNotIn('depth_exempt', merged[0])


class PointedRiseTests(SimpleTestCase):
    """Finding 3: the every-pass guard held only when it was the second pass that missed."""

    def test_a_miss_in_the_first_pass_is_a_miss(self):
        pointer = [{'id': 'old', 'text': 'The packet already held this line about the AI workshop.'}]
        cite = [{'source_id': 'old', 'quote': 'The packet already held this line about the AI workshop.'}]
        # combine() fills citations from the second pass when the first found nothing.
        two = {'id': 'p2', 'finding': 'not_found', 'second_finding': 'full', 'citations': cite,
               'second_citations': cite}
        self.assertFalse(layer2.pointed_rise(two, pointer))
        self.assertFalse(layer2.pointed_rise({**two, 'third_finding': 'full', 'third_citations': cite}, pointer))
        both = {**two, 'finding': 'full'}
        self.assertTrue(layer2.pointed_rise(both, pointer))


class TypedAnswerSupportTests(TestCase):
    """Finding 2: an answer with no document was shown as "Supported by a document" through word-matched pointers."""

    def setUp(self):
        self.rubric = release()
        self.code = self.rubric['indicators'][0]['code']
        self.cid = self.rubric['indicators'][0]['conditions'][0]['id']
        self.question = DepthQuestion.objects.create(run_ref='run-typed', kind='missing', indicator_code=self.code,
                                                     condition_ids=[self.cid], text='We found nothing for this.',
                                                     rank=1, spec_version='x')

    def _check(self, answer, document_ids, pages):
        response = submit(self.question, answer=answer, document_ids=document_ids)
        packet = [{**w, 'text_offset': 0} for w in pages]
        check_response(response, Reply({}), attached=pages if document_ids else [], corpus=pages,
                       context=({self.cid: record(self.cid, 0)}, {self.code: packet}))
        response.refresh_from_db()
        return response

    def test_word_pointers_go_to_the_re_judge_but_do_not_make_it_supported(self):
        response = self._check('Dr Rao completed the IIT Madras machine learning certificate programme', [],
                               [ANNEXURE])
        self.assertFalse(response.supported)
        self.assertEqual(response.follow_up_text[:len('Please attach')], 'Please attach')
        self.assertEqual([w['evidence_role'] for w in response.windows], [layer2.HELD_ROLE])   # still re-judged

    def test_a_pointer_into_an_attached_document_is_supported(self):
        page = {**ANNEXURE, 'document_id': '00000000-0000-0000-0000-00000000000a'}
        response = self._check('It is in our self-study report, annexure 3.',
                               ['00000000-0000-0000-0000-00000000000a'], [page])
        self.assertTrue(response.supported)


class TieBreakCitationTests(SimpleTestCase):
    """Finding 6: a tie-broken part cites the passes that agree with its majority; finding 11: the reason."""

    def _passes(self, second_p2, third_p2, third_state='unknown'):
        a, b, c = ({'source_id': s, 'quote': 'q ' + s} for s in ('a', 'b', 'c'))

        def one(p2, cite, state, credit):
            return {'condition_id': CID, 'state': state, 'credit': credit, 'reason': state,
                    'parts': [{'id': 'p1', 'finding': 'full', 'credited_as': 'full', 'citations': [a]},
                              {'id': 'p2', 'finding': p2, 'credited_as': p2,
                               'citations': [cite] if p2 != 'not_found' else []}]}
        first = one('full', b, 'met', 1.0)
        second = one(second_p2, c, 'unknown', part_judgment.credit(one(second_p2, c, 'x', 0)['parts']))
        third = one(third_p2, c, third_state, part_judgment.credit(one(third_p2, c, 'x', 0)['parts']))
        merged = part_judgment.combine([first], [second])[0][0]
        return part_judgment.add_third(merged, third, first, second), (a, b, c)

    def test_the_outlier_page_is_not_the_parts_citation(self):
        record_, (a, b, c) = self._passes('related', 'related')
        p2 = record_['parts'][1]
        self.assertEqual(p2['citations'], [c])          # the two related passes, not the first pass's lone full
        self.assertEqual(p2['first_citations'], [b])    # kept for the per-pass guards
        self.assertNotIn(b, record_['citations'])

    def test_a_part_one_pass_credited_is_not_quoted(self):
        record_, (a, b, c) = self._passes('not_found', 'not_found', third_state='not_met')
        self.assertEqual(record_['parts'][1]['citations'], [])
        self.assertGreater(record_['credit'], 0)
        # The subject, which every pass credited, is what the record cites; the lone pass's page is not.
        self.assertEqual(record_['citations'], [a])

    def test_with_no_majority_anywhere_the_record_still_shows_its_basis(self):
        lone = [{'source_id': 'x', 'quote': 'q x'}]
        parts = lambda found: [{'id': 'p1', 'finding': found, 'credited_as': found,
                                'citations': lone if found == 'full' else []}]
        first = {'condition_id': 'AIQIF-C1.1.F1', 'state': 'met', 'credit': 1.0, 'reason': '', 'parts': parts('full')}
        miss = {**first, 'state': 'not_met', 'credit': 0.0, 'parts': parts('not_found')}
        merged = part_judgment.combine([first], [miss])[0][0]
        record_ = part_judgment.add_third(merged, miss, first, miss)
        self.assertEqual(record_['parts'][0]['citations'], [])
        self.assertEqual(record_['citations'], lone)

    def test_a_credited_disagreement_does_not_say_not_credited(self):
        record_, _ = self._passes('related', 'not_found', third_state='not_met')
        if record_['state'] == 'unknown':
            self.assertNotIn('Not credited', record_['reason'])
        self.assertIn('Credited at the mean', part_judgment.disagreement_reason(['met', 'unknown'], 0.75))
        self.assertIn('Not credited', part_judgment.disagreement_reason(['met', 'unknown'], 0))


class LearningTests(SimpleTestCase):
    """Finding 7: map learning learns only from parts credited in at least two passes."""

    def test_a_lone_pass_teaches_nothing(self):
        lone = {'condition_id': CID, 'credit': 0.17, 'parts': [
            {'id': 'p1', 'credited_as': 'full', 'second_credited_as': 'not_found', 'third_credited_as': 'not_found',
             'first_citations': [{'quote': 'x'}], 'citations': [], 'second_citations': [], 'third_citations': []}]}
        self.assertEqual(learn._cited(lone), [])
        two = {**lone, 'parts': [{**lone['parts'][0], 'third_credited_as': 'full',
                                  'third_citations': [{'quote': 'y'}]}]}
        self.assertEqual([c['quote'] for c, _ in learn._cited(two)], ['x', 'y'])
        single = {'condition_id': CID, 'credit': 1, 'parts': [{'id': 'p1', 'credited_as': 'full',
                                                               'citations': [{'quote': 'z'}]}]}
        self.assertEqual(len(learn._cited(single)), 1)   # a one-pass record: its only pass


class OwnRuleTests(TestCase):
    """Finding 9 / compact re-judge decision 4: an open follow-up on an older credit rule is re-judged on that rule."""

    def test_an_older_rule_is_accepted_and_kept(self):
        parts = [{'id': 'p1', 'credited_as': 'full'}, {'id': 'p2', 'credited_as': 'related'}]
        with part_judgment.under_rule('subject-cap-v1'):
            self.assertEqual(part_judgment.credit(parts), 0.25)
            self.assertEqual(part_judgment.metadata()['credit_rule'], 'subject-cap-v1')
            self.assertEqual(part_judgment.active_tie_break(), 'median-credit-of-three-v1')
            old_trace = {'indicator': 'X', 'judgment': part_judgment.metadata()}
        self.assertEqual(part_judgment.credit(parts), 0.5)
        records = [{'condition_id': CID, 'credit': 0.25, 'parts': parts}]
        self.assertEqual(layer2.check_export_rule(records, [old_trace]), 'subject-cap-v1')
        # Credit recorded under the new rule on an old-rule trace is refused: one score, one scale.
        with self.assertRaises(layer2.Layer2Error):
            layer2.check_export_rule([{**records[0], 'credit': 0.5}], [old_trace])
        new_trace = {'indicator': 'Y', 'judgment': part_judgment.metadata()}
        with self.assertRaises(layer2.Layer2Error):
            layer2.check_export_rule(records, [old_trace, new_trace])
        with self.assertRaises(layer2.Layer2Error):
            layer2.check_export_rule(records, [{'indicator': 'Z', 'judgment': {**old_trace['judgment'],
                                                                              'credit_rule': 'no-such-rule'}}])

    def test_the_re_judge_runs_under_the_exports_rule(self):
        rubric = release()
        code = rubric['indicators'][0]['code']
        cid = rubric['indicators'][0]['conditions'][0]['id']
        packet = [{**ANNEXURE, 'text_offset': 0}]
        with part_judgment.under_rule('subject-cap-v1'):
            judgment = part_judgment.metadata()
        export = {'run_id': 'run-old-rule', 'rubric': rubric, 'population': 'All', 'reference_period': '2025-26',
                  'assessment': {'records': [record(cid, 0)],
                                 'traces': [{'indicator': code, 'source_excerpts': packet, 'judgment': judgment}]}}
        seen = {}

        def judge(sources, **kwargs):
            seen['rule'] = part_judgment.active_rule()
            return {'records': [record(cid, 1, 'full', [{'source_id': 'att-1', 'quote': NEW_QUOTE}])], 'traces': []}
        routes = [{'indicator': code, 'conditions': [cid],
                   'windows': [layer2._window(CERTIFICATE, 0, len(CERTIFICATE['text']), 'answer_attachment')],
                   'documents': []}]
        result = rejudge_credit(export, service=None, evaluate_fn=judge, sources=packet + [CERTIFICATE],
                                routes=routes)
        self.assertEqual((seen['rule'], result['credit_rule']), ('subject-cap-v1', 'subject-cap-v1'))
        self.assertEqual(part_judgment.active_rule(), part_judgment.CREDIT_RULE)
