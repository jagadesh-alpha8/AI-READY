"""Second assessment layer (capability/layer2.py, layer2_service.py, layer2_views.py): skeleton tests with stand-in
models. No provider calls."""
import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from .capability import depth, evaluation, layer2, part_judgment
from .capability.engine import release
from .capability.layer2 import Layer2Error
from .capability.layer2_service import (add_evidence, check_additional, check_pending, check_response,
                                        credit_routes, document_sources, next_item, rejudge_credit, submit)
from .capability.layer2_views import flag
from .models import AdditionalEvidence, DepthQuestion, DepthResponse

FILLER = ' The record was kept by the department office and countersigned by the head of the institution.'
CERTIFICATE = {'id': 'att-1', 'document_id': 'doc-new', 'page_number': 1,
               'text': 'Certificate of completion. Certificate Programme in Machine Learning, IIT Madras, 2025.'
                       ' Issued by the Centre for Continuing Education after the final assessment and project review.'}
ANNEXURE = {'id': 'page-7', 'document_id': 'doc-ssr', 'page_number': 7,
            'text': 'Annexure 3. Dr Rao completed the Certificate Programme in Machine Learning at IIT Madras.'
                    ' The faculty development cell keeps the attendance sheets and signed feedback forms on file.'}
CANTEEN = {'id': 'page-9', 'document_id': 'doc-ssr', 'page_number': 9,
           'text': 'Canteen menu and library opening times for the semester.' + FILLER}
ANSWER = 'Our faculty completed the Certificate Programme in Machine Learning with IIT Madras.'
# Only in the certificate: the programme's name alone is also in the annexure, so a quote of it is not new.
NEW_QUOTE = 'Issued by the Centre for Continuing Education'


class Reply:
    """A stand-in model that returns a fixed response and records its calls."""
    model_name = 'stand-in'

    def __init__(self, response):
        self.response, self.calls = response, []

    def __call__(self, system_prompt, user_content, response_schema, schema_name):
        self.calls.append((schema_name, json.loads(user_content), response_schema))
        return self.response


def spec_condition():
    spec = depth.spec()
    for code, indicator in spec['indicators'].items():
        for cid in indicator['conditions']:
            dims = depth._condition_dimensions(spec, cid)[1]
            if len(dims) >= 2:
                return spec, code, cid, dims
    raise AssertionError('No condition with two dimensions in the depth spec.')


class SearchTests(SimpleTestCase):
    def test_small_attachment_whole_then_corpus_by_the_answer(self):
        windows = layer2.search_with_answer(ANSWER, [CERTIFICATE], [ANNEXURE, CANTEEN])
        self.assertEqual(windows[0]['evidence_role'], 'answer_attachment')
        self.assertEqual(windows[0]['text'], CERTIFICATE['text'])
        self.assertEqual([w['id'] for w in windows if w['evidence_role'] == 'answer_search'], ['page-7'])

    def test_text_already_in_the_packet_is_not_sent_again(self):
        packet = [{**ANNEXURE, 'text_offset': 0}]
        windows = layer2.search_with_answer(ANSWER, [], [ANNEXURE, CANTEEN], packet=packet)
        self.assertEqual(windows, [])

    def test_no_answer_text_searches_only_the_attachment(self):
        windows = layer2.search_with_answer('', [CERTIFICATE], [ANNEXURE])
        self.assertEqual([w['id'] for w in windows], ['att-1'])

    def test_large_attachment_is_ranked_and_bounded(self):
        big = {**CERTIFICATE, 'text': ('Unrelated minutes of the sports committee meeting.\n' * 150)
               + CERTIFICATE['text'] + '\n' + ('Unrelated minutes of the sports committee meeting.\n' * 150)}
        windows = layer2.search_with_answer(ANSWER, [big], [], attachment_limit=1500)
        self.assertTrue(windows)
        self.assertLessEqual(sum(len(w['text']) for w in windows), 1500)
        self.assertTrue(any('Certificate Programme in Machine Learning' in w['text'] for w in windows))


    def test_a_large_attachment_does_not_crowd_out_the_corpus(self):
        bulky = {**CERTIFICATE, 'text': CERTIFICATE['text'] + ('\nAttendance register row.' * 280)}
        self.assertLessEqual(len(bulky['text']), layer2.ATTACHMENT_CHARS)
        windows = layer2.search_with_answer(ANSWER, [bulky], [ANNEXURE])
        self.assertEqual([w['id'] for w in windows], ['att-1', 'page-7'])

    def test_text_repeated_in_another_document_is_taken_once(self):
        restated = {**ANNEXURE, 'id': 'aqar-3', 'document_id': 'doc-aqar'}
        windows = layer2.search_with_answer(ANSWER, [], [ANNEXURE, restated, CANTEEN])
        self.assertEqual(len(windows), 1)

    def test_pages_extraction_tagged_join_whole(self):
        windows = layer2.page_windows([CERTIFICATE, ANNEXURE], {('doc-new', 1)})
        self.assertEqual([(w['id'], w['evidence_role']) for w in windows], [('att-1', 'extraction_tag')])


