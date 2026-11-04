"""Contracts for current evidence, bounded review controls, and local semantic retrieval."""
import json
import os
from copy import deepcopy
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase, override_settings
from apps.documents.models import Document
from apps.extraction.models import ExtractionJob, DocumentPage
from apps.extraction.services.pipeline import ExtractionPipeline
from apps.facts.models import ExtractedFact, FactAIQIFMapping
from apps.facts.lifecycle import reconcile_extraction
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability.citations import expand_citation
from .capability.evaluation import validate_decisions, select_context
from .capability.reviewed_evidence import for_context, citation_issue, snapshot
from .capability.semantic_retrieval import SemanticRanker, configured_policy, ranker_for
from .retrieval_test_fixtures import synthetic_ranker


class FactLifecycleTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='Synthetic College'))
        self.doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self.old = ExtractedFact.objects.create(sprint=self.sprint, document=self.doc,
            source_document=self.doc, field_key='faculty', field_name='Faculty', value=42,
            source_page='1', source_snippet='The faculty count is 42.')
        self.job = ExtractionJob.objects.create(sprint=self.sprint, document=self.doc, status='running', completeness='complete')
        self.pages = {'pages': [{'page_number': 1, 'text': 'The faculty count is 43.'}]}

    def test_complete_empty_extraction_retires_machine_fact_and_mapping_from_active_views(self):
        FactAIQIFMapping.objects.create(fact=self.old, indicator_code='AIQIF-C4.1', criterion='aiqif_c4',
            reason='Synthetic', confidence=.9, status='mapped')
        result = reconcile_extraction(self.job, set(), self.pages)
        self.assertEqual(result['retired'], 1)
        self.assertFalse(self.sprint.facts.exists())
        self.assertFalse(FactAIQIFMapping.objects.exists())
        self.assertTrue(FactAIQIFMapping.all_objects.exists())
        self.assertEqual(snapshot(self.sprint)['claims'], [])
        self.assertIsNotNone(ExtractedFact.all_objects.get(pk=self.old.pk).retired_at)

    def test_partial_or_failed_run_does_not_retire_existing_facts(self):
        self.job.completeness = 'partial'
        self.job.save()
        reconcile_extraction(self.job, set(), self.pages)
        self.assertTrue(ExtractedFact.objects.filter(pk=self.old.pk).exists())
        self.job.completeness, self.job.status = 'complete', 'failed'
        self.job.save()
        reconcile_extraction(self.job, set(), self.pages)
        self.assertTrue(ExtractedFact.objects.filter(pk=self.old.pk).exists())

    def test_recovered_worker_cannot_retire_the_replacement_workers_observations(self):
        from apps.extraction.exceptions import ExtractionSuperseded
        self.job.task_token = 'old-worker'
        self.job.celery_task_id = 'replacement-worker'
        self.job.save()
        with self.assertRaises(ExtractionSuperseded):
            reconcile_extraction(self.job, set(), self.pages)
        self.assertTrue(ExtractedFact.objects.filter(pk=self.old.pk).exists())

    def test_human_decision_is_preserved_and_changed_support_is_flagged(self):
        self.old.status = 'confirmed'
        self.old.save()
        reconcile_extraction(self.job, set(), self.pages)
        self.old.refresh_from_db()
        self.assertEqual((self.old.value, self.old.status), (42, 'confirmed'))
        self.assertTrue(self.old.source_review_required)
        self.assertIsNone(self.old.retired_at)
        self.assertTrue(snapshot(self.sprint)['claims'][0]['verification']['source_review_required'])
        self.pages['pages'][0]['text'] = 'The faculty count is 42.'
        reconcile_extraction(self.job, set(), self.pages)
        self.old.refresh_from_db()
        self.assertFalse(self.old.source_review_required)

    def test_reappearance_reactivates_the_same_machine_observation(self):
        reconcile_extraction(self.job, set(), self.pages)
        incoming = {'field_key': 'faculty', 'field_name': 'Faculty', 'value': 42,
                    'source_page': '1', 'source_snippet': 'The faculty count is 42.'}
        ExtractionPipeline._persist_facts(self.job, [incoming])
        active = ExtractedFact.objects.get()
        self.assertEqual(active.pk, self.old.pk)
        self.assertIsNone(active.retired_at)
        self.assertIn(active.pk, self.job._seen_fact_ids)

    def test_reviewer_corrected_source_in_another_document_is_not_flagged(self):
        other = Document.objects.create(sprint=self.sprint)
        self.old.source_document, self.old.status = other, 'corrected'
        self.old.save()
        reconcile_extraction(self.job, set(), self.pages)
        self.old.refresh_from_db()
        self.assertFalse(self.old.source_review_required)
        self.assertIsNone(self.old.retired_at)


