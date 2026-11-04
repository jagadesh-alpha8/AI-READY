"""Structural contracts; synthetic evidence is not a private reference recall benchmark."""
from django.test import SimpleTestCase
from .retrieval_test_fixtures import synthetic_ranker
from .capability.passages import construct_passages
from .capability.evidence_queries import requirement_queries
from .capability.evaluation import select_context
from .capability.evidence_retrieval import diverse
from .capability.retrieval_diagnostics import gold_traces, trace_summary, readable_report
from .capability.semantic_retrieval import SemanticRetrievalUnavailable, ranker_for


class Model:
    def __init__(self):
        self.passage_calls = 0
        self.query_calls = 0
    def passage_embed(self, texts, **kwargs):
        self.passage_calls += 1
        return [[1., 0.] if 'training' in text.lower() else [0., 1.] for text in texts]
    def query_embed(self, text):
        self.query_calls += 1
        return [[1., 0.]]


def indicator():
    return {'code': 'TEST', 'name': 'Broad topic', 'scoring_mode': 'independent_conditions',
            'conditions': [{'id': 'a', 'text': 'An approved plan identifies a faculty training priority.'},
                           {'id': 'b', 'text': 'An owner is assigned to that priority.'}]}


class PassageArchitectureTests(SimpleTestCase):
    def test_complete_embedding_inputs_are_token_bounded_and_body_offsets_exact(self):
        ranker = synthetic_ranker(Model())
        source = {'id': 'p', 'text': 'Faculty development:\n' + ('é 12.34 | training 2024-25: 17; ' * 600)}
        passages = construct_passages([source], ranker)
        self.assertGreater(len(passages), 3)
        self.assertTrue(all(p.tokens <= ranker.token_limit - 8 for p in passages))
        self.assertTrue(all(p.text == source['text'][p.start:p.end] for p in passages))
        self.assertTrue(all(p.tokens == len(ranker.token_offsets(p.embedding_text)) for p in passages))
        # Every original non-whitespace character remains represented by some body span.
        covered = {n for p in passages for n in range(p.start, p.end)}
        self.assertTrue(all(n in covered for n, char in enumerate(source['text']) if not char.isspace()))

    def test_table_chunks_carry_actual_heading_and_labels(self):
        header = '[Table 1 on page 1 -- columns: Year | Faculty trained]'
        source = {'id': 'p', 'text': header + '\n' + '\n'.join(f'Year: {n} | Faculty trained: {n + 10}' for n in range(100))}
        passages = construct_passages([source], synthetic_ranker(Model()))
        self.assertGreater(len(passages), 1)
        self.assertTrue(all(p.kind == 'table' for p in passages))
        self.assertTrue(all(header in p.embedding_text for p in passages))
        self.assertTrue(all(source['text'][p.heading[0]:p.heading[1]] == header for p in passages))
        self.assertTrue(any('Year: 99 | Faculty trained: 109' in p.text for p in passages))

    def test_long_header_is_bounded_and_explicitly_flagged(self):
        source = {'id': 'p', 'text': '[Table 1 on page 1 -- columns: ' + 'column | ' * 160 + ']\nYear: 2026 | Count: 12'}
        ranker = synthetic_ranker(Model(), limit=128)
        passages = construct_passages([source], ranker)
        self.assertTrue(all(p.tokens <= 120 for p in passages))
        self.assertTrue(all(p.heading_clipped for p in passages))

    def test_referential_assertions_receive_context_without_broad_title_prefix(self):
        queries = requirement_queries(indicator(), synthetic_ranker(Model()))
        self.assertEqual(queries[0]['queries'], [indicator()['conditions'][0]['text']])
        self.assertIn('approved plan', queries[1]['queries'][0])
        self.assertIn('owner', queries[1]['queries'][0])
        self.assertNotIn('Broad topic', queries[1]['queries'][0])
        self.assertLessEqual(len(queries[1]['queries']), 2)

    def test_store_and_embeddings_reused_then_invalidated_when_source_changes(self):
        model = Model()
        ranker = synthetic_ranker(model)
        sources = [{'id': 'p', 'text': 'Faculty training records document the approved programme.'}]
        first = select_context(indicator(), sources, semantic_ranker=ranker)
        second = select_context(indicator(), list(reversed(sources)), semantic_ranker=ranker)
        self.assertEqual(first, second)
        self.assertEqual(model.passage_calls, 1)
        self.assertEqual(ranker.stats['corpus_builds'], 1)
        sources[0]['text'] += ' A revised owner was appointed.'
        select_context(indicator(), sources, semantic_ranker=ranker)
        self.assertEqual(model.passage_calls, 2)
        self.assertEqual(ranker.stats['corpus_builds'], 2)

    def test_header_costs_budget_and_packets_contain_only_exact_source_spans(self):
        header = '[Table 1 on page 1 -- columns: Year | Faculty training]'
        text = header + '\n' + '\n'.join(f'Year: {n} | Faculty training: {n + 10}' for n in range(100))
        source = {'id': 'p', 'text': text}
        class LastRowModel(Model):
            def passage_embed(self, texts, **kwargs):
                return [[1., 0.] if 'Year: 99' in text else [0., 1.] for text in texts]
        selected = select_context(indicator(), [source], semantic_ranker=synthetic_ranker(LastRowModel()), max_chars=1100)
        self.assertTrue(selected)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 1100)
        self.assertTrue(any(header in s['text'] for s in selected))
        self.assertTrue(any(s['text_offset'] > 0 for s in selected))
        for item in selected:
            self.assertEqual(item['text'], text[item['text_offset']:item['text_offset'] + len(item['text'])])

    def test_packing_never_clips_a_body_to_fill_remaining_budget(self):
        source = {'id': 'p', 'text': 'training ' * 200}
        trace = {}
        selected = select_context(indicator(), [source], semantic_ranker=synthetic_ranker(Model()), max_chars=100, diagnostics=trace)
        self.assertEqual(selected, [])
        self.assertTrue(any(a['outcome'] == 'budget_excluded' for a in trace['packing_attempts']))

    def test_unscoped_duplicate_pages_retain_independent_provenance(self):
        source = {'id': 'p', 'document_id': 'd', 'text': 'Training was planned.\n\nTraining is operational.'}
        other = {'id': 'q', 'document_id': 'd', 'text': source['text']}
        passages = construct_passages([source, other], synthetic_ranker(Model()))
        order, suppressed = diverse(list(range(len(passages))), passages)
        self.assertEqual(len(order), 2)
        self.assertFalse(suppressed)
        self.assertIn('planned', passages[order[0]].text)
        self.assertIn('operational', passages[order[0]].text)

    def test_semantic_failure_cannot_silently_return_lexical_evidence(self):
        class Broken(Model):
            def passage_embed(self, texts, **kwargs):
                raise SemanticRetrievalUnavailable('Broken local model')
        with self.assertRaises(SemanticRetrievalUnavailable):
            select_context(indicator(), [{'id': 'p', 'text': 'Training evidence.'}], semantic_ranker=synthetic_ranker(Broken()))
        with self.assertRaises(SemanticRetrievalUnavailable):
            ranker_for({'mode': 'hybrid', 'fusion': 'different-policy'})

    def test_ingestion_and_context_signals_are_reported_without_claiming_entailment(self):
        source = {'id': 'p', 'document_id': 'd', 'page_number': 1, 'text': 'Faculty training was planned for next year.'}
        gold = [{'condition_id': 'a', 'document_id': 'd', 'page': 1, 'quote': 'A quotation absent from the source.'}]
        rubric = {'indicators': [indicator()]}
        rows = gold_traces(rubric, [source], gold, synthetic_ranker(Model()))
        self.assertEqual(rows[0]['loss_stage'], 'quote_not_in_searchable_page')
        self.assertEqual(trace_summary(rows)['source_quotes_present'], 0)
        similarity = rows[0]['queries'][0]['nearest_semantic'][0]['similarity']
        self.assertGreaterEqual(similarity, -1.00001)
        self.assertLessEqual(similarity, 1.00001)
        report = readable_report({'gold_traces': {'regression': rows}, 'trace_summary': {'regression': trace_summary(rows)}})
        self.assertIn('manual relevance/entailment review', report)
        self.assertIn('planned for next year', report)

    def test_bge_query_instruction_is_query_only(self):
        model = Model()
        model.model_name = 'BAAI/bge-small-en-v1.5'
        ranker = synthetic_ranker(model)
        query = ranker.query_input('Faculty training records')
        self.assertTrue(query.startswith('Represent this sentence for searching relevant passages: '))
        passages = ranker.passages([{'id': 'p', 'text': 'Faculty training records are retained.'}])
        self.assertFalse(passages[0].embedding_text.startswith('Represent this sentence'))

    def test_table_rows_retain_the_actual_reporting_period_heading(self):
        text = 'Academic year 2024-25\n[Table 1 on page 1 -- columns: Department | Faculty trained]\n' + \
               '\n'.join(f'Department: Arts | Faculty trained: {n}' for n in range(100))
        passages = construct_passages([{'id': 'p', 'text': text}], synthetic_ranker(Model()))
        rows = [p for p in passages if p.kind == 'table']
        self.assertTrue(rows)
        self.assertTrue(all('Academic year 2024-25' in p.embedding_text for p in rows))
        self.assertTrue(all(len(p.context_spans) == 2 for p in rows))

    def test_partial_overlap_cannot_suppress_unique_row_tails(self):
        from .capability.passages import Passage
        source = {'id': 'p', 'text': 'x' * 1800}
        passages = [Passage(source, start, end, 'table', None, source['text'][start:end] + str(start), 1)
                    for start, end in ((0, 1200), (600, 1800))]
        selected, suppressed = diverse([0, 1], passages)
        self.assertEqual(selected, [0, 1])
        self.assertFalse(suppressed)