class CheckTests(SimpleTestCase):
    dims = [{'id': 'coverage', 'name': 'Coverage', 'ask': 'How many took part?'},
            {'id': 'intensity', 'name': 'Intensity', 'ask': 'How many hours?'}]
    windows = [layer2._window(CERTIFICATE, 0, len(CERTIFICATE['text']), 'answer_attachment')]

    def test_nothing_found_means_no_call_and_a_request_for_a_document(self):
        model = Reply({})
        result = layer2.check_answer('Q?', ANSWER, [], self.dims, model)
        self.assertFalse(model.calls)
        self.assertFalse(result['supported'])
        self.assertEqual(result['follow_up'], layer2.NO_SUPPORT_FOLLOW_UP)
        self.assertEqual({d['support'] for d in result['dimensions']}, {'not_supported'})

    def test_output_is_checked_not_trusted(self):
        model = Reply({'dimensions': [
            {'dimension_id': 'coverage', 'support': 'supported', 'passage_ids': ['p1'], 'note': ''},
            {'dimension_id': 'intensity', 'support': 'partly', 'passage_ids': [], 'note': 'hours not shown'},
            {'dimension_id': 'bogus', 'support': 'supported', 'passage_ids': ['p1'], 'note': ''}],
            'follow_up': 'Which document shows the hours?'})
        result = layer2.check_answer('Q?', ANSWER, self.windows, self.dims, model)
        by_id = {d['dimension_id']: d for d in result['dimensions']}
        self.assertEqual(set(by_id), {'coverage', 'intensity'})
        self.assertEqual(by_id['coverage']['support'], 'supported')
        self.assertEqual(by_id['intensity']['support'], 'not_supported')  # partly with no passage is not counted
        self.assertTrue(result['supported'])
        self.assertEqual(result['follow_up'], 'Which document shows the hours?')
        self.assertEqual([p['source_id'] for p in result['passages']], ['att-1'])
        self.assertEqual(model.calls[0][0], 'answer_check')
        self.assertEqual(model.calls[0][1]['answer'], ANSWER)

    def test_one_follow_up_at_most_and_only_while_something_is_open(self):
        everything = {'dimensions': [{'dimension_id': d['id'], 'support': 'supported', 'passage_ids': ['p1'],
                                      'note': ''} for d in self.dims], 'follow_up': 'Anything else?'}
        self.assertIsNone(layer2.check_answer('Q?', ANSWER, self.windows, self.dims, Reply(everything))['follow_up'])
        partly = {'dimensions': [{'dimension_id': 'coverage', 'support': 'partly', 'passage_ids': ['p1'], 'note': ''}],
                  'follow_up': 'Which register?'}
        self.assertIsNone(layer2.check_answer('Q?', ANSWER, self.windows, self.dims, Reply(partly),
                                              allow_follow_up=False)['follow_up'])


class RoutingTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.first = self.rubric['indicators'][0]
        self.pillar = [i['code'] for i in self.rubric['indicators'] if i['pillar'] == self.first['pillar']]

    def test_area_pick_expands_to_its_key_indicators(self):
        routing = layer2.route_additional(self.rubric, [self.first['pillar']])
        self.assertEqual(routing['indicators'], self.pillar)
        self.assertEqual(routing['conditions'], {})

    def test_requirement_pick_limits_its_indicator_unless_the_whole_indicator_is_picked(self):
        cid = self.first['conditions'][0]['id']
        self.assertEqual(layer2.route_additional(self.rubric, [cid])['conditions'], {self.first['code']: [cid]})
        self.assertEqual(layer2.route_additional(self.rubric, [cid, self.first['code']])['conditions'], {})

    def test_picks_first_then_extraction_tags_capped(self):
        last = self.rubric['indicators'][-1]['code']
        routing = layer2.route_additional(self.rubric, [last, 'nonsense'], extracted_codes=self.pillar, cap=2)
        self.assertEqual(routing['indicators'], [last, self.pillar[0]])
        self.assertEqual(routing['dropped'], [c for c in self.pillar[1:] if c != last])
        self.assertEqual(routing['unknown'], ['nonsense'])


def record(cid, credit, finding='not_found', citations=()):
    return {'condition_id': cid, 'credit': credit, 'state': 'met' if credit == 1 else 'unknown',
            'parts': [{'id': 'a', 'finding': finding, 'credited_as': finding, 'citations': list(citations)}]}


class CreditPathTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.indicator = self.rubric['indicators'][0]
        self.code = self.indicator['code']
        self.ids = [c['id'] for c in self.indicator['conditions']]
        self.packet = [{**ANNEXURE, 'text_offset': 0}]
        self.window = layer2._window(CERTIFICATE, 0, len(CERTIFICATE['text']), 'answer_attachment')

    def test_targets_skip_full_credit_and_routes_without_passages(self):
        records = [record(self.ids[0], 1), record(self.ids[1], 0.25)]
        targets = layer2.credit_targets(records, self.rubric, [
            {'indicator': self.code, 'conditions': None, 'windows': [self.window]},
            {'indicator': self.rubric['indicators'][1]['code'], 'conditions': None, 'windows': []},
            {'indicator': 'NOT-A-CODE', 'conditions': None, 'windows': [self.window]}])
        self.assertEqual(list(targets), [self.code])
        self.assertNotIn(self.ids[0], targets[self.code]['conditions'])
        self.assertIn(self.ids[1], targets[self.code]['conditions'])
        subset = layer2.subset_rubric(self.rubric, targets)
        self.assertEqual({c['id'] for c in subset['indicators'][0]['conditions']}, set(targets[self.code]['conditions']))

    def test_fixed_packet_is_the_provisional_one_plus_only_new_text(self):
        repeat = {**ANNEXURE, 'text_offset': 0, 'evidence_role': 'answer_search'}
        targets = {self.code: {'conditions': self.ids[:1], 'windows': [repeat, self.window]}}
        contexts, audit = layer2.fixed_contexts([{'indicator': self.code, 'source_excerpts': self.packet}], targets)
        self.assertEqual(contexts[self.code][:1], self.packet)
        self.assertEqual([w['id'] for w in contexts[self.code][1:]], ['att-1'])
        self.assertEqual(audit[self.code]['added_chars'], len(CERTIFICATE['text']))
        small, _ = layer2.fixed_contexts([{'indicator': self.code, 'source_excerpts': self.packet}], targets, limit=150)
        self.assertEqual(sum(len(w['text']) for w in small[self.code][1:]), 150)
        tiny, _ = layer2.fixed_contexts([{'indicator': self.code, 'source_excerpts': self.packet}], targets, limit=40)
        self.assertEqual(tiny[self.code], self.packet)  # pieces under MIN_PIECE are not worth a place
        with self.assertRaises(Layer2Error):
            layer2.fixed_contexts([], targets)

    def test_credit_rises_only_on_evidence_new_to_the_packet(self):
        cid = self.ids[0]
        packets = {self.code: self.packet}
        provisional = [record(cid, 0)]
        new = [record(cid, 1, 'full', [{'source_id': 'att-1', 'quote': NEW_QUOTE}])]
        old = [record(cid, 1, 'full', [{'source_id': 'page-7', 'quote': 'completed the Certificate Programme'}])]
        merged, audit = layer2.merge_new_evidence(provisional, new, packets)
        self.assertEqual((merged[0]['credit'], audit[0]['decision']), (1, 'replaced'))
        merged, audit = layer2.merge_new_evidence(provisional, old, packets)
        self.assertEqual((merged[0]['credit'], audit[0]['decision']), (0, 'rise without new evidence'))
        contradicted = [record(cid, 0, 'contradicted', [{'source_id': 'att-1', 'quote': 'IIT Madras'}])]
        merged, audit = layer2.merge_new_evidence([record(cid, 0.25, 'related')], contradicted, packets)
        self.assertEqual((merged[0]['credit'], audit[0]['decision'], audit[0]['contradicted_parts']),
                         (0.25, 'no rise', ['a']))

    def test_merge_reads_both_passes_of_a_combined_record(self):
        cid = 'X-1.1.A1'
        old_cite = {'source_id': 'page-7', 'quote': 'completed the Certificate Programme'}
        new_cite = {'source_id': 'att-1', 'quote': NEW_QUOTE}
        subject = {'id': 's', 'finding': 'full', 'credited_as': 'full', 'second_finding': 'full',
                   'second_credited_as': 'full', 'citations': [old_cite], 'second_citations': [old_cite],
                   'part_credit': 1.0}
        provisional = {'condition_id': cid, 'credit': 0.0, 'state': 'unknown', 'parts': [
            subject, {'id': 'a', 'finding': 'not_found', 'credited_as': 'not_found', 'second_finding': 'not_found',
                      'second_credited_as': 'not_found', 'citations': [], 'second_citations': [], 'part_credit': 0.0}]}
        # Only the second pass found the new certificate: its citation survives only in second_citations.
        rejudged = {'condition_id': cid, 'credit': 0.5, 'state': 'unknown', 'parts': [
            subject, {'id': 'a', 'finding': 'not_found', 'credited_as': 'not_found', 'second_finding': 'full',
                      'second_credited_as': 'full', 'citations': [new_cite], 'second_citations': [new_cite],
                      'part_credit': 0.5}]}
        rejudged['parts'][1]['citations'] = []
        merged, audit = layer2.merge_new_evidence([provisional], [rejudged], {'X-1.1': self.packet})
        self.assertEqual((audit[0]['decision'], merged[0]['credit']), ('replaced', 0.5))

    def test_a_part_that_rose_without_new_evidence_keeps_its_provisional_result(self):
        cid = 'X-1.1.A2'
        old_cite = {'source_id': 'page-7', 'quote': 'completed the Certificate Programme'}
        new_cite = {'source_id': 'att-1', 'quote': NEW_QUOTE}
        part = lambda pid, finding, cites: {'id': pid, 'finding': finding, 'credited_as': finding, 'citations': cites}
        provisional = {'condition_id': cid, 'credit': 0.0, 'state': 'unknown',
                       'parts': [part('s', 'full', [old_cite]), part('a', 'not_found', []), part('b', 'not_found', [])]}
        rejudged = {'condition_id': cid, 'credit': 1.0, 'state': 'met',
                    'parts': [part('s', 'full', [old_cite]), part('a', 'full', [new_cite]), part('b', 'full', [old_cite])]}
        merged, audit = layer2.merge_new_evidence([provisional], [rejudged], {'X-1.1': self.packet})
        self.assertEqual(audit[0]['decision'], 'replaced')
        self.assertEqual((audit[0]['new_evidence_parts'], audit[0]['reverted_parts']), (['a'], ['b']))
        self.assertEqual((merged[0]['credit'], merged[0]['state']), (0.5, 'unknown'))
        self.assertEqual([p['credited_as'] for p in merged[0]['parts']], ['full', 'full', 'not_found'])

    def test_contradictions_are_listed_for_review(self):
        audit = [{'condition_id': 'X', 'contradicted_parts': ['a']}, {'condition_id': 'Y', 'contradicted_parts': []}]
        self.assertEqual(layer2.contradictions(audit), [{'condition_id': 'X', 'parts': ['a']}])

    def test_skip_flag_from_forms(self):
        self.assertEqual([flag(v) for v in (True, 'true', '1', 'on', False, 'false', '0', '', None)],
                         [True, True, True, True, False, False, False, False, False])

    def test_evaluate_needs_a_fixed_packet_for_every_indicator(self):
        with self.assertRaises(ValueError):
            evaluation.evaluate([], service=None, population='All', reference_period='2025-26',
                                rubric={'indicators': [self.indicator]}, fixed_contexts={})

    def test_prepare_uses_the_fixed_packet_without_retrieval(self):
        window = {**ANNEXURE, 'text_offset': 0}
        job = evaluation._prepare(self.indicator, sources=[ANNEXURE, CANTEEN], semantic_ranker=None, gemini=False,
                                  reviewed_evidence=None, population='All', reference_period='2025-26', scope=None,
                                  fixed_context=[window])
        self.assertEqual(job['context'], [window])
        self.assertIsNone(job['evidence_lane'])


