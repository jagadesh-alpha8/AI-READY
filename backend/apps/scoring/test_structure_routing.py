"""Structure routing: NAAC sections, duplicate pages, routed picks and the per-document cap.

The invariant that matters most: with no structure (the default), packets are exactly what they were.
"""
from django.test import SimpleTestCase, override_settings

from apps.scoring.capability import structure as st
from apps.scoring.capability.evaluation import select_balanced_context, select_context
from apps.scoring.capability.semantic_retrieval import configured_policy

FILLER = 'Students attend lectures and laboratory sessions across departments every semester. ' * 30


def page(sid, doc, number, text):
    return {'id': sid, 'document_id': doc, 'page_number': number, 'text': text, 'retrieval_hints': []}


def indicator(code='AIQIF-C8.1'):
    return {'code': code, 'name': 'Digital Services and AI-Enabled Operations', 'scoring_mode': 'independent_conditions',
            'conditions': [{'id': f'{code}.F1', 'text': 'An institutional digital service has a defined purpose.'},
                           {'id': f'{code}.F2', 'text': 'A responsible owner is assigned to that service.'}]}


SSR = [
    page('s1', 'ssr', 1, 'Executive summary of the institution.\n' + FILLER),
    page('s2', 'ssr', 2, '6.2.3\nImplementation of e-governance in areas of operation\nResponse:\n'
                         'The ERP digital service purpose is admissions and finance; the registrar is the owner.\n' + FILLER),
    page('s3', 'ssr', 3, 'continued e-governance narrative, the service owner reviews the ERP.\n' + FILLER),
    page('s4', 'ssr', 4, '6.3.1\nWelfare measures for teaching staff\nResponse:\nStaff welfare.\n' + FILLER),
    page('s5', 'ssr', 5, '7.3.1\nInstitutional distinctiveness\nResponse:\nDistinct.\n6.ANNEXURE\n'
                         '[Table 1 on page 5 -- columns: 1.Metrics | Level Deviations]\n1.Metrics: 2.6.2 | before DVV\n'),
]


class SectionTests(SimpleTestCase):
    def test_sections_carry_across_pages_and_ignore_backward_references(self):
        sections = st.sections(SSR)
        self.assertEqual(sections['s1'], [])
        self.assertEqual([x.metric for _, _, x in sections['s2']], ['6.2.3'])
        self.assertTrue(sections['s2'][0][2].title.startswith('Implementation of e-governance'))
        # Page 3 has no heading: it continues 6.2.3.
        self.assertEqual([(a, x.metric) for a, _, x in sections['s3']], [(0, '6.2.3')])
        # The annexure opens a section; the backward metric number inside it does not.
        self.assertEqual([x.metric for _, _, x in sections['s5']], ['7.3.1', 'annexure'])

    def test_title_continues_onto_next_page_and_skips_footer(self):
        pages = [page('a', 'd', 1, 'Some text\n6.2.2\nPage 139/187 07-08-2024 09:21:42'),
                 page('b', 'd', 2, 'Effectiveness of institutional bodies\nResponse:\nYes.')]
        title = st.sections(pages)['a'][0][2].title
        self.assertNotIn('Page 139', title)
        self.assertIn('Effectiveness of institutional bodies', title)

    def test_routes_match_titles_not_numbers(self):
        sections = st.sections(SSR)
        routed = st.routed_spans(sections, 'AIQIF-C8.1')
        self.assertIn('s2', routed)
        self.assertIn('s3', routed)
        self.assertNotIn('s4', routed)
        self.assertEqual(set(st.ROUTES), {f'AIQIF-C{c}.{i}' for c in range(1, 10) for i in range(1, 5)})


