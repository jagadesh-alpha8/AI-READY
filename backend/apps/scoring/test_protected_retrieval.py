"""Adversarial discovery must preserve the measured lexical baseline."""
from django.test import SimpleTestCase
from .retrieval_test_fixtures import synthetic_ranker
from .capability.evaluation import select_context
from .capability.evidence_retrieval import expansion_exclusion
from .capability.passages import Passage


class Model:
    def passage_embed(self, texts, **kwargs):
        return [[1., 0.] if 'mentored coaching' in text else [0., 1.] for text in texts]
    def query_embed(self, text):
        return [[1., 0.]]


def indicator():
    return {'code': 'TEST', 'name': 'Faculty training', 'scoring_mode': 'independent_conditions',
            'conditions': [{'id': 'c', 'text': 'Faculty training is operational.'}]}


class ProtectedBaselineTests(SimpleTestCase):
    def sources(self):
        return [{'id': str(n), 'text': 'Faculty training schedules and attendance. ' + ('administrative background ' * 65)}
                for n in range(24)] + [{'id': 'novel', 'text': 'mentored coaching developed instructors through supervised practice. ' + 'Details. ' * 50}]

    def assert_preserved(self, baseline, selected):
        for old in baseline:
            self.assertTrue(any(s['id'] == old['id'] and s['text_offset'] <= old['text_offset']
                and s['text_offset'] + len(s['text']) >= old['text_offset'] + len(old['text']) for s in selected), old['id'])

    def test_same_budget_retains_every_baseline_character(self):
        for budget in (100, 500, 1800, 18000):
            with self.subTest(budget=budget):
                sources = self.sources()
                baseline = select_context(indicator(), sources, max_chars=budget)
                selected = select_context(indicator(), sources, max_chars=budget, semantic_ranker=synthetic_ranker(Model()))
                self.assert_preserved(baseline, selected)
                self.assertLessEqual(sum(len(s['text']) for s in selected), budget)

    def test_expansion_adds_paraphrase_without_evicting_lexical_evidence(self):
        sources = self.sources()
        ranker = synthetic_ranker(Model())
        ranker.baseline_chars = 1800
        baseline = select_context(indicator(), sources, max_chars=1800)
        self.assertNotIn('novel', {s['id'] for s in baseline})
        trace = {}
        selected = select_context(indicator(), sources, max_chars=3000, semantic_ranker=ranker, diagnostics=trace)
        self.assert_preserved(baseline, selected)
        self.assertIn('novel', {s['id'] for s in selected})
        self.assertEqual(trace['baseline_chars'], sum(len(s['text']) for s in baseline))
        self.assertGreater(trace['expansion_chars'], 0)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 3000)
        self.assertEqual(selected, select_context(indicator(), sources[::-1], max_chars=3000, semantic_ranker=ranker))

    def test_boilerplate_is_removed_before_the_semantic_shortlist(self):
        class BoilerplateFirst(Model):
            def passage_embed(self, texts, **kwargs):
                return [[1., 0.] if 'File Description:' in text else [.8, .6] for text in texts]
        ranker = synthetic_ranker(BoilerplateFirst())
        ranker.baseline_chars = 0
        sources = [{'id': str(n), 'text': f'[Table {n} -- columns: File Description | Document]\n'
                    'File Description: Provide training records | Document: View Document'} for n in range(90)]
        sources.append({'id': 'actual', 'text': 'The faculty completed a documented training programme.'})
        trace = {}
        selected = select_context(indicator(), sources, max_chars=1000, semantic_ranker=ranker, diagnostics=trace)
        self.assertEqual({s['id'] for s in selected}, {'actual'})
        self.assertEqual(len(trace['expansion_exclusions']), 90)
        self.assertEqual(len(trace['requirements'][0]['semantic']), 1)
        self.assertEqual(ranker.stats['embedded_passages'], 1)
        self.assertEqual(ranker.stats['skipped_instruction_passages'], 90)

    def test_expansion_spans_remain_exact_nonoverlapping_and_header_costed(self):
        ranker = synthetic_ranker(Model())
        ranker.baseline_chars = 500
        header = '[Table 1 -- columns: Department | Trained]'
        sources = [{'id': 't', 'text': 'Academic year 2026\n' + header + '\n' +
            '\n'.join(f'Department: Arts | Trained: {n}' for n in range(150))}]
        baseline = select_context(indicator(), sources, max_chars=500)
        selected = select_context(indicator(), sources, max_chars=2500, semantic_ranker=ranker)
        self.assert_preserved(baseline, selected)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 2500)
        for a in selected:
            self.assertEqual(a['text'], sources[0]['text'][a['text_offset']:a['text_offset'] + len(a['text'])])
            for b in selected:
                if a is not b:
                    self.assertTrue(a['text_offset'] + len(a['text']) <= b['text_offset'] or
                                    b['text_offset'] + len(b['text']) <= a['text_offset'])

    def test_filter_keeps_substantive_tables_and_mixed_passages(self):
        for text, excluded in [
            ('3.2 Resource Mobilization for Research 3.2.1', True),
            ('Response:\nView Document', True),
            ('Faculty trained: 17 | Year: 2026', False),
            ('BOARD APPROVED THE PLAN', False),
            ('File Description: Supply records | Document: View Document\nFaculty trained: 17', False),
        ]:
            with self.subTest(text=text):
                p = Passage({'id': 'p', 'text': text}, 0, len(text), 'prose', None, text, 10)
                self.assertEqual(bool(expansion_exclusion(p)), excluded)

    def test_default_hybrid_allowance_is_explicit_and_bm25_unchanged(self):
        ranker = synthetic_ranker(Model())
        self.assertEqual((ranker.baseline_chars, ranker.context_chars), (18000, 24000))
        sources = self.sources()
        baseline = select_context(indicator(), sources)
        selected = select_context(indicator(), sources, semantic_ranker=ranker)
        self.assert_preserved(baseline, selected)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 24000)