class FlowTests(TestCase):
    def setUp(self):
        self.spec, self.code, self.cid, self.dims = spec_condition()
        self.rubric = release()
        indicator = next(i for i in self.rubric['indicators'] if i['code'] == self.code)
        self.missing_cid = next(c['id'] for c in indicator['conditions'] if c['id'] != self.cid)
        self.q1 = DepthQuestion.objects.create(run_ref='run-x', kind='depth', indicator_code=self.code,
                                               condition_ids=[self.cid], dimension_ids=[d['id'] for d in self.dims[:2]],
                                               text='Who ran the training, and for how many hours?', rank=1,
                                               spec_version=self.spec['version'])
        self.q2 = DepthQuestion.objects.create(run_ref='run-x', kind='missing', indicator_code=self.code,
                                               condition_ids=[self.missing_cid], text='We found nothing for this.',
                                               rank=2, spec_version=self.spec['version'])

    def check_reply(self, follow_up):
        first, second = self.dims[0]['id'], self.dims[1]['id']
        return Reply({'dimensions': [{'dimension_id': first, 'support': 'supported', 'passage_ids': ['p1'], 'note': ''},
                                     {'dimension_id': second, 'support': 'not_supported', 'passage_ids': [],
                                      'note': 'Hours not shown.'}], 'follow_up': follow_up})

    def test_one_question_then_its_one_follow_up_then_the_next_question(self):
        self.assertEqual(next_item('run-x')['question'], self.q1)
        response = submit(self.q1, answer=ANSWER, document_ids=['00000000-0000-0000-0000-000000000001'])
        self.assertEqual(response.status, DepthResponse.Status.PENDING)
        check_response(response, self.check_reply('Which document shows the hours?'), attached=[CERTIFICATE], corpus=[])
        response.refresh_from_db()
        self.assertTrue(response.supported)
        self.assertEqual(response.follow_up_text, 'Which document shows the hours?')
        item = next_item('run-x')
        self.assertEqual((item['type'], item['response']), ('follow_up', response))
        child = submit(self.q1, answer='The attendance register lists 40 hours.', parent=response)
        check_response(child, self.check_reply('And the syllabus?'), attached=[CERTIFICATE], corpus=[])
        child.refresh_from_db()
        self.assertEqual(child.follow_up_text, '')  # never followed up again
        with self.assertRaises(Layer2Error):
            submit(self.q1, answer='more', parent=response)
        self.assertEqual(next_item('run-x')['question'], self.q2)

    def test_supported_depth_answer_also_routes_to_the_credit_path(self):
        response = submit(self.q1, answer=ANSWER)
        check_response(response, self.check_reply(''), attached=[CERTIFICATE], corpus=[])
        routes = credit_routes('run-x')
        self.assertEqual([(r['indicator'], r['conditions']) for r in routes], [(self.code, [self.cid])])
        self.assertEqual(response.support_check['search']['ranking'], 'keyword')

    def test_documents_are_read_only_for_a_run_in_this_database(self):
        response = submit(self.q1, answer=ANSWER, document_ids=['00000000-0000-0000-0000-000000000009'])
        with self.assertRaises(Layer2Error):
            check_response(response, self.check_reply(''))

    def test_typed_answer_with_nothing_found_costs_no_call_and_asks_for_a_document(self):
        model = self.check_reply('unused')
        response = submit(self.q1, answer='We ran a 300-hour programme.')
        check_response(response, model, attached=[], corpus=[CANTEEN])
        self.assertFalse(model.calls)
        self.assertFalse(response.supported)
        self.assertEqual(response.follow_up_text, layer2.NO_SUPPORT_FOLLOW_UP)

    def test_skip_and_empty_answers(self):
        response = submit(self.q2, skip=True)
        self.assertEqual((response.kind, response.status), ('dont_know', 'checked'))
        self.q2.refresh_from_db()
        self.assertEqual(self.q2.status, DepthQuestion.Status.ANSWERED)
        with self.assertRaises(Layer2Error):
            submit(self.q1)

    def test_nothing_found_answer_goes_to_the_credit_path_and_raises_credit_only_on_new_evidence(self):
        response = submit(self.q2, answer=ANSWER, document_ids=['00000000-0000-0000-0000-000000000002'])
        model = Reply({})
        check_response(response, model, attached=[CERTIFICATE], corpus=[])
        self.assertFalse(model.calls)  # judged in the credit path, not here
        self.assertTrue(response.supported)
        routes = credit_routes('run-x')
        self.assertEqual([(r['indicator'], r['conditions']) for r in routes], [(self.code, [self.missing_cid])])
        packet = [{**ANNEXURE, 'text_offset': 0}]
        export = {'run_id': 'run-x', 'rubric': self.rubric, 'population': 'All', 'reference_period': '2025-26',
                  'assessment': {'records': [record(self.missing_cid, 0)],
                                 'traces': [{'indicator': self.code, 'source_excerpts': packet,
                                             'judgment': part_judgment.metadata()}]}}
        seen = {}

        def judge(sources, **kwargs):
            seen.update(kwargs)
            return {'records': [record(self.missing_cid, 1, 'full', [
                {'source_id': 'att-1', 'quote': NEW_QUOTE}])], 'traces': []}
        result = rejudge_credit(export, service=None, evaluate_fn=judge, sources=[ANNEXURE, CERTIFICATE])
        self.assertEqual([c['id'] for c in seen['rubric']['indicators'][0]['conditions']], [self.missing_cid])
        self.assertEqual([w['id'] for w in seen['fixed_contexts'][self.code]], ['page-7', 'att-1'])
        self.assertEqual(result['merge'][0]['decision'], 'replaced')
        self.assertGreater(result['final_score'], result['provisional_score'])

    def test_additional_evidence_needs_a_pick_and_is_routed_and_searched(self):
        with self.assertRaises(Layer2Error):
            add_evidence('run-x', self.rubric, document_ids=['00000000-0000-0000-0000-000000000003'], picked=[])
        item = add_evidence('run-x', self.rubric, document_ids=['00000000-0000-0000-0000-000000000003'],
                            note='Certificate Programme in Machine Learning', picked=[self.code])
        check_additional(item, self.rubric, attached=[CERTIFICATE], extracted=set())
        item.refresh_from_db()
        self.assertEqual((item.status, item.routing['indicators']), ('checked', [self.code]))
        self.assertEqual([w['id'] for w in item.windows], ['att-1'])
        self.assertEqual(credit_routes('run-x')[0]['indicator'], self.code)


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_JUDGMENT='conditions',
    CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False,
    AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}', SECOND_LAYER_CHECK_ON_SUBMIT=False)