class DeduplicateTests(SimpleTestCase):
    def test_identical_pages_drop_but_any_difference_is_kept(self):
        copy = [page('c2', 'copy', 2, SSR[1]['text'].replace(' ', '  ')),
                page('c3', 'copy', 3, SSR[2]['text'] + ' one extra sentence.')]
        kept, dropped = st.deduplicate(SSR + copy)
        # The longer document keeps its page; the two-page extract's identical page is dropped.
        self.assertEqual(dropped, [{'id': 'c2', 'duplicate_of': 's2', 'page': ('copy', 2), 'kept_page': ('ssr', 2)}])
        self.assertEqual(st.page_aliases({'dropped': dropped}), {('ssr', 2): [('copy', 2)]})
        self.assertIn('c3', [s['id'] for s in kept])
        self.assertEqual(len(kept), len(SSR) + 1)

    def test_order_independent(self):
        a, _ = st.deduplicate(SSR + SSR[:0])
        b, _ = st.deduplicate(list(reversed(SSR)))
        self.assertEqual(sorted(s['id'] for s in a), sorted(s['id'] for s in b))


class ReviewedClaimAliasTests(SimpleTestCase):
    def test_claim_on_a_dropped_copy_attaches_to_the_kept_page(self):
        from apps.scoring.capability.reviewed_evidence import for_context
        quote = 'The ERP digital service purpose is admissions and finance'
        claim = {'id': 'c1', 'revision': '1', 'institution_id': 'i', 'sprint_id': 's', 'attribute': 'erp', 'label': 'ERP',
                 'value': 'admissions and finance', 'original_value': 'admissions and finance', 'value_origin': 'extracted',
                 'scope': {'period': '2023-24', 'population': ['Institution'], 'unit': '', 'includes': [], 'excludes': [],
                           'sources': {}, 'stated': {}},
                 'kind': 'context', 'disposition': 'extracted',
                 'verification': {'outcome': 'verified', 'grounding': 'exact', 'validation': 'pass',
                                  'automation': 'would_auto_verify', 'source_review_required': False},
                 'source': {'document_id': 'copy', 'version': 1, 'current': True, 'page': '2', 'quote': quote},
                 'original_source': {'document_id': 'copy', 'page': '2', 'quote': quote}, 'decisions': []}
        ledger = {'claims': [claim], 'issues': []}
        window = [{**SSR[1], 'text_offset': 0}]
        without, with_alias = {}, {}
        for_context(ledger, window, diagnostics=without)
        for_context(ledger, window, diagnostics=with_alias, aliases={('ssr', 2): [('copy', 2)]})
        self.assertFalse(without['claims'][0]['attached'])
        self.assertTrue(with_alias['claims'][0]['attached'])
        self.assertEqual(with_alias['claims'][0]['current_references'][0]['source_id'], 's2')


class DeduplicateOnlyTests(SimpleTestCase):
    def test_without_routing_there_are_no_sections_and_no_cap(self):
        crowd = [page(f'q{n}', 'aqar', n, ('e-governance digital service purpose owner ERP registrar ' * 40))
                 for n in range(1, 9)]
        sources = SSR + crowd
        structure = st.build(sources, routing=False)
        self.assertEqual(structure['sections'], {})
        self.assertEqual(select_balanced_context(indicator(), structure['sources'], max_chars=6000, structure=structure),
                         select_balanced_context(indicator(), structure['sources'], max_chars=6000))


class SelectionTests(SimpleTestCase):
    def test_default_packet_is_unchanged(self):
        before = select_balanced_context(indicator(), SSR, max_chars=6000)
        self.assertEqual(before, select_balanced_context(indicator(), SSR, max_chars=6000, structure=None))

    def test_single_document_keeps_its_full_budget(self):
        structure = st.build(SSR)
        plain = select_balanced_context(indicator(), SSR, max_chars=6000)
        routed = select_balanced_context(indicator(), structure['sources'], max_chars=6000, structure=structure)
        self.assertEqual(sum(len(w['text']) for w in plain), sum(len(w['text']) for w in routed))

    def test_document_cap_leaves_room_for_another_document(self):
        crowd = [page(f'q{n}', 'aqar', n, ('e-governance digital service purpose owner ERP registrar ' * 40))
                 for n in range(1, 9)]
        sources = SSR + crowd
        plain = select_balanced_context(indicator(), sources, max_chars=6000)
        structure = st.build(sources)
        capped = select_balanced_context(indicator(), structure['sources'], max_chars=6000, structure=structure)
        share = lambda packet, doc: sum(len(w['text']) for w in packet if w['document_id'] == doc)
        self.assertGreater(share(capped, 'ssr'), share(plain, 'ssr'))
        self.assertIn('s2', {w['id'] for w in capped})
        # Every selected window is an exact slice of its source.
        lookup = {s['id']: s['text'] for s in sources}
        for w in capped:
            self.assertEqual(lookup[w['id']][w['text_offset']:w['text_offset'] + len(w['text'])], w['text'])

    def test_structure_is_rejected_outside_independent_conditions(self):
        legacy = {**indicator(), 'scoring_mode': 'legacy'}
        with self.assertRaises(ValueError):
            select_context(legacy, SSR, max_chars=6000, structure=st.build(SSR))


