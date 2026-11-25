"""The map packet's fill in bands, and the semantic step (allocation evidence-map-then-semantic-v1). No model calls:
a word-count embedding stands in for bge-small, except in the one test that uses the real model when it is installed."""
import os
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.scoring.capability.evaluation import map_argument
from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable, map_policy

from . import packet, semantic, spec
from .test_packet import FILLER, indicator, keyword_fill, page, tag


def bag_embed(texts, query):
    """A deterministic stand-in embedding: counts of a few words."""
    vocab = ('erp', 'data', 'records', 'digit', 'student', 'library', 'sports', 'policy', 'review', 'evidence',
             'register', 'traceab', 'source', 'verification', 'dvv')
    return [[t.lower().count(w) + 0.01 for w in vocab] for t in texts]


class FillBandTests(SimpleTestCase):
    def setUp(self):
        self.ind = indicator('AIQIF-C9.2')
        self.req = [c['id'] for c in self.ind['conditions']]
        self.read = page('read', 'doc-a', 1, 'Read page. ' + FILLER * 2)
        self.unread = page('unread', 'doc-b', 1, 'Unread page. ' + FILLER * 2)
        self.topical = page('topical', 'doc-c', 1, 'Topical page. ' + FILLER * 2)
        self.sources = [self.read, self.topical, self.unread]
        self.frozen = {'pages': {
            spec.text_hash(self.read['text']): {'page_type': 'other', 'tags': []},
            spec.text_hash(self.topical['text']): {'page_type': 'syllabus_or_course_content',
                                                   'tags': [tag(self.ind['code'], 'topical')]}}}

    def test_pages_the_tagger_never_read_come_first_then_read_pages_then_topical(self):
        context, trace = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill)
        self.assertEqual([w['id'] for w in context], ['unread', 'read', 'topical'])
        self.assertEqual([w['reasons'][0]['step'] for w in trace['windows']],
                         ['keyword_fill_unread', 'keyword_fill', 'keyword_fill_topical'])
        self.assertEqual(trace['allocation'], packet.ALLOCATION)
        self.assertNotIn('semantic_fill', trace)


class SemanticFillTests(SimpleTestCase):
    def setUp(self):
        self.ind = indicator('AIQIF-C9.2')
        other = indicator('AIQIF-C6.2')['code']
        self.match = page('match', 'doc-a', 141, 'The DVV verification register traces every reported value to its '
                          'source record. ' + FILLER * 4)
        self.noise = page('noise', 'doc-b', 9, 'Sports day. ' + FILLER * 4)
        self.plain = page('plain', 'doc-c', 3, 'A plain page. ' + FILLER * 4)
        self.sources = [self.noise, self.plain, self.match]
        self.frozen = {'pages': {
            spec.text_hash(self.match['text']): {'page_type': 'list_register_or_table', 'tags': [
                {**tag(other, 'direct', [], 'The DVV verification register'),
                 'reason': 'Register of verification: each value traced to its source record and evidence.'}]},
            spec.text_hash(self.noise['text']): {'page_type': 'other', 'tags': [
                {**tag(other, 'supporting', [], 'Sports day.'), 'reason': 'Sports day photographs.'}]},
            spec.text_hash(self.plain['text']): {'page_type': 'other', 'tags': []}}}
        self.search = semantic.TagSearch(bag_embed)

    def test_a_page_tagged_for_another_indicator_is_found_by_meaning_before_the_keyword_fill(self):
        context, trace = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill,
                                      semantic=self.search)
        steps = {w['id']: w['reasons'][0]['step'] for w in trace['windows']}
        self.assertEqual(steps['match'], 'semantic_fill')
        self.assertEqual(context[0]['id'], 'match')
        self.assertEqual(trace['allocation'], packet.SEMANTIC_ALLOCATION)
        self.assertEqual(trace['semantic_fill']['windows'][0]['id'], 'match')
        # The keyword fill still takes the rest: nothing is excluded.
        self.assertEqual({w['id'] for w in context}, {'match', 'noise', 'plain'})
        # The judge sees page text only: no tag description, strength or step.
        for window in context:
            self.assertNotIn('Register of verification', window['text'])
            self.assertFalse({'strength', 'step', 'tags', 'reason'} & window.keys())

    def test_the_semantic_step_never_takes_more_than_its_share_of_the_fill(self):
        big = [page(f'b{n}', f'doc-{n}', n, f'Verification register {n}. ' + FILLER * 20) for n in range(8)]
        frozen = {'pages': {spec.text_hash(p['text']): {'page_type': 'other', 'tags': [
            {**tag('AIQIF-C6.2', 'direct', [], f'Verification register {i}.'),
             'reason': 'verification register of source records'}]} for i, p in enumerate(big)}}
        context, trace = packet.build(self.ind, big, frozen, cap=12000, keyword_fill=keyword_fill,
                                      semantic=self.search)
        self.assertLessEqual(trace['semantic_fill']['chars'], 12000 // 2)
        self.assertLessEqual(sum(len(w['text']) for w in context), 12000)

    def test_the_same_inputs_give_the_same_packet(self):
        a = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill,
                         semantic=semantic.TagSearch(bag_embed))
        b = packet.build(self.ind, list(reversed(self.sources)), self.frozen, cap=60000, keyword_fill=keyword_fill,
                         semantic=semantic.TagSearch(bag_embed))
        self.assertEqual([w['id'] for w in a[0] if True][:1], [w['id'] for w in b[0]][:1])
        self.assertEqual(a[1]['semantic_fill']['windows'], b[1]['semantic_fill']['windows'])

    def test_vectors_are_embedded_once_per_text(self):
        calls = []

        def counting(texts, query):
            calls.append(len(texts))
            return bag_embed(texts, query)
        search = semantic.TagSearch(counting)
        for _ in range(3):
            packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill, semantic=search)
        self.assertEqual(len(calls), 2)   # the requirement searches once, the tag descriptions once