class SecondLayerAPITests(APITestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        from apps.institutions.models import Institution
        from apps.sprints.models import Sprint
        from .models import CapabilityExecution
        institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=institution)
        other = Sprint.objects.create(institution=Institution.objects.create(name='Other'))
        user = User.objects.create_user(username='coordinator', email='coord@example.com',
                                        role=User.Role.IQAC_COORDINATOR, institution=institution)
        self.client.force_authenticate(user)
        self.doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        DocumentPage.objects.create(document=self.doc, page_number=1, text='Institutional evidence for 2025-26.')
        self.foreign = Document.objects.create(sprint=other, document_type='naac_ssr')
        base = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
        with patch('apps.scoring.capability.execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                started = self.client.post(base, {'population': 'All', 'reference_period': '2025-26'}, format='json',
                                           HTTP_IDEMPOTENCY_KEY='layer2')
        self.assertEqual(started.status_code, 202, started.data)
        self.execution = CapabilityExecution.objects.get(run_id=started.data['id'])
        self.url = f'{base}/{self.execution.run_id}'
        self.code = self.execution.run.inputs['rubric']['indicators'][0]['code']
        self.question = DepthQuestion.objects.create(
            run_ref=str(self.execution.run_id), kind='missing', indicator_code=self.code,
            condition_ids=[self.execution.run.inputs['rubric']['indicators'][0]['conditions'][0]['id']],
            text='We found nothing for this. Do you have anything?', rank=1, spec_version='test')

    def test_question_flow_and_document_ownership(self):
        listed = self.client.get(f'{self.url}/questions')
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data['next']['question']['id'], str(self.question.pk))
        foreign = self.client.post(f'{self.url}/questions/{self.question.pk}/responses',
                                   {'answer': 'Here', 'document_ids': [str(self.foreign.pk)]}, format='json')
        self.assertEqual(foreign.status_code, 400)
        made = self.client.post(f'{self.url}/questions/{self.question.pk}/responses',
                                {'answer': 'Our register', 'document_ids': [str(self.doc.pk)]}, format='json')
        self.assertEqual(made.status_code, 201, made.data)
        self.assertEqual(made.data['status'], 'pending')
        shown = self.client.get(f"{self.url}/responses/{made.data['id']}/")
        self.assertEqual((shown.status_code, shown.data['answer']), (200, 'Our register'))
        again = self.client.post(f'{self.url}/questions/{self.question.pk}/responses', {'skip': True}, format='json')
        self.assertEqual(again.status_code, 400)
        self.assertIsNone(self.client.get(f'{self.url}/questions').data['next'])

    def test_follow_up_endpoint_and_one_answer_only(self):
        spec, code, cid, dims = spec_condition()
        question = DepthQuestion.objects.create(
            run_ref=str(self.execution.run_id), kind='depth', indicator_code=code, condition_ids=[cid],
            dimension_ids=[d['id'] for d in dims[:2]], text='Who ran it, and for how long?', rank=2,
            spec_version=spec['version'])
        made = self.client.post(f'{self.url}/questions/{question.pk}/responses',
                                {'answer': 'Institutional evidence', 'document_ids': [str(self.doc.pk)]}, format='json')
        self.assertEqual(made.status_code, 201, made.data)
        response = DepthResponse.objects.get(pk=made.data['id'])
        model = Reply({'dimensions': [{'dimension_id': dims[0]['id'], 'support': 'supported', 'passage_ids': ['p1'],
                                       'note': ''}], 'follow_up': 'Which document shows the hours?'})
        check_response(response, model, ranker=None)
        self.assertEqual(response.follow_up_text, 'Which document shows the hours?')
        nxt = self.client.get(f'{self.url}/questions').data['next']
        self.assertEqual((nxt['type'], nxt['response_id']), ('follow_up', str(response.pk)))
        answered = self.client.post(f'{self.url}/responses/{response.pk}/follow-up',
                                    {'answer': 'The register', 'skip': 'false'}, format='json')
        self.assertEqual((answered.status_code, answered.data['parent_id']), (201, str(response.pk)))
        again = self.client.post(f'{self.url}/responses/{response.pk}/follow-up', {'skip': True}, format='json')
        self.assertEqual(again.status_code, 400)

    def test_documents_wait_for_extraction_report_failures_and_stay_in_their_sprint(self):
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        busy = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status=Document.Status.PROCESSING)
        DocumentPage.objects.create(document=busy, page_number=1, text='Half read.')
        failed = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status=Document.Status.FAILED)
        self.assertFalse(document_sources([str(busy.pk)], self.sprint.pk)[1])
        sources, ready, broken = document_sources([str(self.doc.pk), str(failed.pk)], self.sprint.pk)
        self.assertEqual((len(sources), ready, broken), (1, True, [str(failed.pk)]))
        with self.assertRaises(Layer2Error):
            document_sources([str(self.foreign.pk)], self.sprint.pk)
        with self.assertRaises(Layer2Error):
            submit(self.question, answer='x', document_ids=[str(self.foreign.pk)])

    def test_pending_answers_are_checked_by_the_command_path(self):
        submit(self.question, answer='Institutional evidence', document_ids=[str(self.doc.pk)])
        counts = check_pending(str(self.execution.run_id), Reply({}), ranker=None)
        self.assertEqual((counts['checked'], counts['waiting'], counts['model_calls']), (1, 0, 0))
        response = DepthResponse.objects.get()
        self.assertTrue(response.supported)
        self.assertEqual(response.windows[0]['document_id'], str(self.doc.pk))

    def test_long_answers_are_refused_and_a_failed_check_on_submit_keeps_the_answer(self):
        long = self.client.post(f'{self.url}/questions/{self.question.pk}/responses',
                                {'answer': 'x' * 5000}, format='json')
        self.assertEqual(long.status_code, 400)
        with override_settings(SECOND_LAYER_CHECK_ON_SUBMIT=True), \
                patch('apps.scoring.capability.layer2_service.check_response', side_effect=RuntimeError('provider')), \
                patch('apps.scoring.capability.depth.default_model', return_value=Reply({})):
            made = self.client.post(f'{self.url}/questions/{self.question.pk}/responses',
                                    {'answer': 'Our register', 'document_ids': [str(self.doc.pk)]}, format='json')
        self.assertEqual((made.status_code, made.data['status']), (201, 'pending'))

    def test_additional_evidence(self):
        empty = self.client.post(f'{self.url}/additional-evidence',
                                 {'document_ids': [str(self.doc.pk)], 'note': 'x', 'picked': []}, format='json')
        self.assertEqual(empty.status_code, 400)
        made = self.client.post(f'{self.url}/additional-evidence',
                                {'document_ids': [str(self.doc.pk)], 'note': 'Our AI lab register',
                                 'picked': [self.code]}, format='json')
        self.assertEqual(made.status_code, 201, made.data)
        self.assertEqual(made.data['routed_indicators'], [self.code])
        self.assertEqual(len(self.client.get(f'{self.url}/additional-evidence/').data['results']), 1)
        self.assertEqual(AdditionalEvidence.objects.count(), 1)


