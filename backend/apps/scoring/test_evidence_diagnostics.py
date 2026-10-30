from copy import deepcopy
from unittest import TestCase

from .capability.engine import assess, release
from .capability.evaluation import select_context
from .capability.diagnostics import explain


class EvidenceDiagnosticsTests(TestCase):
    def test_unknown_zero_is_explained_without_reinterpreting_result(self):
        rubric = release()
        records = [{'condition_id': c['id'], 'state': 'unknown', 'validation_issue': 'No applicable period.'}
                   for i in rubric['indicators'] for c in i['conditions']]
        inputs = {'rubric': rubric, 'sources': [], 'manifest': []}
        assessment = {'records': records, 'result': assess({}, rubric), 'traces': []}
        before = deepcopy(assessment)
        diagnostics = explain(inputs, assessment)
        self.assertIn('not a finding', diagnostics['explanation'])
        self.assertEqual(diagnostics['state_counts']['unknown'], 216)
        self.assertEqual(len(diagnostics['foundation_blockers']), 36)
        self.assertEqual(diagnostics['validation_issues'][0]['count'], 216)
        self.assertEqual(assessment, before)

    def test_requirement_words_find_evidence_later_in_a_page(self):
        indicator = {'code': 'C1', 'name': 'Governance', 'conditions': [
            {'text': 'Institutional artificial intelligence policy and accountable committee.'}]}
        text = 'Unrelated background text. ' * 500 + 'Artificial intelligence policy and accountable committee. ' * 12
        selected = select_context(indicator, [{'id': 'x', 'text': text}])
        self.assertIn('accountable committee', selected[0]['text'])
        offset = selected[0]['text_offset']
        self.assertGreater(offset, 0)
        self.assertEqual(selected[0]['text'], text[offset:offset + len(selected[0]['text'])])

    def test_source_id_changes_do_not_change_tie_breaking(self):
        indicator = {'code': 'C1', 'name': 'Policy', 'conditions': [{'text': 'AI policy'}]}
        a = [{'id': 'a', 'text': 'AI policy first'}, {'id': 'b', 'text': 'AI policy second'}]
        b = [{'id': '0', 'text': a[1]['text']}, {'id': 'z', 'text': a[0]['text']}]
        self.assertEqual([r['text'] for r in select_context(indicator, a)],
                         [r['text'] for r in select_context(indicator, b)])