class ExactFragmentTests(SimpleTestCase):
    left = 'The governing council approved the policy.'
    right = 'The review committee checks outcomes annually.'

    def test_joined_fragments_become_separate_exact_citations(self):
        text = self.left + ' Additional administrative detail. ' + self.right
        expanded = expand_citation({'source_id': 's', 'quote': self.left + ' ... ' + self.right}, [{'text': text}])
        self.assertEqual([c['quote'] for c in expanded], [self.left, self.right])

    def test_fragments_cannot_cross_windows_or_reverse_order(self):
        citation = {'source_id': 's', 'quote': self.left + ' … ' + self.right}
        for windows in ([{'text': self.left}, {'text': self.right}], [{'text': self.right + self.left}]):
            with self.assertRaises(ValueError):
                expand_citation(citation, windows)

    def test_fragment_cannot_hide_rejected_alternative_from_validation(self):
        from .test_context_diagnostics import fixture, indicator, REJECTED
        _, context, ledger = fixture()
        item = indicator()
        source = context[1]
        # Each fragment is exact; local review controls must still reject it.
        first = source['text'].split(REJECTED)[0].strip()
        row = {'condition_id': item['conditions'][0]['id'], 'state': 'met', 'reason': 'Synthetic',
               'scope_supported': True, 'period_supported': True,
               'citations': [{'source_id': source['id'], 'quote': first + ' ... ' + REJECTED}]}
        outcome = next(r for r in validate_decisions(item, {'conditions': [row]}, context, reviewed_evidence=ledger)
                       if r['condition_id'] == row['condition_id'])
        self.assertEqual(outcome['state'], 'unknown')
        self.assertIn('rejected', outcome['reason'])


class BoundedConflictTests(SimpleTestCase):
    def test_many_off_window_alternatives_are_summarized_and_full_guard_is_preserved(self):
        from .test_context_diagnostics import corpus
        sources, ledger = corpus(200)
        context = [{**sources[0], 'text': sources[0]['text'][:500], 'text_offset': 0}]
        before = deepcopy(ledger)
        packet = for_context(ledger, context)
        self.assertLessEqual(len(json.dumps(packet)), 24000)
        self.assertTrue(any(i['omitted_alternatives'] > 100 for i in packet['issues']))
        self.assertEqual(ledger, before)
        anchored = next(c for c in ledger['claims'] if c['id'] == 'c-0-students')
        citations = [{'source_id': sources[0]['id'], 'quote': anchored['source']['quote']}]
        self.assertTrue(citation_issue(citations, ledger, sources, state='met'))


class HybridRetrievalTests(SimpleTestCase):
    def test_local_fusion_keeps_both_candidate_routes_and_does_not_duplicate_sources(self):
        import numpy as np
        class Model:
            def passage_embed(self, texts, **kwargs):
                return [np.array([1., 0.]) if 'pedagogical' in t else np.array([0., 1.]) for t in texts]
            def query_embed(self, text):
                return [np.array([1., 0.])]
        ranker = synthetic_ranker(Model())
        indicator = {'code': 'TEST', 'name': 'Teacher training', 'scoring_mode': 'independent_conditions',
                     'conditions': [{'text': 'Teachers receive training.'}]}
        sources = [{'id': 'semantic', 'text': 'Pedagogical development workshops. '.lower()},
                   {'id': 'lexical', 'text': 'Teachers receive training.'}]
        selected = select_context(indicator, sources, max_chars=500, semantic_ranker=ranker)
        self.assertEqual({s['id'] for s in selected}, {'semantic', 'lexical'})
        self.assertLessEqual(sum(len(s['text']) for s in selected), 500)
        self.assertEqual(selected, select_context(indicator, sources[::-1], max_chars=500, semantic_ranker=ranker))

    @override_settings(CAPABILITY_RETRIEVAL_MODE='hybrid', CAPABILITY_EMBEDDING_PATH='/nonexistent-model')
    def test_unprovisioned_hybrid_is_an_explicit_error(self):
        with self.assertRaises(ValueError):
            configured_policy()

    def test_no_semantic_provider_is_created_for_a_frozen_lexical_run(self):
        with patch('builtins.__import__', wraps=__import__) as imports:
            self.assertIsNone(ranker_for({'mode': 'bm25'}))
        self.assertFalse(any(call.args[0].startswith('fastembed') for call in imports.call_args_list))