# ------------------------------------------------------------------ audit of PR #45 (12 Nov): one test per finding

def gated_condition():
    """A real condition with a gate part and at least two other parts."""
    spec = part_judgment._load()[0]['conditions']
    for cid, item in spec.items():
        parts = [p['id'] for p in item['parts']]
        gates = [p['id'] for p in item['parts'] if p.get('gate')] or parts[:1]
        if len(parts) >= 3 and parts[0] in gates:
            return cid, cid.rsplit('.', 1)[0], parts
    raise AssertionError('No gated condition with three parts.')


def two_pass(pid, first, second=None, cites=(), second_cites=None):
    value = {'full': 1.0, 'related': part_judgment.RELATED_CREDIT}
    second = first if second is None else second
    return {'id': pid, 'finding': first, 'credited_as': first, 'second_finding': second, 'second_credited_as': second,
            'citations': list(cites), 'second_citations': list(cites if second_cites is None else second_cites),
            'part_credit': round((value.get(first, 0) + value.get(second, 0)) / 2, 4)}


OLD_TEXT = 'The B.Tech programme includes a practical laboratory assessment of every student each semester.'
NEW_TEXT = 'The college runs an approved Minor in Artificial Intelligence and Machine Learning from 2024-25.'


class AuditFixTests(SimpleTestCase):
    def setUp(self):
        self.cid, self.code, self.parts = gated_condition()
        self.packet = [{'id': 'page-old', 'document_id': 'doc-ssr', 'page_number': 3, 'text': OLD_TEXT + FILLER,
                        'text_offset': 0}]
        self.old = {'source_id': 'page-old', 'quote': OLD_TEXT}
        self.new = {'source_id': 'page-new', 'quote': NEW_TEXT}

    def test_document_only_reply_is_judged_on_the_documents(self):
        spec, code, cid, dims = spec_condition()
        model = Reply({'dimensions': [{'dimension_id': dims[0]['id'], 'support': 'supported', 'passage_ids': ['p1'],
                                       'note': ''}], 'follow_up': ''})
        window = layer2._window(CERTIFICATE, 0, len(CERTIFICATE['text']), 'answer_attachment')
        result = layer2.check_answer('Who ran it?', '', [window], dims[:2], model)
        self.assertTrue(result['supported'])
        sent = model.calls[0][1]
        self.assertIn('documents only', sent['answer'])
        self.assertEqual(sent['passages'][0]['role'], 'answer_attachment')
        self.assertIn('sent documents without writing anything', layer2.CHECK_PROMPT)
        self.assertNotIn('the answer says nothing about it', layer2.CHECK_PROMPT)

    def test_corpus_support_can_be_switched_off(self):
        spec, code, cid, dims = spec_condition()
        model = Reply({'dimensions': [{'dimension_id': dims[0]['id'], 'support': 'supported', 'passage_ids': ['p1'],
                                       'note': ''}], 'follow_up': ''})
        found = layer2._window(ANNEXURE, 0, len(ANNEXURE['text']), 'answer_search')
        on = layer2.check_answer('Who ran it?', ANSWER, [found], dims[:1], model)
        off = layer2.check_answer('Who ran it?', ANSWER, [found], dims[:1], model, counts_from={'answer_attachment'})
        self.assertEqual((on['supported'], off['supported']), (True, False))
        self.assertIn('already submitted', off['dimensions'][0]['note'])

    def test_a_restated_copy_is_not_new_evidence(self):
        copy = {'id': 'aqar-page', 'document_id': 'doc-aqar', 'page_number': 1, 'text': 'AQAR 2024-25. ' + OLD_TEXT + FILLER,
                'text_offset': 0}
        self.assertFalse(layer2.is_new({'source_id': 'aqar-page', 'quote': OLD_TEXT}, self.packet))
        targets = {self.code: {'conditions': [self.cid], 'windows': [copy]}}
        contexts, audit = layer2.fixed_contexts([{'indicator': self.code, 'source_excerpts': self.packet}], targets)
        self.assertEqual(contexts[self.code], self.packet)
        self.assertEqual(audit[self.code]['restatements_skipped'], 1)

    def test_new_evidence_for_a_missing_gate_unlocks_the_other_parts(self):
        gate, *rest = self.parts
        provisional = {'condition_id': self.cid, 'credit': 0.0, 'state': 'unknown',
                       'parts': [two_pass(p, 'not_found') for p in self.parts]}
        rejudged = {'condition_id': self.cid, 'credit': 1.0, 'state': 'met', 'pass_credits': [1.0, 1.0],
                    'parts': [two_pass(gate, 'full', cites=[self.new])] + [two_pass(p, 'full', cites=[self.old])
                                                                          for p in rest]}
        merged, audit = layer2.merge_new_evidence([provisional], [rejudged], {self.code: self.packet})
        self.assertEqual(audit[0]['decision'], 'replaced')
        self.assertEqual((audit[0]['new_evidence_parts'], audit[0]['unlocked_parts']), ([gate], rest))
        self.assertEqual(merged[0]['credit'], 1.0)
        # The re-judge's own pass credits move to the marker; they do not describe the merged record.
        self.assertNotIn('pass_credits', merged[0])
        self.assertEqual(merged[0]['second_layer']['rejudge_pass_credits'], [1.0, 1.0])

    def test_no_unlock_when_the_gate_was_already_credited(self):
        gate, first, *others = self.parts
        provisional = {'condition_id': self.cid, 'credit': 0.0, 'state': 'unknown',
                       'parts': [two_pass(gate, 'full', cites=[self.old])] + [two_pass(p, 'not_found')
                                                                              for p in [first, *others]]}
        rejudged = {'condition_id': self.cid, 'credit': 1.0, 'state': 'met',
                    'parts': [two_pass(gate, 'full', cites=[self.old]), two_pass(first, 'full', cites=[self.new])]
                    + [two_pass(p, 'full', cites=[self.old]) for p in others]}
        merged, audit = layer2.merge_new_evidence([provisional], [rejudged], {self.code: self.packet})
        self.assertEqual((audit[0]['new_evidence_parts'], audit[0]['unlocked_parts'], audit[0]['reverted_parts']),
                         ([first], [], others))

    def test_a_failed_rejudgment_is_reported_not_called_no_rise(self):
        failed = {'condition_id': self.cid, 'credit': 0.0, 'state': 'unknown', 'parts': [], 'cause': 'not_evaluated',
                  'validation_issue': 'Model evaluation failed (Timeout). Capability is unknown.'}
        provisional = {'condition_id': self.cid, 'credit': 0.0, 'state': 'unknown',
                       'parts': [two_pass(p, 'not_found') for p in self.parts]}
        merged, audit = layer2.merge_new_evidence([provisional], [failed], {self.code: self.packet})
        self.assertTrue(audit[0]['decision'].startswith('not re-judged'))
        self.assertEqual(merged[0]['parts'], provisional['parts'])

    def test_new_windows_take_the_budget_in_route_order(self):
        rubric = release()
        indicator = next(i for i in rubric['indicators'] if i['code'] == self.code)
        records = [{'condition_id': c['id'], 'credit': 0.0} for c in indicator['conditions']]
        depth_window = {'id': 'depth-page', 'document_id': 'd', 'page_number': 1, 'text': 'D' * 300, 'text_offset': 0}
        missing_window = {'id': 'missing-page', 'document_id': 'm', 'page_number': 1, 'text': 'M ' * 150,
                          'text_offset': 0}
        targets = layer2.credit_targets(records, rubric, [
            {'indicator': self.code, 'conditions': None, 'windows': [depth_window], 'kind': 'depth'},
            {'indicator': self.code, 'conditions': None, 'windows': [missing_window], 'kind': 'missing'},
            {'indicator': self.code, 'conditions': None, 'windows': [], 'documents': ['doc-x'], 'kind': 'additional'}])
        self.assertEqual([w['id'] for w in targets[self.code]['windows']], ['missing-page', 'depth-page'])
        self.assertEqual(targets[self.code]['documents'], ['doc-x'])

    def test_export_scored_under_another_part_rule_is_refused(self):
        targets = {self.code: {'conditions': [self.cid], 'windows': []}}
        old_rule = {**part_judgment.metadata(), 'related_credit': 0.5}
        with self.assertRaises(Layer2Error):
            layer2.check_export_rule([], [{'indicator': self.code, 'judgment': old_rule}], targets)
        with self.assertRaises(Layer2Error):
            layer2.check_export_rule([], [{'indicator': self.code}], targets)
        # Subject counted as a share (the rule before 528c550): the recorded credit is not today's.
        shared = {'condition_id': self.cid, 'credit': 0.5,
                  'parts': [two_pass(self.parts[0], 'full')] + [two_pass(p, 'not_found') for p in self.parts[1:]]}
        with self.assertRaises(Layer2Error):
            layer2.check_export_rule([shared], [{'indicator': self.code, 'judgment': part_judgment.metadata()}],
                                     targets)
        layer2.check_export_rule([{**shared, 'credit': 0.0}],
                                 [{'indicator': self.code, 'judgment': part_judgment.metadata()}], targets)

    def test_credited_evidence_and_anchored_query(self):
        record = {'citations': [self.old]}
        windows = layer2.credited_windows(record, self.packet + [{**CANTEEN, 'text_offset': 0}])
        self.assertEqual([(w['id'], w['evidence_role']) for w in windows], [('page-old', 'credited_evidence')])
        self.assertEqual(layer2.anchored_query('Yes, 300 hours.', record), 'Yes, 300 hours. ' + OLD_TEXT)
        self.assertEqual(layer2.anchored_query('Yes.', None), 'Yes.')

    def test_fallback_query_is_records_language_not_rubric_wording(self):
        rubric = release()
        indicator = rubric['indicators'][0]
        query = layer2.profile_query(rubric, [indicator['conditions'][0]['id']])
        self.assertTrue(query)
        self.assertNotEqual(query, indicator['name'])

    def test_fixed_packets_build_no_embedding_ranker(self):
        indicator = release()['indicators'][0]
        with patch('apps.scoring.capability.semantic_retrieval.ranker_for', side_effect=AssertionError('built')):
            outcome = evaluation.evaluate([], service=None, population='All', reference_period='2025-26',
                                          rubric={**release(), 'indicators': [indicator]}, max_calls=0,
                                          judgment='parts', fixed_contexts={indicator['code']: []},
                                          retrieval_policy={'mode': 'hybrid', 'follow_up': None})
        self.assertEqual(len(outcome['records']), len(indicator['conditions']))