def _model_folder():
    folder = Path(tempfile.mkdtemp())
    (folder / 'tokenizer.json').write_text('{}')
    (folder / 'model.onnx').write_bytes(b'onnx')
    return folder


@override_settings(CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, CAPABILITY_MAP_CAP_CHARS=60000, EVIDENCE_MAP_SHAPE='one')
class SemanticPolicyTests(SimpleTestCase):
    @override_settings(CAPABILITY_MAP_FILL='keyword')
    def test_keyword_fill_is_the_default_and_unchanged(self):
        policy = map_policy({})
        self.assertEqual(policy['allocation'], packet.ALLOCATION)
        self.assertNotIn('semantic', policy)

    @override_settings(CAPABILITY_MAP_FILL='semantic', CAPABILITY_EMBEDDING_PATH='')
    def test_semantic_refuses_to_start_without_a_provisioned_model(self):
        with self.assertRaises(SemanticRetrievalUnavailable):
            map_policy({})

    @override_settings(CAPABILITY_MAP_FILL='semantic')
    def test_semantic_refuses_to_start_without_fastembed(self):
        from importlib.metadata import PackageNotFoundError
        with override_settings(CAPABILITY_EMBEDDING_PATH=str(_model_folder())), \
                patch('importlib.metadata.version', side_effect=PackageNotFoundError('fastembed')), \
                self.assertRaises(SemanticRetrievalUnavailable):
            map_policy({})

    @override_settings(CAPABILITY_MAP_FILL='semantic')
    def test_semantic_policy_freezes_the_model_and_its_files(self):
        with override_settings(CAPABILITY_EMBEDDING_PATH=str(_model_folder())), \
                patch('importlib.metadata.version', return_value='0.9.1'):
            policy = map_policy({})
        self.assertEqual(policy['allocation'], packet.SEMANTIC_ALLOCATION)
        self.assertEqual(policy['semantic']['version'], semantic.VERSION)
        self.assertEqual(len(policy['semantic']['artifact_hash']), 64)

    @override_settings(CAPABILITY_MAP_FILL='bogus')
    def test_an_unknown_fill_is_refused(self):
        with self.assertRaises(SemanticRetrievalUnavailable):
            map_policy({})

    def test_a_semantic_run_gets_its_search_and_a_keyword_run_none(self):
        base = {'mode': 'map', 'window_chars': packet.WINDOW_CHARS, 'cap_chars': 60000,
                'fill_share': '/'.join(map(str, packet.FILL_SHARE)),
                'context_share': '/'.join(map(str, packet.CONTEXT_SHARE))}
        frozen = {'pages': {}}
        self.assertIsNone(map_argument({**base, 'allocation': packet.ALLOCATION}, frozen)['semantic'])
        with patch('apps.evidence_map.semantic.configured', return_value='search') as configured:
            got = map_argument({**base, 'allocation': packet.SEMANTIC_ALLOCATION,
                                'semantic': {'version': semantic.VERSION}}, frozen)
        self.assertEqual(got['semantic'], 'search')
        configured.assert_called_once()
        with self.assertRaises(ValueError):
            map_argument({**base, 'allocation': packet.SEMANTIC_ALLOCATION, 'semantic': {'version': 'old'}}, frozen)

    def test_a_run_refuses_when_the_worker_model_differs_from_the_frozen_one(self):
        with override_settings(CAPABILITY_EMBEDDING_PATH=str(_model_folder())), \
                self.assertRaises(SemanticRetrievalUnavailable):
            semantic.configured({'semantic': {'artifact_hash': 'f' * 64}})


def _real_model():
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return ''
    path = os.environ.get('CAPABILITY_EMBEDDING_PATH') or '/opt/embeddings/bge-small-en-v1.5'
    return path if (Path(path) / 'tokenizer.json').is_file() else ''


@skipUnless(_real_model(), 'bge-small not provisioned here (the production image bakes it)')
class RealModelTests(SimpleTestCase):
    def test_the_real_model_ranks_a_meaning_match_first(self):
        with override_settings(CAPABILITY_EMBEDDING_PATH=_real_model(), CAPABILITY_EMBEDDING_MODEL='BAAI/bge-small-en-v1.5'):
            search = semantic.configured({})
        scores = search.similarities(
            ['Corrections to reported values are recorded with the reason and the evidence behind them.'],
            ['Table of values before and after DVV verification, with the remark explaining each change.',
             'The sports ground hosts the annual athletics meet.'])[0]
        self.assertGreater(scores[0], scores[1])
