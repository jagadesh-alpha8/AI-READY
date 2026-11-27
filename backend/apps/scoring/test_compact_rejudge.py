"""The compact re-judge (capability/compact.py) and its replay harness (compact_replay.py). No model calls."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from .capability import compact, compact_replay, layer2, part_judgment
from .capability.engine import release
from .capability.layer2_service import rejudge_credit
from .models import RejudgeLook
from .test_layer2 import ANNEXURE, CANTEEN, CERTIFICATE, NEW_QUOTE, record

CID = 'AIQIF-C1.1.F2'
SPEC = part_judgment._load()[0]['conditions'][CID]['parts']


def page(pid, doc, number, text):
    return {'id': pid, 'document_id': doc, 'page_number': number, 'text': text}


class PageTests(SimpleTestCase):
    def test_only_identical_text_is_the_same_page(self):
        held = page('p1', 'd1', 1, 'The AI policy was approved  in 2024.\n')
        same = page('n1', 'd9', 1, ' The AI policy was approved in 2024. ')
        edited = page('n2', 'd9', 2, 'The AI policy was approved in 2024. It is reviewed every year.')
        self.assertEqual(compact.twins([same, edited], [held]), {'n1': 'p1', 'n2': 'n2'})

    def test_three_states_per_part(self):
        rec = {'condition_id': CID, 'parts': [
            {'id': 'p1', 'credited_as': 'full', 'citations': [{'source_id': 'a', 'quote': 'x'}]},
            {'id': 'p2', 'credited_as': 'not_found', 'citations': []}]}
        got = compact.states(rec, [{'id': 'a'}, {'id': 'b'}], ['a', 'b', 'c'])
        self.assertEqual(got['a'], {'p1': 'cited', 'p2': 'held'})       # cited for one part, held for the other
        self.assertEqual(got['b'], {'p1': 'held', 'p2': 'held'})
        self.assertEqual(got['c'], {'p1': 'never_reached', 'p2': 'never_reached'})
        cited_only = {'a': {'p1': 'cited'}}
        self.assertFalse(compact.needs_rejudge(cited_only, rec, typed_shown=True, identifies=True))
        related = {**rec, 'parts': [{**rec['parts'][0], 'credited_as': 'related', 'second_credited_as': 'related'}]}
        # Decision 2: cited only as partly shown, and the answer, shown to the judge, says what the document is.
        self.assertTrue(compact.needs_rejudge(cited_only, related, typed_shown=True, identifies=True))
        self.assertFalse(compact.needs_rejudge(cited_only, related, typed_shown=False, identifies=True))

    def test_named_pages(self):
        self.assertEqual(compact.named_pages('See page 12 and pp. 3-5 of the report'), {3, 4, 5, 12})
        self.assertEqual(compact.named_pages('We have 300 hours of training'), set())


class PacketTests(SimpleTestCase):
    def test_groups_in_order_and_whole_documents_when_they_fit(self):
        sent = [page('s1', 'd1', 1, 'Certificate of the AI workshop for faculty. ' * 5)]
        stage1 = [{'id': 'old', 'text': 'The plan names digital priorities. ' * 3, 'text_offset': 0}]
        rec = {'condition_id': CID, 'parts': [
            {'id': 'p1', 'credited_as': 'full', 'citations': [{'source_id': 'old', 'quote': 'names digital priorities'}]},
            {'id': 'p2', 'credited_as': 'not_found', 'citations': []}]}
        pointed = [{'id': 'held', 'text': 'A committee is named. ' * 20, 'text_offset': 0, 'evidence_role': 'answer_points_to'}]
        packet, pages = compact.build(CID, SPEC, rec, stage1, sent=sent, pointed=pointed, answers=['see the certificate'],
                                      tags_by_key={}, corpus=[])
        self.assertEqual([w['evidence_role'] for w in packet], ['sent_with_answer', 'pointed_by_college', 'cited_so_far'])
        self.assertEqual(pages['partial'], [])
        self.assertNotIn('keyword', ''.join(w['evidence_role'] for w in packet))

    def test_a_long_document_is_selected_and_the_named_page_comes_first(self):
        doc = [page(f's{n}', 'd1', n, f'Page {n} of the annual report about canteen menus. ' * 40) for n in range(1, 30)]
        doc[19]['text'] = 'Minutes: the AI committee is assigned responsibility for the digital priority. ' * 20
        packet, pages = compact.build(CID, SPEC, None, [], sent=doc, pointed=[], answers=['It is on page 7.'],
                                      tags_by_key={}, corpus=[], caps={'sent': 6000})
        self.assertEqual(packet[0]['id'], 's7')                       # the page the answer names
        self.assertIn('s20', pages['groups']['sent'])                 # then the page matching the parts' wording
        self.assertEqual(pages['partial'], ['d1'])
        self.assertLessEqual(sum(len(w['text']) for w in packet), 6000)

    def test_the_statement_is_beside_the_passages(self):
        block = compact.statement_block([('The charter is our AI policy.', True), ('For the library question.', False)])
        self.assertIn('Never quote', block['note'])
        self.assertEqual([s['written_for'] for s in block['statements']], ['this requirement', 'a different question'])
        self.assertIsNone(compact.statement_block([('  ', True)]))


class PerPassTests(SimpleTestCase):
    def setUp(self):
        self.stage1 = [{'id': 'old', 'text': 'The packet already held this line about the AI workshop.'}]
        self.current = {'condition_id': CID, 'parts': [
            {'id': 'p1', 'finding': 'full', 'credited_as': 'full', 'second_finding': 'full', 'second_credited_as': 'full',
             'citations': [{'source_id': 'old', 'quote': 'The packet already held this line'}],
             'second_citations': [{'source_id': 'old', 'quote': 'The packet already held this line'}]},
            {'id': 'p2', 'finding': 'not_found', 'credited_as': 'not_found', 'second_finding': 'not_found',
             'second_credited_as': 'not_found', 'citations': [], 'second_citations': []}]}

    def test_a_pass_rises_only_on_its_own_new_text(self):
        new = [{'source_id': 'att-1', 'quote': NEW_QUOTE}]
        old = [{'source_id': 'old', 'quote': 'The packet already held this line'}]
        twin = {'condition_id': CID, 'parts': [self.current['parts'][0], {
            'id': 'p2', 'finding': 'full', 'credited_as': 'full', 'second_finding': 'full', 'second_credited_as': 'full',
            'citations': new, 'second_citations': old}]}
        out = compact.per_pass(twin, self.current, self.stage1, [])
        p2 = out['parts'][1]
        self.assertEqual((p2['credited_as'], p2['second_credited_as']), ('full', 'not_found'))
        self.assertEqual(layer2._recredit(out['parts'], CID), 0.5)

    def test_pointed_text_needs_every_pass(self):
        old = [{'source_id': 'old', 'quote': 'The packet already held this line'}]
        both = {'condition_id': CID, 'parts': [self.current['parts'][0], {
            'id': 'p2', 'finding': 'full', 'credited_as': 'full', 'second_finding': 'full', 'second_credited_as': 'full',
            'citations': old, 'second_citations': old}]}
        self.assertEqual(compact.per_pass(both, self.current, self.stage1, self.stage1)['parts'][1]['second_credited_as'],
                         'full')
        one = {**both, 'parts': [both['parts'][0], {**both['parts'][1], 'second_credited_as': 'not_found',
                                                     'second_finding': 'not_found', 'second_citations': []}]}
        self.assertEqual(compact.per_pass(one, self.current, self.stage1, self.stage1)['parts'][1]['credited_as'],
                         'not_found')
        self.assertEqual(compact.split(one, ['old']), ['p2'])


class SettingsTests(TestCase):
    @override_settings(REJUDGE_PACKET='compact', REJUDGE_TYPED_ANSWER='shown', REJUDGE_OTHER_REQUIREMENTS=True)
    def test_description_follows_the_settings(self):
        lines = compact.description(compact.current_settings())['lines']
        self.assertIn('understand what the document is', lines[0])
        self.assertIn('count it there too', lines[3])
        off = compact.description({**compact.current_settings(), 'typed_answer': 'hidden', 'other_requirements': False})
        self.assertTrue(off['lines'][0].endswith('find the right page.'))
        self.assertEqual(off['lines'][3], 'We consider each document for the question it is attached to.')
        self.assertIsNone(compact.description({'packet': 'whole'}))

    def test_settings_are_frozen_per_run(self):
        from apps.institutions.models import Institution
        from apps.sprints.models import Sprint
        from .models import CapabilityRun
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='Synthetic College'))
        run = CapabilityRun.objects.create(sprint=sprint, inputs={}, inputs_hash='x')
        with override_settings(REJUDGE_PACKET='compact'):
            self.assertEqual(compact.frozen_settings(str(run.pk))['packet'], 'compact')
        self.assertEqual(compact.frozen_settings(str(run.pk))['packet'], 'compact')   # a release changes nothing
        self.assertEqual(compact.frozen_settings('not-in-this-database')['packet'], 'whole')


@override_settings(REJUDGE_PACKET='compact', REJUDGE_TYPED_ANSWER='shown')
class CompactRejudgeTests(TestCase):
    def setUp(self):
        self.rubric = release()
        self.indicator = self.rubric['indicators'][0]
        self.code = self.indicator['code']
        self.cids = [c['id'] for c in self.indicator['conditions']][:2]
        self.packet = [{**ANNEXURE, 'text_offset': 0}, {**CANTEEN, 'text_offset': 0}]
        self.export = {'run_id': 'run-compact', 'rubric': self.rubric, 'population': 'All',
                       'reference_period': '2025-26',
                       'assessment': {'records': [record(c, 0) for c in self.cids],
                                      'traces': [{'indicator': self.code, 'source_excerpts': self.packet,
                                                  'judgment': part_judgment.metadata()}]}}
        self.routes = [{'indicator': self.code, 'conditions': list(self.cids), 'windows': [],
                        'documents': ['doc-new'], 'kind': 'missing', 'from': 'response:r1',
                        'answer': 'The certificate from the Centre for Continuing Education.'}]
        self.calls = []

    def judge(self, sources, **kwargs):
        self.calls.append(kwargs)
        cid = kwargs['rubric']['indicators'][0]['conditions'][0]['id']
        return {'records': [record(cid, 1, 'full', [{'source_id': 'att-1', 'quote': NEW_QUOTE}])],
                'traces': [{'indicator': self.code, 'source_excerpts': kwargs['fixed_contexts'][self.code]}]}

    def run_it(self):
        with patch('apps.scoring.capability.layer2_service.run_sprint_id', return_value='s'), \
                patch('apps.scoring.capability.compact._upload_tags', return_value=({}, [], {})), \
                patch('apps.scoring.capability.layer2_service.run_sources', return_value=[ANNEXURE, CANTEEN]), \
                patch('apps.scoring.capability.layer2_service.document_sources',
                      return_value=([CERTIFICATE], True, [])):
            return rejudge_credit(self.export, service=None, evaluate_fn=self.judge, routes=self.routes)

    def test_one_requirement_per_request_with_the_statement(self):
        result = self.run_it()
        self.assertEqual(len(self.calls), 2)
        for call in self.calls:
            self.assertEqual([len(i['conditions']) for i in call['rubric']['indicators']], [1])
            packet = call['fixed_contexts'][self.code]
            self.assertEqual(packet[0]['evidence_role'], 'sent_with_answer')
            self.assertNotIn('page-9', [w['id'] for w in packet])      # the keyword fill is left out
            self.assertIn('college', call['statements'][self.code]['note'])
        self.assertEqual(result['compact']['requests'], 2)
        self.assertEqual({r['decision'] for r in result['merge']}, {'replaced'})
        lines = result['document_lines']['response:r1']
        self.assertTrue(any(line['kind'] == 'counted' for line in lines))
        self.assertTrue(all('staff' in line for line in lines))
        self.assertEqual(RejudgeLook.objects.filter(run_ref='run-compact').count(), 2)

    def test_the_same_pages_reuse_the_stored_look(self):
        first = self.run_it()
        self.calls.clear()
        again = self.run_it()
        self.assertEqual(self.calls, [])                                 # no re-roll
        self.assertEqual([r['final_credit'] for r in again['merge']], [r['final_credit'] for r in first['merge']])
        self.assertTrue(all(l['text'].startswith('We have already taken a second look')
                            for l in again['document_lines']['response:r1']))

    def test_an_unclean_reading_gets_one_fresh_look_when_sent_again(self):
        self.run_it()
        RejudgeLook.objects.update(flags={'split': True})
        self.routes.append({**self.routes[0], 'from': 'response:r2'})
        self.calls.clear()
        self.run_it()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(set(RejudgeLook.objects.values_list('fresh_looks', flat=True)), {1})
        self.routes.append({**self.routes[0], 'from': 'response:r3'})
        self.calls.clear()
        self.run_it()
        self.assertEqual(self.calls, [])                                 # at most one fresh look

    def test_staff_can_order_the_fresh_look(self):
        self.run_it()
        with self.assertRaises(ValueError):
            compact.order_fresh_look('run-compact', self.cids[0], '')
        self.assertEqual(compact.order_fresh_look('run-compact', self.cids[0], 'Page 3 was not read.'), 1)
        self.calls.clear()
        self.run_it()
        self.assertEqual(len(self.calls), 1)

    def test_whole_mode_is_unchanged(self):
        with override_settings(REJUDGE_PACKET='whole'):
            result = self.run_it()
        self.assertNotIn('compact', result)
        self.assertEqual(result['follow_up_settings']['packet'], 'whole')


class ReplayTests(SimpleTestCase):
    def test_marks_and_the_template_answer(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write('#D0=Report.pdf\n1|d|C1.1.F2|D0|7\n2|n|C1.1.F2|D0|9\n3|s|C1.4|D0|2\n')
        self.assertEqual(compact_replay.load_marks(f.name), [('AIQIF-C1.1.F2', 'Report.pdf', 7, 'direct'),
                                                            ('AIQIF-C1.1.F2', 'Report.pdf', 9, 'not_evidence')])
        self.assertTrue(compact_replay.template_answer(CID).startswith('This page shows that a digital'))

    def test_test5_counts_selection(self):
        doc = [{'id': f's{n}', 'document_id': 'd', 'page_number': n, 'filename': 'Report.pdf',
                'text': f'Page {n} about canteen menus and timetables. ' * 60} for n in range(1, 40)]
        doc[30]['text'] = 'A digital priority is identified and the AI committee is assigned responsibility. ' * 20
        export = {'assessment': {'records': []}}
        out = compact_replay.test5(export, doc, [(CID, 'Report.pdf', 31, 'direct')], caps=(12000, 40000))
        self.assertEqual(out['counts']['12000'].get('direct_selected'), 1)


class LinesShownTests(SimpleTestCase):
    def test_a_college_sees_the_line_and_staff_the_detail(self):
        from .capability.layer2_views import _lines
        rows = [{'document_id': 'd', 'requirement': CID, 'kind': 'read_again', 'text': 'Read again.',
                 'staff': {'page_states': {}}}]
        self.assertNotIn('staff', _lines(rows, False)[0])
        self.assertIn('staff', _lines(rows, True)[0])


class LoweringLineTests(SimpleTestCase):
    def test_a_lowering_says_where_what_and_from_which_page(self):
        plan = {'page_numbers': {'new': 4, 'old': 12}, 'files': {'old': 'SSR.pdf'}, 'page_documents': {},
                'previous_parts': [{'id': 'p2', 'citations': [{'source_id': 'old', 'quote': 'x'}]}]}
        row = {'decision': 'lowered', 'previous_credit': 0.5, 'lowered_parts': ['p2'],
               'contradicting_quotes': [{'part': 'p2', 'source_id': 'new', 'quote': 'y'}]}
        out = compact.lines({'kind': 'missing'}, CID, asked=True, audit_row=row,
                            final_record={'parts': [{'id': 'p1', 'credited_as': 'full'},
                                                    {'id': 'p2', 'credited_as': 'contradicted'}]},
                            documents=['d'], names={'d': 'Minutes.pdf'}, plan=plan, unreadable=[], typed_shown=False)
        self.assertEqual(out[0]['kind'], 'lowered')
        self.assertIn('Minutes.pdf (page 4)', out[0]['text'])
        self.assertIn('50% from page 12 of SSR.pdf', out[0]['text'])
        self.assertIn('send the document that settles it', out[0]['text'])