class AuditFixFlowTests(TestCase):
    def setUp(self):
        self.spec, self.code, self.cid, self.dims = spec_condition()
        self.question = DepthQuestion.objects.create(
            run_ref='run-y', kind='depth', indicator_code=self.code, condition_ids=[self.cid],
            dimension_ids=[d['id'] for d in self.dims[:2]], text='Who ran the training?', rank=1,
            spec_version=self.spec['version'])

    def test_search_leaves_out_the_packet_and_the_check_reads_the_credited_evidence(self):
        packet = [{**ANNEXURE, 'text_offset': 0}]
        record = {'condition_id': self.cid, 'citations': [{'source_id': 'page-7', 'quote': 'Dr Rao completed the '
                                                           'Certificate Programme in Machine Learning'}]}
        other = {'id': 'page-12', 'document_id': 'doc-aqar', 'page_number': 12,
                 'text': 'The Certificate Programme in Machine Learning with IIT Madras ran for 120 hours in 2024-25,'
                         ' with a final project assessed by the centre.' + FILLER}
        model = Reply({'dimensions': [{'dimension_id': self.dims[0]['id'], 'support': 'supported',
                                       'passage_ids': ['p1', 'p2'], 'note': ''}], 'follow_up': ''})
        response = submit(self.question, answer=ANSWER)
        check_response(response, model, attached=[], corpus=[ANNEXURE, other, CANTEEN], ranker=None,
                       context=({self.cid: record}, {self.code: packet}))
        self.assertEqual([w['id'] for w in response.windows], ['page-12'])  # the packet's page is not taken again
        roles = [p['role'] for p in model.calls[0][1]['passages']]
        self.assertEqual(roles, ['credited_evidence', 'answer_search'])
        self.assertEqual(response.support_check['search']['support_from'], ['answer_search', 'credited_evidence'])

    def test_new_responses_start_pending_and_the_file_path_needs_documents(self):
        from .capability.depth_service import DepthError, load_responses
        self.assertEqual(DepthResponse(question=self.question, kind='answer').status, DepthResponse.Status.PENDING)
        with self.assertRaises(DepthError):
            load_responses([{'question_id': str(self.question.pk), 'kind': 'answer', 'answer': 'Yes.',
                             'supported': True}], commit=True)
        load_responses([{'question_id': str(self.question.pk), 'kind': 'answer', 'answer': 'Yes.', 'supported': True,
                         'document_ids': ['00000000-0000-0000-0000-0000000000aa']}], commit=True)
        self.assertEqual(DepthResponse.objects.get().status, DepthResponse.Status.CHECKED)

    def test_depth_judge_waits_for_pending_checks(self):
        from .capability.depth_service import judge_run
        submit(self.question, answer=ANSWER)
        export = {'run_id': 'run-y', 'rubric': release(),
                  'assessment': {'records': [{'condition_id': self.cid, 'credit': 1.0, 'state': 'met', 'parts': [],
                                              'citations': []}]}}
        model = Reply({})
        result = judge_run(export, model, commit=True)
        self.assertEqual((result['awaiting_check'], result['judged'], result['unanswered']), ([self.cid], [], []))
        self.assertFalse(model.calls)


