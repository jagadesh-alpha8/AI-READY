"""Packets built from the evidence map (allocation evidence-map-then-keyword-v1). No model calls."""
from django.test import SimpleTestCase, TestCase, override_settings

from apps.institutions.models import Institution
from apps.scoring.capability.engine import release
from apps.scoring.capability.evaluation import MapLane, _prepare, map_argument
from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable, configured_policy
from apps.sprints.models import Sprint

from . import packet, spec
from .models import MapJob, MapPage

FILLER = 'The college library holds books on many subjects and is open to all students on working days. '


def page(pid, document, number, text):
    return {'id': pid, 'document_id': document, 'page_number': number, 'text': text}


def tag(indicator, strength, requirements=(), quote=''):
    return {'indicator': indicator, 'requirements': list(requirements), 'strength': strength, 'quote': quote,
            'quote_found': bool(quote), 'reason': 'test'}


def indicator(code='AIQIF-C9.2'):
    return next(i for i in release()['indicators'] if i['code'] == code)


def keyword_fill(pages, max_chars):
    """A stand-in for the keyword selector: pages in order, whole, while they fit."""
    out, used = [], 0
    for p in pages:
        if used + len(p['text']) > max_chars:
            break
        out.append(dict(p, text_offset=0))
        used += len(p['text'])
    return out


