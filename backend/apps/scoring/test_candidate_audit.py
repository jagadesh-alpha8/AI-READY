"""Candidate availability and packet feasibility do not establish decision truth."""
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from .capability.retrieval_diagnostics import candidate_audit, labelled_packet_oracle


def requirement(lexical, semantic):
    return {'raw_lexical': lexical, 'profile_lexical': lexical, 'raw_semantic': semantic,
            'lexical': lexical, 'semantic': semantic, 'raw_scores': [1., 1., 1.],
            'profile_scores': [1., 1., 1.], 'similarity': [1., 1., 1.], 'lexical_scores': [1., 1., 1.]}


class CandidateAuditTests(SimpleTestCase):
    def test_alternative_quotes_do_not_inflate_requirement_coverage(self):
        from .capability.pipeline_diagnostics import retrieval_recall
        source = {'id': 'p', 'document_id': 'd', 'page_number': 1,
                  'text': 'Training provided. Mentors named. Feedback collected.'}
        rubric = {'indicators': [{'code': 'I', 'conditions': [{'id': 'a'}, {'id': 'b'}]}]}
        gold = [{'condition_id': cid, 'document_id': 'd', 'page': 1, 'quote': quote}
                for cid, quote in [('a', 'Training provided.'), ('a', 'Mentors named.'), ('b', 'Feedback collected.')]]
        result = retrieval_recall(rubric, [source], gold,
            selector=lambda *args, **kwargs: [{**source, 'text': 'Training provided.', 'text_offset': 0}])
        self.assertEqual(result['of'], 3)
        self.assertEqual(result['retrieved'], 1)
        self.assertEqual(result['labelled_requirement_coverage']['labelled_requirements'], 2)
        self.assertEqual(result['labelled_requirement_coverage']['requirements_with_any_target_retrieved'], 1)

    def test_another_requirements_query_can_find_the_target(self):
        first = requirement([0], [1])
        other = requirement([2], [2])
        result = candidate_audit([first, other], first, [2])['5']
        self.assertFalse(result['target_requirement_raw_union'])
        self.assertTrue(result['indicator_raw_union'])
        self.assertTrue(result['indicator_eligible_union'])
        self.assertEqual(result['indicator_eligible_union_size'], 3)

    def test_filtered_candidates_are_visible_in_raw_but_not_eligible_pool(self):
        target = requirement([0], [1])
        target['raw_lexical'] = [2, 0]
        result = candidate_audit([target], target, [2])['5']
        self.assertTrue(result['target_requirement_raw_union'])
        self.assertFalse(result['target_requirement_eligible_union'])

    def test_zero_scores_do_not_count_as_candidate_recall(self):
        target = requirement([0], [0])
        target.update(raw_scores=[0., 0., 0.], profile_scores=[0., 0., 0.],
                      similarity=[0., 0., 0.], lexical_scores=[0., 0., 0.])
        self.assertFalse(any(candidate_audit([target], target, [0])['100'].values()))

    def test_oracle_counts_shared_heading_once_and_marks_missing_candidates(self):
        rows = [{'indicator': 'I', 'matching_candidates': [{'source_id': 'p', 'offset': a,
                 'end': b, 'context_spans': [[0, 10]]}]} for a, b in ((10, 20), (20, 30))]
        result = labelled_packet_oracle(rows, 30)['I']
        self.assertEqual(result['label_aware_packet_chars'], 30)
        self.assertTrue(result['all_labelled_candidates_fit'])
        self.assertFalse(labelled_packet_oracle(rows, 29)['I']['all_labelled_candidates_fit'])
        rows.append({'indicator': 'I', 'matching_candidates': []})
        self.assertFalse(labelled_packet_oracle(rows, 100)['I']['all_labelled_candidates_fit'])

    def test_local_model_disables_telemetry_before_model_construction(self):
        from .capability.semantic_retrieval import _model
        runtime = SimpleNamespace(disable_telemetry_events=Mock())
        def construct(**kwargs):
            self.assertEqual(os.environ['ORT_DISABLE_TELEMETRY'], '1')
            runtime.disable_telemetry_events.assert_called_once()
            self.assertTrue(kwargs['local_files_only'])
            return 'public synthetic model'
        with patch.dict(os.environ, {'ORT_DISABLE_TELEMETRY': '0'}), patch.dict('sys.modules', {
            'onnxruntime': runtime, 'fastembed': SimpleNamespace(TextEmbedding=construct)}):
            self.assertEqual(_model('/synthetic-only', 'synthetic', 'test-no-telemetry'), 'public synthetic model')