class RankerAndRouteTests(SimpleTestCase):
    def test_attachments_get_their_own_ranker_so_the_corpus_index_is_kept(self):
        stub = object()
        self.assertIs(layer2._attachment_ranker(stub), stub)
        self.assertIsNone(layer2._attachment_ranker(None))

        from .capability.semantic_retrieval import SemanticRanker

        class Model:
            model_name = 'stub'
        ranker = SemanticRanker(Model(), tokenizer=object(), token_limit=512)
        twin = layer2._attachment_ranker(ranker)
        self.assertIsNot(twin, ranker)
        self.assertIs(layer2._attachment_ranker(ranker), twin)
        self.assertIs(twin.model, ranker.model)

    def test_a_route_with_documents_but_nothing_found_reaches_no_judge_without_tagged_pages(self):
        rubric = release()
        indicator = rubric['indicators'][0]
        export = {'run_id': 'run-z', 'rubric': rubric, 'population': 'All', 'reference_period': '2025-26',
                  'assessment': {'records': [{'condition_id': c['id'], 'credit': 0.0} for c in indicator['conditions']],
                                 'traces': []}}
        routes = [{'indicator': indicator['code'], 'conditions': None, 'windows': [], 'documents': ['doc-x'],
                   'kind': 'missing'}]
        with patch('apps.scoring.capability.layer2_service._run', return_value=None):
            result = rejudge_credit(export, service=None, routes=routes,
                                    evaluate_fn=lambda *a, **k: self.fail('no judge call expected'))
        self.assertEqual(result['note'], 'No new evidence to re-judge.')