@skipUnless(os.environ.get('CAPABILITY_TEST_EMBEDDING_PATH'), 'Provision a local embedding artifact for the semantic smoke test')
class RealLocalSemanticTests(SimpleTestCase):
    def test_real_local_model_retrieves_a_paraphrase_without_exact_requirement_terms(self):
        with override_settings(CAPABILITY_RETRIEVAL_MODE='hybrid',
                               CAPABILITY_EMBEDDING_PATH=os.environ['CAPABILITY_TEST_EMBEDDING_PATH']):
            policy = configured_policy()
            ranker = ranker_for(policy)
        indicator = {'code': 'TEST', 'name': 'Staff development', 'scoring_mode': 'independent_conditions',
                     'conditions': [{'text': 'Teachers receive professional training.'}]}
        sources = [{'id': f'noise-{n}', 'text': ('Teachers training records index archive. ' * 60)} for n in range(12)]
        sources.append({'id': 'target', 'text': 'Lecturers completed a hands-on pedagogical development workshop with practical exercises and mentoring.'})
        selected = select_context(indicator, sources, max_chars=1800, semantic_ranker=ranker)
        self.assertIn('target', {s['id'] for s in selected})
        self.assertLessEqual(sum(len(s['text']) for s in selected), 1800)

    def test_dense_real_encoder_inputs_are_bounded_and_reused_without_truncation(self):
        with override_settings(CAPABILITY_RETRIEVAL_MODE='hybrid',
                               CAPABILITY_EMBEDDING_PATH=os.environ['CAPABILITY_TEST_EMBEDDING_PATH']):
            ranker = ranker_for(configured_policy())
        header = '[Table 1 on page 1 -- columns: Year | Staff training]'
        source = {'id': 'dense', 'text': header + '\n' + ('1|2|3|4|5|6|7|8|9|0\n' * 300)}
        self.assertGreater(len(ranker.token_offsets(source['text'][:1200])), ranker.token_limit)
        item = {'code': 'T', 'name': 'Training', 'scoring_mode': 'independent_conditions',
                'conditions': [{'id': 'c', 'text': 'Staff training is recorded.'}]}
        first = select_context(item, [source], semantic_ranker=ranker)
        count = ranker.stats['embedded_passages']
        second = select_context(item, [source], semantic_ranker=ranker)
        self.assertEqual(first, second)
        self.assertEqual(ranker.stats['embedded_passages'], count)
        self.assertEqual(ranker.stats['corpus_builds'], 1)
        self.assertTrue(all(not ranker.input_diagnostics(p.embedding_text)['truncated'] for p in ranker.passages([source])))


    def test_all_profile_queries_fit_real_encoder_and_are_used_for_retrieval(self):
        from .capability.engine import release
        from .capability.evidence_queries import requirement_queries
        with override_settings(CAPABILITY_RETRIEVAL_MODE='hybrid',
                               CAPABILITY_EMBEDDING_PATH=os.environ['CAPABILITY_TEST_EMBEDDING_PATH']):
            ranker = ranker_for(configured_policy())
        rubric = release()
        for indicator in rubric['indicators']:
            for request in requirement_queries(indicator, ranker):
                self.assertEqual(request['query_roles'][0], 'evidence_records')
                for query in request['queries']:
                    self.assertLessEqual(len(ranker.token_offsets(ranker.query_input(query))), ranker.token_limit - 8)
        item = next(i for i in rubric['indicators'] if i['code'] == 'AIQIF-C6.1')
        trace = {}
        source = {'id': 'p', 'text': 'The computer centre provides desktop workstations and internet access to students.'}
        select_context(item, [source], semantic_ranker=ranker, diagnostics=trace)
        for request in trace['requirements']:
            self.assertTrue(all(query in ranker.queries for query in request['queries']))
        self.assertIn('desktop workstations', trace['requirements'][0]['queries'][0])