class EvaluateTests(SimpleTestCase):
    def test_frozen_structure_runs_and_a_mismatched_version_is_refused(self):
        from apps.scoring.test_indicator_concurrency import ContentKeyed, SOURCE
        from apps.scoring.capability.evaluation import evaluate
        common = dict(service=ContentKeyed(), population='All programmes', reference_period='2025-26')
        plain = evaluate([SOURCE], **common)
        routed = evaluate([SOURCE], retrieval_policy={'mode': 'bm25', 'structure': st.VERSION}, **common)
        self.assertEqual(plain['decisions'], routed['decisions'])
        deduplicated = evaluate([SOURCE, {**SOURCE, 'id': 'document-b:1'}],
                                retrieval_policy={'mode': 'bm25', 'deduplicate': st.DEDUPLICATE_VERSION}, **common)
        self.assertEqual(plain['decisions'], deduplicated['decisions'])
        with self.assertRaises(ValueError):
            evaluate([SOURCE], retrieval_policy={'mode': 'bm25', 'structure': 'naac-metric-routing-v0'}, **common)
        with self.assertRaises(ValueError):
            evaluate([SOURCE], retrieval_policy={'mode': 'bm25', 'deduplicate': 'other'}, **common)


class PolicyTests(SimpleTestCase):
    @override_settings(CAPABILITY_STRUCTURE_ROUTING=False, CAPABILITY_DEDUPLICATE_PAGES=False, CAPABILITY_RETRIEVAL_ALLOCATION='')
    def test_off_by_default_policy_has_no_structure(self):
        self.assertEqual(configured_policy('bm25'), {'mode': 'bm25'})

    @override_settings(CAPABILITY_STRUCTURE_ROUTING=True, CAPABILITY_DEDUPLICATE_PAGES=True, CAPABILITY_RETRIEVAL_ALLOCATION='')
    def test_on_policy_freezes_the_versions(self):
        self.assertEqual(configured_policy('bm25'), {'mode': 'bm25', 'structure': st.VERSION,
                                                     'deduplicate': st.DEDUPLICATE_VERSION})

    @override_settings(CAPABILITY_RETRIEVAL_ALLOCATION='protected-baseline-then-discovery-wide-v1')
    def test_wide_allocation_needs_hybrid(self):
        from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable
        with self.assertRaises(SemanticRetrievalUnavailable):
            configured_policy('bm25')

    @override_settings(CAPABILITY_RETRIEVAL_ALLOCATION='something-else')
    def test_unknown_allocation_is_refused(self):
        from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable
        with self.assertRaises(SemanticRetrievalUnavailable):
            configured_policy('bm25')


