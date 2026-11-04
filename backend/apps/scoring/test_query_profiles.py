"""Evidence-seeking retrieval descriptions must not become new assessment criteria."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from .capability.engine import release
from .capability.query_profiles import validate_profiles, profile_metadata, evidence_query
from .capability.evidence_queries import requirement_queries
from .capability.semantic_retrieval import ranker_for, SemanticRetrievalUnavailable, FUSION
from .capability.evidence_retrieval import retrieve_evidence
from .retrieval_test_fixtures import synthetic_ranker
from .test_passage_architecture import Model


class QueryProfileTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.pack = json.loads(Path(__file__).with_name('capability').joinpath('retrieval_profiles_v1.json').read_text())
        self.ranker = synthetic_ranker(Model())

    def test_all_216_assertions_have_distinct_reviewable_record_descriptions(self):
        profiles = validate_profiles(self.pack, self.rubric)
        self.assertEqual(len(profiles), 216)
        self.assertEqual(len({p['query'] for p in profiles.values()}), 216)
        self.assertTrue(all(p['query'] != p['assertion'] for p in profiles.values()))

    def test_profile_and_assertion_both_reach_encoder_queries_without_slot_starvation(self):
        for indicator in self.rubric['indicators']:
            for condition, request in zip(indicator['conditions'], requirement_queries(indicator, self.ranker)):
                self.assertEqual(len(request['queries']), 2)
                self.assertEqual(request['query_roles'][0], 'evidence_records')
                self.assertEqual(request['queries'][0], self.pack['profiles'][condition['id']]['query'])
                self.assertIn(request['query_roles'][1], ('assertion', 'contextual_assertion'))
                self.assertTrue(all(len(self.ranker.token_offsets(q)) <= 192 for q in request['queries']))

    def test_referential_assertion_retains_context_and_its_evidence_query(self):
        request = requirement_queries(self.rubric['indicators'][0], self.ranker)[1]
        self.assertIn('appointment order', request['queries'][0])
        self.assertIn('approved institutional plan', request['queries'][1])
        self.assertIn('responsible owner', request['queries'][1])

    def test_stale_missing_extra_and_duplicate_profiles_are_rejected(self):
        for mode in ('stale', 'missing', 'extra', 'duplicate'):
            pack = deepcopy(self.pack)
            keys = list(pack['profiles'])
            if mode == 'stale':
                pack['profiles'][keys[0]]['assertion'] = 'An old requirement.'
            elif mode == 'missing':
                pack['profiles'].pop(keys[0])
            elif mode == 'extra':
                pack['profiles']['unknown'] = pack['profiles'][keys[0]]
            else:
                pack['profiles'][keys[1]]['query'] = pack['profiles'][keys[0]]['query']
            with self.assertRaises(ValueError):
                validate_profiles(pack, self.rubric)

    def test_canonical_requirement_cannot_silently_use_a_stale_profile(self):
        with self.assertRaises(ValueError):
            evidence_query({'id': 'AIQIF-C1.1.F1', 'text': 'Changed assertion without profile review.'})

    def test_enabling_profiles_do_not_require_ai_adoption_or_product_specific_records(self):
        ids = ('AIQIF-C1.3.F1', 'AIQIF-C4.4.F1', 'AIQIF-C6.1.F1', 'AIQIF-C9.1.F1', 'AIQIF-C9.2.F1')
        for cid in ids:
            query = self.pack['profiles'][cid]['query'].lower()
            self.assertNotIn('artificial intelligence', query)
            self.assertNotIn(' ai ', query)
            self.assertNotIn('ai-ready', query)
            self.assertNotIn('cri', query)
        self.assertIn('desktop workstations', self.pack['profiles']['AIQIF-C6.1.F1']['query'])
        self.assertIn('IQAC', self.pack['profiles']['AIQIF-C9.1.F1']['query'])

    def test_profiles_do_not_mutate_rubric_or_add_scoring_conditions(self):
        before = deepcopy(self.rubric)
        for indicator in self.rubric['indicators']:
            requirement_queries(indicator, self.ranker)
        self.assertEqual(self.rubric, before)
        self.assertEqual(len([c for i in self.rubric['indicators'] for c in i['conditions']]), 216)

    def test_record_aliases_affect_retrieval_and_diagnostic_scores(self):
        indicator = next(i for i in self.rubric['indicators'] if i['code'] == 'AIQIF-C6.1')
        sources = [{'id': 'access', 'text': 'The computer centre provides desktop workstations and library computers to students.'},
                   {'id': 'topic', 'text': 'Artificial intelligence innovation strategy and research vision.'}]
        trace = {}
        selected = retrieve_evidence(indicator, sources, self.ranker, max_chars=500, diagnostics=trace)
        self.assertIn('access', {s['id'] for s in selected})
        requirement = trace['requirements'][0]
        relevant = next(n for n, p in enumerate(trace['passages']) if p.source['id'] == 'access')
        self.assertGreater(requirement['profile_scores'][relevant], requirement['contextual_scores'][relevant])
        self.assertEqual(requirement['query_roles'][0], 'evidence_records')
        self.assertTrue(all(query in self.ranker.queries for query in requirement['queries']))

    @override_settings(CAPABILITY_EMBEDDING_MODEL='BAAI/bge-small-en-v1.5')
    def test_frozen_profile_checksum_mismatch_is_explicit_and_loads_no_model(self):
        from .capability.semantic_retrieval import query_instruction
        policy = {'mode': 'hybrid', 'fusion': FUSION, 'representation': 'token-source-spans-v1',
            'target_tokens': 240, 'query_policy': 'evidence-record-profiles-1',
            'query_instruction': query_instruction('BAAI/bge-small-en-v1.5'),
            'lexical_weight': 2, 'semantic_weight': 1,
            'allocation': 'protected-baseline-then-discovery-v1', 'baseline_chars': 18000,
            'expansion_chars': 6000, 'expansion_filter': 'instruction-heading-only-v2',
            **profile_metadata()}
        policy['query_profiles_hash'] = 'wrong-checksum'
        with patch('apps.scoring.capability.semantic_retrieval._model', side_effect=AssertionError('Must not load a model')):
            with self.assertRaises(SemanticRetrievalUnavailable):
                ranker_for(policy)

    def test_profiled_lexical_ablation_never_requests_vectors(self):
        class NoEmbeddings(Model):
            def passage_embed(self, texts, **kwargs):
                raise AssertionError('Lexical ablation must not encode passages')
            def query_embed(self, text):
                raise AssertionError('Lexical ablation must not encode queries')
        ranker = synthetic_ranker(NoEmbeddings())
        indicator = next(i for i in self.rubric['indicators'] if i['code'] == 'AIQIF-C6.1')
        sources = [{'id': 'access', 'text': 'Computer centre desktop workstations and ICT facilities are available to students.'}]
        selected = retrieve_evidence(indicator, sources, ranker, include_semantic=False)
        self.assertEqual([s['id'] for s in selected], ['access'])
        self.assertEqual(ranker.stats['embedded_passages'], 0)
