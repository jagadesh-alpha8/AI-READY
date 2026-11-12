"""Targeted extra search after part judgment (follow_up.py): which parts are searched, which text is added,
and that the second judgment can add credit but never remove it."""
import json

from django.test import SimpleTestCase, override_settings

from .capability import follow_up as extra
from .capability import part_judgment
from .capability.engine import release
from .capability.evaluation import _judge_parts, _prepare
from .retrieval_test_fixtures import synthetic_ranker

FILLER = 'Students attend lectures and laboratory sessions across departments every semester. ' * 12
ERP = ('The institution runs an ERP digital service for admissions and examinations; its purpose is to process '
       'admission and examination records for every programme. ')
OWNER = 'Accountability for the platform rests with the Registrar office, which is answerable for it. '


class Model:
    model_name = 'test'

    def passage_embed(self, texts, **kwargs):
        return [[1., 0.] if 'Registrar' in text else [0., 1.] for text in texts]

    def query_embed(self, text):
        return [[1., 0.]]


def page(sid, doc, text):
    return {'id': sid, 'document_id': doc, 'page_number': 1, 'text': text, 'retrieval_hints': []}


def indicator():
    return next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C8.1')


class Service:
    """First judgment: the ERP page is the service and its purpose; nothing else is found.
    Follow-up judgment: `follow_up` decides what the second judgment reports for C8.1.F2."""
    def __init__(self, follow_up='full', fail=False):
        self.follow_up, self.fail, self.calls = follow_up, fail, []

    def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name):
        payload = json.loads(user_content)
        extra_windows = [s for s in payload['sources'] if s.get('evidence_role') == 'follow_up_search']
        self.calls.append([c['id'] for c in payload['indicator']['conditions']])
        erp = next(s for s in payload['sources'] if 'ERP digital service' in s['text'])
        cite = lambda window, text: [{'source_id': window['id'], 'quote': text}]
        rows = {}
        for condition in payload['indicator']['conditions']:
            findings = []
            for part in condition['parts']:
                finding, citations = 'not_found', []
                if condition['id'] in ('AIQIF-C8.1.F1', 'AIQIF-C8.1.F2') and part['id'] == 'p1':
                    finding, citations = 'full', cite(erp, 'runs an ERP digital service for admissions')
                elif condition['id'] == 'AIQIF-C8.1.F1':
                    finding, citations = 'full', cite(erp, 'its purpose is to process admission and examination records')
                elif condition['id'] == 'AIQIF-C8.1.F2' and extra_windows:
                    if self.fail:
                        raise RuntimeError('provider down')
                    owner = next(w for w in extra_windows if 'Registrar' in w['text'])
                    finding = self.follow_up
                    citations = [] if finding == 'not_found' else cite(owner, 'rests with the Registrar office')
                findings.append({'part_id': part['id'], 'finding': finding, 'citations': citations})
            if extra_windows and condition['id'] == 'AIQIF-C8.1.F2' and self.follow_up == 'lower':
                findings = [{'part_id': p['id'], 'finding': 'not_found', 'citations': []} for p in condition['parts']]
            rows[condition['id']] = {'reason': 'Test.', 'scope_supported': True, 'period_supported': True,
                                     'findings': findings}
        return {'conditions': rows}