class EmbeddingCacheTests(SimpleTestCase):
    def test_vectors_round_trip_and_are_reused_by_the_ranker(self):
        import tempfile
        import numpy as np
        from apps.scoring.capability.semantic_retrieval import EmbeddingCache, SemanticRanker

        class Model:
            model_name = 'test'

            def __init__(self):
                self.embedded = []

            def passage_embed(self, texts, batch_size=32):
                self.embedded.extend(texts)
                return [np.array([len(t), 1.0, 2.0], dtype=np.float32) for t in texts]

            def query_embed(self, text):
                return [np.array([1.0, 0.0, 0.0], dtype=np.float32)]

        class Passage:
            def __init__(self, text):
                self.embedding_text, self.text = text, text

        with tempfile.TemporaryDirectory() as tmp:
            cache = EmbeddingCache(tmp, 'a' * 64)
            cache.put_many([('alpha passage text', [1.0, 2.0, 3.0])])
            self.assertEqual(cache.get_many(['alpha passage text', 'missing'])['alpha passage text'].tolist(), [1.0, 2.0, 3.0])
            passages = [Passage('Students use the ERP portal for admission records.'),
                        Passage('The library has twenty thousand titles on open shelves.')]
            first_model, second_model = Model(), Model()
            first = SemanticRanker(first_model, cache=EmbeddingCache(tmp, 'a' * 64)).similarities(passages, ['erp'])
            second = SemanticRanker(second_model, cache=EmbeddingCache(tmp, 'a' * 64)).similarities(passages, ['erp'])
            self.assertEqual(len(first_model.embedded), 2)
            self.assertEqual(second_model.embedded, [])  # every passage came from the cache
            self.assertTrue(np.array_equal(first[0], second[0]))
            # A different model artifact never reads these vectors.
            self.assertEqual(EmbeddingCache(tmp, 'b' * 64).get_many(['alpha passage text']), {})


class RepeatSkipTests(SimpleTestCase):
    """Repeat skipping: a window that mostly repeats one chosen from another document gives way to new text."""
    REPEATED = ('The ERP digital service purpose is admissions and finance; the registrar is the owner of the '
                'e-governance service and reviews it each term. ')
    NEW = 'A separate helpdesk digital service has its own purpose: student grievances; the dean of students is owner. '

    def sources(self):
        return [page('s1', 'ssr', 1, self.REPEATED * 12),
                page('a1', 'aqar', 1, self.REPEATED * 12 + ' restated'),   # the AQAR restating the SSR
                page('n1', 'minutes', 1, self.NEW * 12)]

    def test_off_by_default_and_without_policy_key(self):
        sources = self.sources()
        self.assertFalse(st.build(sources)['repeat_skip'])
        plain = select_balanced_context(indicator(), sources, max_chars=2400)
        with_structure = select_balanced_context(indicator(), sources, max_chars=2400,
                                                 structure=st.build(sources, deduplicate_pages=False, routing=False))
        self.assertEqual(plain, with_structure)

    def test_cross_document_repeat_gives_way_to_new_text(self):
        sources = self.sources()
        plain = select_balanced_context(indicator(), sources, max_chars=2400)
        structure = st.build(sources, deduplicate_pages=False, routing=False, repeat_skip=True)
        skipped = select_balanced_context(indicator(), sources, max_chars=2400, structure=structure)
        documents = lambda packet: {w['document_id'] for w in packet}
        self.assertEqual(documents(plain), {'ssr', 'aqar'})      # the restatement crowds out the minutes
        self.assertEqual(documents(skipped), {'ssr', 'minutes'})
        lookup = {s['id']: s['text'] for s in sources}
        for w in skipped:
            self.assertEqual(lookup[w['id']][w['text_offset']:w['text_offset'] + len(w['text'])], w['text'])

    def test_same_document_text_is_never_skipped(self):
        candidate = st.words(self.REPEATED)
        self.assertFalse(st.repeats(candidate, 'ssr', [('ssr', candidate)]))
        self.assertTrue(st.repeats(candidate, 'aqar', [('ssr', candidate)]))
        self.assertFalse(st.repeats(st.words(self.NEW), 'minutes', [('ssr', candidate)]))
        self.assertFalse(st.repeats(frozenset(), 'x', [('ssr', candidate)]))

    def test_policy_key_and_version(self):
        with override_settings(CAPABILITY_REPEAT_SKIP=True):
            self.assertEqual(configured_policy('bm25')['repeat_skip'], st.REPEAT_SKIP_VERSION)
        with override_settings(CAPABILITY_REPEAT_SKIP=False):
            self.assertNotIn('repeat_skip', configured_policy('bm25'))

    def test_a_different_frozen_version_is_refused(self):
        from apps.scoring.capability.evaluation import evaluate
        with self.assertRaisesRegex(ValueError, 'repeat-skip version'):
            evaluate(self.sources(), service=None, population='Students', reference_period='2024',
                     retrieval_policy={'mode': 'bm25', 'repeat_skip': 'other-v0'}, max_calls=0)