class BuildTests(SimpleTestCase):
    def setUp(self):
        self.ind = indicator()
        self.req = [c['id'] for c in self.ind['conditions']]
        self.sources = [page(f'p{n}', 'doc-a' if n < 6 else 'doc-b', n, f'Page {n}. ' + FILLER * 3) for n in range(1, 11)]
        self.long = page('long', 'doc-c', 1, FILLER * 60 + 'Answer before DVV Verification: 100 Answer after: 133. '
                         'Remark: changed as per the report. ' + FILLER * 60)
        self.sources.append(self.long)

    def frozen(self, tags):
        return {'pages': {spec.text_hash(s['text']): {'page_type': 'other', 'tags': tags[s['id']]}
                          for s in self.sources if s['id'] in tags}}

    def test_tagged_pages_come_first_and_the_judge_sees_no_tag(self):
        frozen = self.frozen({'p9': [tag(self.ind['code'], 'supporting', [self.req[0]])],
                              'p7': [tag(self.ind['code'], 'direct', [self.req[1]])]})
        context, trace = packet.build(self.ind, self.sources, frozen, cap=6000, keyword_fill=keyword_fill)
        self.assertEqual([w['id'] for w in context[:2]], ['p7', 'p9'])
        for window in context:
            self.assertFalse({'strength', 'step', 'tags', 'reason', 'evidence_role'} & window.keys())
        self.assertEqual([w['reasons'][0]['step'] for w in trace['windows'][:2]], ['direct', 'supporting'])

    def test_a_long_page_is_cut_around_the_quotation(self):
        frozen = self.frozen({'long': [tag(self.ind['code'], 'direct', [self.req[3]], 'Answer before DVV Verification: 100')]})
        context, _ = packet.build(self.ind, self.sources, frozen, cap=20000, keyword_fill=keyword_fill)
        window = context[0]
        self.assertEqual(window['id'], 'long')
        self.assertEqual(len(window['text']), packet.WINDOW_CHARS)
        self.assertIn('Answer before DVV Verification: 100', window['text'])
        self.assertEqual(self.long['text'][window['text_offset']:window['text_offset'] + len(window['text'])],
                         window['text'])   # an exact span of the frozen page
        before = window['text'].index('Answer before')
        self.assertLess(before, packet.WINDOW_CHARS // 2)   # about a third before, two thirds after

    def test_a_third_of_the_cap_is_kept_for_the_keyword_fill(self):
        tags = {s['id']: [tag(self.ind['code'], 'direct', [self.req[0]])] for s in self.sources[:10]}
        context, trace = packet.build(self.ind, self.sources, self.frozen(tags), cap=1200, keyword_fill=keyword_fill)
        self.assertLessEqual(trace['tagged_chars'], 800)
        self.assertGreater(trace['left_out_for_space'].get('direct', 0), 0)
        self.assertLessEqual(sum(len(w['text']) for w in context), 1200)

    def test_topical_pages_go_to_the_back_of_the_fill(self):
        frozen = self.frozen({'p1': [tag(self.ind['code'], 'topical')], 'p2': [tag(self.ind['code'], 'topical')]})
        context, trace = packet.build(self.ind, self.sources, frozen, cap=100000, keyword_fill=keyword_fill)
        ids = [w['id'] for w in context]
        self.assertGreater(ids.index('p1'), ids.index('p10'))
        self.assertEqual(trace['topical_pages'], 2)

    def test_tags_for_other_indicators_are_ignored(self):
        frozen = self.frozen({'p8': [tag('AIQIF-C1.1', 'direct')]})
        context, trace = packet.build(self.ind, self.sources, frozen, cap=100000, keyword_fill=keyword_fill)
        self.assertEqual(context[0]['id'], 'p1')
        self.assertEqual(trace['tagged_chars'], 0)

    def test_requirements_take_turns_and_prefer_a_new_document(self):
        frozen = self.frozen({'p1': [tag(self.ind['code'], 'direct', [self.req[0]])],
                              'p2': [tag(self.ind['code'], 'direct', [self.req[0]])],
                              'p7': [tag(self.ind['code'], 'direct', [self.req[0]])],
                              'p3': [tag(self.ind['code'], 'direct', [self.req[1]])]})
        context, _ = packet.build(self.ind, self.sources, frozen, cap=100000, keyword_fill=keyword_fill)
        first = context[:4]
        self.assertEqual(first[1]['id'], 'p3')      # the second requirement's turn comes before the first's second
        self.assertEqual({w['id'] for w in first}, {'p1', 'p2', 'p3', 'p7'})
        # The first requirement's second pick comes from the document it has not used yet.
        self.assertNotEqual(first[0]['document_id'], first[2]['document_id'])

    def test_context_tags_only_from_documents_already_in_the_packet(self):
        frozen = self.frozen({'p2': [tag(self.ind['code'], 'direct', [self.req[0]])],
                              'p4': [tag(self.ind['code'], 'context')], 'p8': [tag(self.ind['code'], 'context')]})
        context, trace = packet.build(self.ind, self.sources, frozen, cap=100000, keyword_fill=keyword_fill)
        steps = {w['id']: w['reasons'][0]['step'] for w in trace['windows']}
        self.assertEqual(steps['p4'], 'context')
        self.assertEqual(steps['p8'], 'keyword_fill')

    def test_the_lane_runs_inside_the_tagged_share(self):
        seen = {}

        def lane(context, budget):
            seen['budget'] = budget
            return context + [dict(self.sources[9], text_offset=0, evidence_role='extracted_evidence')], {'added': 1}
        frozen = self.frozen({'p2': [tag(self.ind['code'], 'direct', [self.req[0]])]})
        context, trace = packet.build(self.ind, self.sources, frozen, cap=9000, keyword_fill=keyword_fill, lane=lane)
        self.assertEqual(seen['budget'], 6000 - len(self.sources[1]['text']))
        self.assertEqual(context[1]['id'], 'p10')
        self.assertNotIn('p10', [w['id'] for w in context[2:]])
        self.assertEqual(trace['evidence_lane'], {'added': 1})

    def test_the_same_inputs_give_the_same_packet(self):
        frozen = self.frozen({'p2': [tag(self.ind['code'], 'direct', [self.req[0]])],
                              'p9': [tag(self.ind['code'], 'supporting')]})
        one = packet.build(self.ind, self.sources, frozen, cap=7000, keyword_fill=keyword_fill)
        two = packet.build(self.ind, list(reversed(self.sources)), frozen, cap=7000, keyword_fill=keyword_fill)
        self.assertEqual([w['id'] for w in one[0][:2]], [w['id'] for w in two[0][:2]])


class PrepareTests(SimpleTestCase):
    def test_prepare_routes_to_the_map_and_keeps_its_trace(self):
        ind = indicator()
        sources = [page('a', 'doc', 1, 'Evidence index register of source records. ' + FILLER * 4),
                   page('b', 'doc', 2, FILLER * 5)]
        frozen = {'pages': {spec.text_hash(sources[1]['text']): {'page_type': 'other', 'tags': [
            tag(ind['code'], 'direct', [ind['conditions'][0]['id']])]}}}
        policy = configured_policy_for_test()
        job = _prepare(ind, sources=sources, semantic_ranker=None, gemini=True, reviewed_evidence=None,
                       population='Students', reference_period='2023-24', scope=None, judgment='parts',
                       evidence_map=map_argument(policy, frozen), window_cache={'windows': {}, 'pages': {}})
        self.assertEqual(job['context'][0]['id'], 'b')
        self.assertEqual(job['evidence_map']['allocation'], packet.ALLOCATION)
        self.assertNotIn('evidence_map', job['payload'])

    def test_a_map_run_without_its_map_is_refused(self):
        with self.assertRaises(ValueError):
            map_argument(configured_policy_for_test(), None)
        with self.assertRaises(ValueError):
            map_argument({**configured_policy_for_test(), 'window_chars': 9999}, {'pages': {}})

    def test_map_lane_is_what_the_prompt_ceiling_shrinks(self):
        self.assertEqual(MapLane(60000).baseline_chars, 60000)


def configured_policy_for_test():
    with override_settings(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000,
                           CAPABILITY_EVIDENCE_LANE=False, CAPABILITY_FOLLOW_UP_SEARCH=False,
                           CAPABILITY_PROMPT_TOKEN_CEILING=None):
        return configured_policy()


class PolicyTests(SimpleTestCase):
    def test_map_mode_freezes_its_sizes(self):
        policy = configured_policy_for_test()
        self.assertEqual((policy['mode'], policy['allocation'], policy['cap_chars'], policy['fill_share']),
                         ('map', packet.ALLOCATION, 60000, '1/3'))

    @override_settings(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=100000)
    def test_the_input_bound_must_hold_twice_the_cap(self):
        with self.assertRaises(SemanticRetrievalUnavailable):
            configured_policy()

    @override_settings(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000,
                       CAPABILITY_MAP_CAP_CHARS=5000)
    def test_the_cap_is_bounded(self):
        with self.assertRaises(SemanticRetrievalUnavailable):
            configured_policy()


class FreezeTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        self.sources = [page('a', 'doc', 1, 'Alpha page text.'), page('b', 'doc', 2, 'Beta page text.'),
                        page('c', 'doc', 3, 'Alpha  page TEXT.'), page('d', 'doc', 4, '   ')]
        rubric, profiles, parts = spec.rubric_sources()
        self.version = spec.map_version('one', rubric, profiles, parts)

    def store(self, text, status=MapPage.Status.TAGGED, tags=()):
        MapPage.objects.create(text_hash=spec.text_hash(text), map_version=self.version, model='m', status=status,
                               page_type='other', tags=list(tags))

    def test_identical_pages_share_one_entry_and_coverage_counts_them_once(self):
        self.store('Alpha page text.', tags=[tag('AIQIF-C9.2', 'direct')])
        frozen = packet.freeze(self.sources, map_version=self.version, model='m')
        self.assertEqual(len(frozen['pages']), 1)
        self.assertEqual(frozen['coverage'], {'pages': 2, 'tagged': 1, 'failed': 0, 'skipped': 0, 'untagged': 1})

    def test_failed_rows_are_not_tags(self):
        self.store('Alpha page text.', status=MapPage.Status.FAILED)
        frozen = packet.freeze(self.sources, map_version=self.version, model='m')
        self.assertEqual(frozen['pages'], {})
        self.assertEqual(frozen['coverage']['failed'], 1)

    @override_settings(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, EVIDENCE_MAP_AI_MODEL='')
    def test_a_run_uses_the_sprints_map_and_records_it(self):
        from apps.scoring.capability.storage import map_for_run
        MapJob.objects.create(sprint=self.sprint, map_version=self.version, model='m', shape='one', spend_cap_usd=1)
        self.store('Beta page text.', tags=[tag('AIQIF-C9.2', 'direct')])
        policy, frozen = map_for_run(self.sprint, self.sources, configured_policy())
        self.assertEqual((policy['mode'], policy['map_version'], policy['map_model']), ('map', self.version, 'm'))
        self.assertEqual(policy['map_coverage']['tagged'], 1)
        self.assertEqual(list(frozen['pages']), [spec.text_hash('Beta page text.')])

    @override_settings(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, EVIDENCE_MAP_AI_MODEL='',
                       CAPABILITY_KEYWORD_CHARS=18000)
    def test_without_a_map_the_run_falls_back_to_wide_keyword_search(self):
        from apps.scoring.capability.storage import map_for_run
        policy, frozen = map_for_run(self.sprint, self.sources, configured_policy())
        self.assertIsNone(frozen)
        self.assertEqual((policy['mode'], policy['keyword_chars']), ('bm25', 60000))
        self.assertEqual(policy['map_fallback']['reason'], 'no_map')


@override_settings(CAPABILITY_EVIDENCE_LANE=False, AI_RATE_LIMIT_ENABLED=False)
class EvaluateTests(SimpleTestCase):
    def test_a_map_run_sends_the_tagged_page_first_and_traces_why(self):
        import json
        from apps.scoring.capability.evaluation import evaluate
        ind = indicator('AIQIF-C1.1')
        rubric = {**release(), 'indicators': [ind]}
        sources = [page(f'{n:08d}-0000-4000-8000-000000000000', '11111111-1111-4111-8111-111111111111', n,
                        f'Page {n}. ' + FILLER * 20) for n in range(1, 40)]
        target = sources[30]
        frozen = {'pages': {spec.text_hash(target['text']): {'page_type': 'other', 'tags': [
            tag(ind['code'], 'direct', [ind['conditions'][0]['id']], 'Page 31.')]}}}
        sent, traces = [], []

        class Judge:
            provider, model, base_url = 'anthropic', 'claude-haiku-5-5', None

            def extract_structured_data(self, **kwargs):
                payload = json.loads(kwargs['user_content'])
                sent.append(payload)
                return {'conditions': {c['id']: {'reason': 'Stand-in.', 'scope_supported': False,
                                                 'period_supported': False,
                                                 'findings': [{'part_id': p['id'], 'finding': 'not_found',
                                                               'citations': []} for p in c['parts']]}
                                       for c in payload['indicator']['conditions']}}

        policy = configured_policy_for_test()
        result = evaluate(sources, service=Judge(), population='All faculty', reference_period='2024-25', rubric=rubric,
                          max_calls=1, judgment='parts', retrieval_policy=policy, strict_errors=True,
                          evidence_map=frozen)
        packet_sent = sent[0]['sources']
        self.assertEqual(packet_sent[0]['id'], target['id'])
        self.assertLessEqual(sum(len(s['text']) for s in packet_sent), policy['cap_chars'])
        trace = result['traces'][0]
        self.assertEqual(trace['evidence_map']['windows'][0]['reasons'][0]['step'], 'direct')
        self.assertNotIn('direct', json.dumps(packet_sent))

    def test_the_prompt_ceiling_shrinks_the_map_cap(self):
        from apps.scoring.capability import prompt_ceiling
        ind = indicator('AIQIF-C1.1')
        sources = [page(f'p{n}', 'doc', n, f'Page {n}. ' + FILLER * 20) for n in range(1, 60)]
        ceiling = {'version': prompt_ceiling.VERSION, 'tokens': 12000, 'bytes_per_token': 2.6,
                   'short_ids': prompt_ceiling.SHORT_IDS_VERSION}
        job = _prepare(ind, sources=sources, semantic_ranker=None, gemini=True, reviewed_evidence=None,
                       population='Students', reference_period='2023-24', scope=None, judgment='parts', ceiling=ceiling,
                       evidence_map={'pages': {}, 'cap_chars': 60000}, window_cache={'windows': {}, 'pages': {}})
        audit = job['prompt_ceiling']
        self.assertEqual(audit['keyword_chars_before'], 60000)
        self.assertLess(audit['keyword_chars'], 60000)
        self.assertEqual(job['evidence_map']['cap_chars'], audit['keyword_chars'])