class FollowUpTests(SimpleTestCase):
    def sources(self):
        return ([page('erp', 'ssr', ERP * 3)] + [page(f'f{n}', 'ssr', FILLER) for n in range(12)]
                + [page('owner', 'minutes', FILLER[:300] + OWNER + FILLER[:300])])

    def job(self, sources):
        ranker = synthetic_ranker(Model())
        ranker.baseline_chars, ranker.context_chars = 300, 300
        job = _prepare(indicator(), sources=sources, semantic_ranker=ranker, gemini=True, reviewed_evidence=None,
                       population='Students', reference_period='2023-24', scope=None)
        return job, ranker

    def judge(self, service, passes=1):
        import threading
        sources = self.sources()
        job, ranker = self.job(sources)
        self.assertNotIn('owner', {w['id'] for w in job['context']})  # the owner page is not in the first packet
        counted = []
        follow_up = {'ranker': ranker, 'lock': threading.Lock(), 'count': counted.append}
        outcome = _judge_parts(job, True, '', service=service, sources=sources, reviewed_evidence=None,
                               strict_errors=False, recover_provider_errors=False, agreement_passes=passes,
                               follow_up=follow_up)
        return outcome, {r['condition_id']: r for r in outcome['validated']}, counted, job

    def test_found_owner_raises_credit_and_is_in_the_sent_packet(self):
        service = Service('full')
        outcome, records, counted, job = self.judge(service)
        record = records['AIQIF-C8.1.F2']
        self.assertEqual(record['state'], 'met')
        self.assertEqual(record['credit'], 1.0)
        self.assertEqual(record['follow_up']['previous_credit'], 0.0)  # the subject alone earned nothing
        self.assertIn('AIQIF-C8.1.F2', outcome['follow_up_audit']['replaced'])
        # Only conditions with a newly found passage were judged again, in one extra request.
        self.assertEqual(len(service.calls), 2)
        self.assertIn('AIQIF-C8.1.F2', service.calls[1])
        self.assertNotIn('AIQIF-C8.1.F1', service.calls[1])  # fully met already, never re-judged
        self.assertEqual(counted, [1])
        # The trace's packet holds what was sent, and every window is an exact slice of its page.
        sent = outcome['context']
        self.assertIn('owner', {w['id'] for w in sent})
        lookup = {s['id']: s['text'] for s in self.sources()}
        for w in sent:
            self.assertEqual(lookup[w['id']][w['text_offset']:w['text_offset'] + len(w['text'])], w['text'])
        added = sum(len(w['text']) for w in sent) - sum(len(w['text']) for w in job['context'])
        self.assertEqual(added, outcome['follow_up_audit']['added_chars'])
        self.assertLessEqual(added, extra.FOLLOW_UP_CHARS)

    def test_the_extra_search_reuses_the_ranker_index_for_pages_with_printed_dates(self):
        import threading
        stamp = '07-08-2024 09:21:42'
        def dated(source):
            text = source['text'] + '\n' + stamp
            return {**source, 'text': text, 'report_timestamp': {'start': len(text) - len(stamp), 'value': stamp}}
        sources = [dated(s) for s in self.sources()]
        job, ranker = self.job(sources)
        builds = ranker.stats['corpus_builds']
        follow_up = {'ranker': ranker, 'lock': threading.Lock(), 'count': lambda n: None}
        outcome = _judge_parts(job, True, '', service=Service('full'), sources=sources, reviewed_evidence=None,
                               strict_errors=False, recover_provider_errors=False, agreement_passes=1,
                               follow_up=follow_up)
        self.assertEqual(ranker.stats['corpus_builds'], builds)   # no second embedding of the corpus
        self.assertIn('owner', {w['id'] for w in outcome['context']})
        lookup = {s['id']: s['text'] for s in sources}
        for w in outcome['context']:
            self.assertEqual(lookup[w['id']][w['text_offset']:w['text_offset'] + len(w['text'])], w['text'])
            if w.get('evidence_role') == 'follow_up_search':
                self.assertNotIn(stamp, w['text'])

    def test_a_lower_second_judgment_never_removes_credit(self):
        outcome, records, _, _ = self.judge(Service('lower'))
        record = records['AIQIF-C8.1.F2']
        self.assertEqual(record['credit'], 0.0)
        self.assertFalse(record['follow_up']['replaced'])
        self.assertEqual(record['follow_up']['second_credit'], 0.0)
        self.assertEqual(outcome['follow_up_audit']['replaced'], [])

    def test_a_failed_follow_up_request_keeps_the_first_results(self):
        outcome, records, _, job = self.judge(Service('full', fail=True))
        self.assertEqual(records['AIQIF-C8.1.F2']['credit'], 0.0)
        self.assertIn('first results kept', outcome['follow_up_audit']['error'])
        self.assertEqual(outcome['context'], job['context'])

    def test_two_passes_judge_the_follow_up_twice_and_agree(self):
        service = Service('full')
        outcome, records, counted, _ = self.judge(service, passes=2)
        self.assertEqual(len(service.calls), 4)
        self.assertEqual(records['AIQIF-C8.1.F2']['credit'], 1.0)
        self.assertEqual(outcome['follow_up_audit']['disagreements'], [])
        self.assertEqual(counted, [1, 1])

    def test_targets_skip_met_contradicted_and_unevaluated_and_put_partial_conditions_first(self):
        spec = part_judgment.specification(release())
        def record(cid, state, findings, **extra_fields):
            return {'condition_id': cid, 'state': state, 'credit': 0.0, **extra_fields,
                    'parts': [{'id': f'p{n}', 'finding': f} for n, f in enumerate(findings, 1)]}
        from .capability.decision_causes import NOT_EVALUATED
        records = [record('AIQIF-C8.1.A1', 'unknown', ['not_found', 'not_found', 'not_found']),
                   record('AIQIF-C8.1.F2', 'unknown', ['full', 'not_found']),
                   record('AIQIF-C8.1.F1', 'met', ['full', 'full']),
                   record('AIQIF-C8.1.A2', 'not_met', ['contradicted', 'not_found']),
                   record('AIQIF-C8.1.O1', 'unknown', ['not_found'] * 3, cause=NOT_EVALUATED)]
        chosen = extra.targets(records, spec)
        self.assertEqual(chosen[0], ('AIQIF-C8.1.F2', spec['AIQIF-C8.1.F2']['parts'][1]))
        self.assertEqual({cid for cid, _ in chosen}, {'AIQIF-C8.1.F2', 'AIQIF-C8.1.A1'})
        # A part either pass found is not searched again.
        records[1]['parts'][1]['second_finding'] = 'related'
        self.assertNotIn('AIQIF-C8.1.F2', {cid for cid, _ in extra.targets(records, spec)})

    def test_search_never_resends_text_already_in_the_packet(self):
        sources = self.sources()
        ranker = synthetic_ranker(Model())
        part = {'id': 'p2', 'full': 'A responsible owner (office, role, body) is assigned to it'}
        first = extra.search(part, sources, ranker, context=[])
        self.assertTrue(first)
        source, start, end = first[0]
        sent = [{**source, 'text': source['text'][start:end], 'text_offset': start}]
        again = extra.search(part, sources, ranker, context=sent)
        for _, a, b in again:
            self.assertFalse(a < end and start < b and _ == source)

    def test_keep_higher(self):
        first = [{'condition_id': 'a', 'state': 'unknown', 'credit': 0.5}, {'condition_id': 'b', 'state': 'unknown', 'credit': 0.5}]
        second = [{'condition_id': 'a', 'state': 'met', 'credit': 1.0}, {'condition_id': 'b', 'state': 'not_met', 'credit': 0.0}]
        merged, replaced = extra.keep_higher(first, second)
        self.assertEqual(replaced, ['a'])
        self.assertEqual(merged[0]['state'], 'met')
        self.assertEqual(merged[1]['state'], 'unknown')
        self.assertEqual(merged[1]['follow_up']['second_state'], 'not_met')


