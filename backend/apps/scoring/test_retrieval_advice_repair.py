"""Failure-oriented contracts for protected retrieval and item-level advice repair."""
import json
from importlib.util import find_spec
from types import SimpleNamespace
from unittest import skipUnless
from copy import deepcopy
from unittest.mock import Mock

import numpy as np
import jsonschema
from django.test import SimpleTestCase, override_settings

from .capability.evaluation import select_context
from .capability.semantic_retrieval import SemanticRanker, configured_policy
from .capability.recommendations import advice_schema, partition_advice
from .capability.recommendation_execution import tailor_batch
from apps.extraction.exceptions import AIResponseError
from .capability.execution import BudgetExceeded
from .capability.retrieval_diagnostics import gold_traces
from .retrieval_test_fixtures import synthetic_ranker
from .capability.evidence_retrieval import diverse
from .capability.passages import Passage


class ProtectedRetrievalTests(SimpleTestCase):
    def ranker(self):
        class Model:
            def passage_embed(self, texts, **kwargs):
                return [np.array([0., 1.]) if 'LEXICAL' in t else np.array([1., 0.]) for t in texts]
            def query_embed(self, text):
                return [np.array([1., 0.])]
        return synthetic_ranker(Model())

    def test_lexical_survives_adversarial_semantics_with_room_for_expansion(self):
        indicator = {'code': 'TEST', 'name': 'Broad AI theme', 'scoring_mode': 'independent_conditions',
                     'conditions': [{'id': 'c', 'text': 'Faculty completed accredited training.'}]}
        sources = [{'id': 'exact', 'text': 'LEXICAL Faculty completed accredited training. ' + 'x ' * 600}]
        sources += [{'id': f'noise-{n}', 'text': f'General background passage {n}. ' + 'y ' * 600} for n in range(80)]
        trace = {}
        ranker = self.ranker()
        ranker.baseline_chars = 1200
        selected = select_context(indicator, sources, max_chars=2400, semantic_ranker=ranker, diagnostics=trace)
        self.assertIn('exact', {s['id'] for s in selected})
        self.assertTrue(any(s['id'] != 'exact' for s in selected))
        self.assertLessEqual(sum(len(s['text']) for s in selected), 2400)
        self.assertEqual(trace['requirements'][0]['queries'][0], indicator['conditions'][0]['text'])
        self.assertLessEqual(trace['baseline_chars'], 1200)
        self.assertTrue(any(a['phase'] == 'semantic' and a['outcome'] == 'selected' for a in trace['packing_attempts']))
        self.assertTrue(all(a['used_chars'] + a['additional_chars'] <= 2400 for a in trace['packing_attempts']
                            if a['outcome'] == 'selected'))
        self.assertEqual(selected, select_context(indicator, sources[::-1], max_chars=2400, semantic_ranker=ranker))

    def test_duplicate_candidates_do_not_fill_fusion_slots(self):
        source = {'id': 'page', 'text': 'x' * 1200 + 'y' * 1200}
        rows = [Passage(source, start, end, 'prose', None, source['text'][start:end], 1)
                for start, end in ((0, 1200), (100, 1100), (200, 1000), (1200, 2400))]
        selected, rejected = diverse(list(range(len(rows))), rows)
        self.assertEqual([rows[n].start for n in selected], [0, 1200])
        self.assertEqual(len(rejected), 2)

    def test_multiple_requirements_obey_budget_nonoverlap_and_exact_text(self):
        indicator = {'code': 'TEST', 'name': 'Skills', 'scoring_mode': 'independent_conditions',
                     'conditions': [{'id': str(n), 'text': text} for n, text in enumerate(('Faculty training', 'Student access', 'Annual review'))]}
        sources = [{'id': str(n), 'text': ('Faculty training Student access Annual review. ' * 90)} for n in range(6)]
        for budget in (100, 500, 1800, 4500):
            selected = select_context(indicator, sources, max_chars=budget, semantic_ranker=self.ranker())
            self.assertLessEqual(sum(len(s['text']) for s in selected), budget)
            for n, a in enumerate(selected):
                for b in selected[n + 1:]:
                    if a['id'] == b['id']:
                        self.assertTrue(a['text_offset'] + len(a['text']) <= b['text_offset'] or
                                        b['text_offset'] + len(b['text']) <= a['text_offset'])
            self.assertTrue(all(s['text'] == next(x['text'] for x in sources if x['id'] == s['id'])[
                s['text_offset']:s['text_offset'] + len(s['text'])] for s in selected))

    @override_settings(CAPABILITY_RETRIEVAL_MODE='bm25', CAPABILITY_EMBEDDING_PATH='/installed-but-unused')
    def test_bm25_needs_no_model_even_with_model_directory_configured(self):
        self.assertEqual(configured_policy(), {'mode': 'bm25'})

    def test_gold_trace_separates_missing_window_from_bad_ranking(self):
        quote = 'Faculty completed accredited training with practical mentoring.'
        sources = [{'id': 'p', 'document_id': 'd', 'page_number': 1, 'text': quote}]
        rubric = {'indicators': [{'code': 'T', 'name': 'Training', 'scoring_mode': 'independent_conditions',
                   'conditions': [{'id': 'c', 'text': 'Faculty training'}]}]}
        gold = [{'condition_id': 'c', 'document_id': 'd', 'page': 1, 'quote': quote}]
        row = gold_traces(rubric, sources, gold, self.ranker(), 500)[0]
        self.assertEqual(row['loss_stage'], 'retrieved')
        self.assertEqual(row['queries'][0]['semantic_rank'], 1)
        sources[0]['text'] = 'A ' * 700
        gold[0]['quote'] = ('A ' * 300).strip()
        row = gold_traces(rubric, sources, gold, self.ranker(), 500)[0]
        self.assertEqual(row['loss_stage'], 'quote_not_in_candidate_body')
        self.assertIsNone(row['queries'][0]['semantic_rank'])

    @skipUnless(find_spec('tokenizers'), 'Optional local semantic dependency is not installed')
    def test_tokenizer_probe_detects_truncation_without_mutating_live_settings(self):
        from tokenizers import Tokenizer, models, pre_tokenizers
        tokenizer = Tokenizer(models.WordLevel({'[UNK]': 0, 'word': 1}, unk_token='[UNK]'))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        tokenizer.enable_truncation(max_length=5)
        ranker = SemanticRanker(SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer)))
        result = ranker.input_diagnostics(' '.join(['word'] * 20))
        self.assertTrue(result['truncated'])
        self.assertEqual(result['full_tokens'], 20)
        self.assertEqual(result['encoded_tokens'], 5)
        self.assertEqual(tokenizer.truncation['max_length'], 5)