class GoldDocumentIdentityTests(SimpleTestCase):
    def test_same_page_number_in_another_document_does_not_count_as_a_gold_hit(self):
        from .capability.pipeline_diagnostics import retrieval_recall
        rubric = {'indicators': [{'code': 'TEST', 'name': 'Synthetic', 'conditions': [{'id': 'condition', 'text': 'Synthetic'}]}]}
        quote = 'This is the exact quotation used by the synthetic test.'
        wrong = {'id': 'wrong', 'document_id': 'other-doc', 'page_number': 1, 'text': quote, 'text_offset': 0}
        gold = [{'condition_id': 'condition', 'document_id': 'labelled-doc', 'page': 1, 'quote': quote}]
        result = retrieval_recall(rubric, [wrong], gold, selector=lambda *args, **kwargs: [wrong])
        self.assertEqual(result['retrieved'], 0)
        self.assertEqual(result['page_hits'], 0)

class RetrievalComparisonCommandTests(TestCase):
    def test_comparison_uses_frozen_text_without_evaluator_calls_or_writes(self):
        from io import StringIO
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from django.core.management import call_command
        from .capability.storage import create_run
        from .models import CapabilityRunEvent
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='Synthetic College'))
        doc = Document.objects.create(sprint=sprint, original_filename='Synthetic.pdf')
        quote = 'The governing council approved a digital strategy for its academic services.'
        DocumentPage.objects.create(document=doc, page_number=1, text=quote)
        run = create_run(institution_id=sprint.institution_id, sprint_id=sprint.pk, population='Synthetic', reference_period='2026')
        cid = run.inputs['rubric']['indicators'][0]['conditions'][0]['id']
        count = CapabilityRunEvent.objects.count()
        class Model:
            def passage_embed(self, texts, **kwargs):
                return [[1., 0.] for text in texts]
            def query_embed(self, text):
                return [[1., 0.]]
        ranker = synthetic_ranker(Model())
        with TemporaryDirectory() as directory:
            gold = Path(directory) / 'gold.json'
            output = Path(directory) / 'comparison.json'
            gold.write_text(json.dumps([{'condition_id': cid, 'document_id': str(doc.pk), 'page': 1, 'quote': quote}]))
            with patch('apps.scoring.capability.semantic_retrieval.configured_policy', return_value={'mode': 'hybrid'}), patch(
                    'apps.scoring.capability.semantic_retrieval.ranker_for', return_value=ranker), patch(
                    'apps.extraction.services.ai_service.get_ai_service', side_effect=AssertionError('No evaluator calls')):
                call_command('capability_retrieval_compare', str(run.pk), gold=str(gold), output=str(output),
                             include_replay_inputs=True, stdout=StringIO())
                replay_output = Path(directory) / 'replay.json'
                with patch('apps.scoring.models.CapabilityRun.objects.get', side_effect=AssertionError('Replay must not read the database')):
                    call_command('capability_retrieval_compare', replay_inputs=str(output), output=str(replay_output), stdout=StringIO())
                replayed = json.loads(replay_output.read_text())
                self.assertEqual(replayed['input_verification'], 'replay_content_hash')
                self.assertTrue(all(row['retrieved'] == 1 for row in replayed['sets']['development'].values()))
                missing = Path(directory) / 'missing.json'
                gold.write_text(json.dumps([{'condition_id': cid, 'document_id': str(doc.pk), 'page': 1,
                                            'quote': 'A manually labelled quotation absent from the frozen page.'}]))
                call_command('capability_retrieval_compare', str(run.pk), gold=str(gold), output=str(missing), stdout=StringIO())
                absent = json.loads(missing.read_text())
                self.assertEqual(absent['gold_traces']['development'][0]['loss_stage'], 'quote_not_in_searchable_page')
                self.assertTrue(missing.with_suffix('.md').exists())

            self.assertEqual(configured_policy()['mode'], 'bm25')
            result = json.loads(output.read_text())
            self.assertEqual(result['replay_inputs']['sources'], run.inputs['sources'])
            self.assertEqual(result['comparison_policy'], {'baseline_chars': 18000, 'expansion_chars': 6000})
            self.assertEqual(set(result['sets']['development']), {'bm25_1800', 'bm25_1200', 'profiled_bm25', 'hybrid_passages',
                'bm25_expanded', 'protected_profiled_expanded', 'hybrid_expanded'})
            self.assertTrue(all(r['retrieved'] == 1 for r in result['sets']['development'].values()))
            self.assertTrue(result['gold_traces']['development'][0]['retrieved'])
            self.assertEqual(result['gold_traces']['development'][0]['queries'][0]['lexical_rank'], 1)
        self.assertEqual(CapabilityRunEvent.objects.count(), count)