class FollowUpPolicyTests(SimpleTestCase):
    def test_policy_needs_hybrid_retrieval_and_part_judgment(self):
        from .capability.semantic_retrieval import SemanticRetrievalUnavailable, configured_policy
        with override_settings(CAPABILITY_FOLLOW_UP_SEARCH=True, CAPABILITY_JUDGMENT='parts'):
            with self.assertRaises(SemanticRetrievalUnavailable):
                configured_policy('bm25')
        with override_settings(CAPABILITY_FOLLOW_UP_SEARCH=False):
            self.assertNotIn('follow_up', configured_policy('bm25'))

    def test_evaluate_refuses_a_follow_up_policy_without_part_judgment(self):
        from .capability.evaluation import evaluate
        with self.assertRaisesRegex(ValueError, 'follow-up search version'):
            evaluate([page('a', 'd', 'text')], service=None, population='Students', reference_period='2024',
                     retrieval_policy={'mode': 'bm25', 'follow_up': 'other'}, max_calls=0, judgment='parts')
        with self.assertRaisesRegex(ValueError, 'needs part judgment and hybrid retrieval'):
            evaluate([page('a', 'd', 'text')], service=None, population='Students', reference_period='2024',
                     retrieval_policy={'mode': 'bm25', 'follow_up': extra.VERSION}, max_calls=0, judgment='parts')

    def test_call_budget_must_cover_the_extra_requests(self):
        from .capability.execution import AssessmentDisabled, policy
        base = dict(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_JUDGMENT='parts', CAPABILITY_MAX_COST_USD='20')
        with override_settings(**base, CAPABILITY_FOLLOW_UP_SEARCH=True, CAPABILITY_MAX_HTTP_CALLS=90):
            with self.assertRaises(AssessmentDisabled):
                policy()
        with override_settings(**base, CAPABILITY_FOLLOW_UP_SEARCH=True, CAPABILITY_MAX_HTTP_CALLS=150):
            self.assertEqual(policy()['max_http_calls'], 150)
            self.assertEqual(policy('recommendation')['max_http_calls'], 150)
        with override_settings(**base, CAPABILITY_FOLLOW_UP_SEARCH=False, CAPABILITY_MAX_HTTP_CALLS=150):
            with self.assertRaises(AssessmentDisabled):
                policy()