class AdviceRepairTests(SimpleTestCase):
    def setUp(self):
        self.citation = {'source_id': 'page', 'quote': 'The faculty completed a documented training programme.'}
        self.actions = [{'id': cid, 'operation': 'gather_evidence', 'type': 'supply_evidence', 'state': 'unknown',
                         'requirement': 'Evidence of faculty training', 'citations': [self.citation],
                         'completion_evidence': 'Scoped supporting records'} for cid in ('a', 'b', 'c')]
        self.rows = [{'condition_id': a['id'], 'operation': a['operation'], 'steps': ['Locate the attendance record.'],
                      'suggested_role': 'Records custodian (suggested)', 'effort': 'small', 'dependencies': [],
                      'completion_evidence': 'Scoped attendance record', 'basis': [self.citation]} for a in self.actions]
        self.sources = [{'id': 'page', 'text': self.citation['quote']}]
        self.payload = {'actions': self.actions, 'sources': self.sources, 'established_strengths': []}
        self.inputs = {'population': 'Faculty', 'reference_period': '2026'}

    def execute(self, first, second=None):
        service = Mock()
        service.extract_structured_data.side_effect = [first, second]
        batch, metrics = tailor_batch(service, self.payload, self.inputs)
        return service, batch, metrics

    def test_only_invalid_item_is_repaired_and_valid_neighbours_unchanged(self):
        first = deepcopy(self.rows)
        first[1]['basis'] = [{'source_id': 'foreign', 'quote': 'Invented unsupported factual assertion.'}]
        original = deepcopy(first)
        service, batch, metrics = self.execute({'advice': first}, {'advice': [self.rows[1]]})
        self.assertEqual(first, original)
        self.assertTrue(all(r['origin'] == 'model_tailored' for r in batch))
        self.assertEqual(batch[0], {**self.rows[0], 'origin': 'model_tailored'})
        self.assertEqual(metrics['repaired_ids'], ['b'])
        repair = json.loads(service.extract_structured_data.call_args_list[1].kwargs['user_content'])
        self.assertEqual([a['id'] for a in repair['actions']], ['b'])
        self.assertEqual(service.extract_structured_data.call_count, 2)

    def test_failed_repair_falls_back_only_for_bad_item(self):
        first = deepcopy(self.rows)
        first[1]['operation'] = 'develop_and_verify'
        _, batch, metrics = self.execute({'advice': first}, {'advice': [first[1]]})
        self.assertEqual([r['origin'] for r in batch], ['model_tailored', 'deterministic_fallback', 'model_tailored'])
        self.assertEqual(batch[1]['operation'], 'gather_evidence')
        self.assertEqual(metrics['final_fallback_ids'], ['b'])
        self.assertIn('Request evidence', batch[1]['steps'][0])

    def test_good_batch_needs_no_repair(self):
        service, _, metrics = self.execute({'advice': self.rows})
        self.assertEqual(service.extract_structured_data.call_count, 1)
        self.assertFalse(metrics['repair_attempted'])

    def test_duplicate_or_missing_id_does_not_discard_other_rows(self):
        for rows in ([self.rows[0], self.rows[1], self.rows[1], self.rows[2]], [self.rows[0], self.rows[2]]):
            valid, errors = partition_advice({'advice': rows}, self.actions, sources=self.sources)
            self.assertEqual(set(valid), {'a', 'c'})
            self.assertEqual(set(errors), {'b'})

    def test_cycle_members_repaired_without_discarding_unrelated_item(self):
        first = deepcopy(self.rows)
        first[0]['dependencies'], first[1]['dependencies'] = ['b'], ['a']
        _, batch, metrics = self.execute({'advice': first}, {'advice': self.rows[:2]})
        self.assertEqual(set(metrics['initial_invalid']), {'a', 'b'})
        self.assertEqual(metrics['repaired_ids'], ['a', 'b'])
        self.assertEqual(batch[2], {**self.rows[2], 'origin': 'model_tailored'})

    def test_repair_cannot_create_cycle_discarding_valid_neighbour(self):
        first = deepcopy(self.rows)
        first[0]['dependencies'] = ['b']
        first[1]['operation'] = 'develop_and_verify'
        corrected = deepcopy(self.rows[1])
        corrected['dependencies'] = ['a']
        _, batch, metrics = self.execute({'advice': first}, {'advice': [corrected]})
        self.assertEqual(batch[0]['origin'], 'model_tailored')
        self.assertEqual(batch[1]['origin'], 'deterministic_fallback')
        self.assertEqual(metrics['final_fallback_ids'], ['b'])

    def test_repair_budget_exhaustion_keeps_good_rows(self):
        first = deepcopy(self.rows)
        first[1]['basis'] = []
        _, batch, metrics = self.execute({'advice': first}, BudgetExceeded())
        self.assertEqual(metrics['final_fallback_ids'], ['b'])
        self.assertEqual(batch[0]['origin'], 'model_tailored')

    def test_malformed_envelope_can_be_repaired_once(self):
        _, batch, metrics = self.execute({'wrong': []}, {'advice': self.rows})
        self.assertEqual(len(metrics['initial_invalid']), 3)
        self.assertEqual(len(metrics['repaired_ids']), 3)
        self.assertTrue(all(r['origin'] == 'model_tailored' for r in batch))

    def test_schema_restricts_requirement_source_and_dependency_ids(self):
        schema = advice_schema(self.actions, self.sources)
        jsonschema.validate({'advice': self.rows}, schema)
        for field, value in (('condition_id', 'foreign'), ('basis', [{'source_id': 'foreign', 'quote': 'invented'}]),
                             ('dependencies', ['foreign'])):
            rows = deepcopy(self.rows)
            rows[0][field] = value
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate({'advice': rows}, schema)

    def test_repair_cannot_replace_already_valid_item(self):
        first = deepcopy(self.rows)
        first[1]['basis'] = []
        replacement = deepcopy(self.rows[0])
        replacement['steps'] = ['Overwrite the accepted item.']
        _, batch, _ = self.execute({'advice': first}, {'advice': [replacement, self.rows[1]]})
        self.assertEqual(batch[0]['steps'], self.rows[0]['steps'])

    def test_unparseable_response_gets_one_repair_and_then_labelled_fallback(self):
        service, batch, metrics = self.execute(AIResponseError('Malformed response'), AIResponseError('Still malformed'))
        self.assertEqual(service.extract_structured_data.call_count, 2)
        self.assertTrue(all(r['origin'] == 'deterministic_fallback' for r in batch))
        self.assertEqual(len(metrics['final_fallback_ids']), 3)
