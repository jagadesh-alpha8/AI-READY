"""Stage-by-stage diagnosis of unresolved requirements: ingestion, extraction, retrieval, scoring.

Synthetic data only. Each test isolates one layer, so a wide reported interval can be traced to
the first stage that loses evidence. expectedFailure marks a defect this suite has found and
that is still open; remove the marker when the fix lands (an unexpected success fails the suite).
"""
import json
import os
import unittest
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.extraction.services.evidence_text import _placeholder
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability import pipeline_diagnostics as stages
from .capability.engine import assess, release
from .capability.storage import create_run
from apps.scoring.capability.storage import frozen_sources

DOC = '00000000-0000-0000-0000-00000000d0c1'
BUDGET_ROW = 'Budget allocation for the AI laboratory in 2024-25 was 40 lakhs'
TABLE = {'index': 1, 'header': ['Year', 'AI laboratory budget (lakhs)'], 'rows': [['2024-25', '40']], 'bbox': [0, 0, 1, 1]}
FILLER = 'Administrative records were filed with the registrar and archived according to the retention schedule. '


def page(number, text, document=DOC):
    return {'id': f'page-{number}', 'document_id': document, 'page_number': number, 'text': text, 'text_source': 'text'}


def stored(sources, tables):
    """Stored-page rows for rendered_sources: each source page with its tables."""
    return [{**s, 'tables': tables.get(s['id'], [])} for s in sources]


def window(source, text=None):
    return {**source, 'text': text if text is not None else source['text'], 'text_offset': 0}


def claim(cid, page_number, quote, kind='ai_evidence', grounding='not_found'):
    return {'id': cid, 'kind': kind, 'disposition': 'extracted', 'verification': {'grounding': grounding},
            'source': {'document_id': DOC, 'page': str(page_number), 'quote': quote},
            'original_source': {'document_id': DOC, 'page': str(page_number), 'quote': quote}, 'decisions': []}


class IngestionTests(SimpleTestCase):
    def test_table_placeholders_and_missing_table_text_are_measured(self):
        sources = [page(1, 'Infrastructure.\n' + _placeholder(1) + '\nPage 1/2'), page(2, FILLER * 4)]
        rendered = stages.rendered_sources(sources, stored(sources, {'page-1': [TABLE]}))
        health = stages.ingestion_health(sources, rendered)
        self.assertEqual((health['pages_with_table_placeholders'], health['table_placeholders']), (1, 1))
        self.assertGreater(health['table_chars_missing'], 0)
        self.assertEqual(health['pages_missing_most_table_text'][0]['page'], 1)
        self.assertIn('AI laboratory budget (lakhs): 40', rendered[0]['text'])
        self.assertNotIn('AIOSTABLEMARKER', rendered[0]['text'])
        self.assertEqual(health['pages_under_300_chars'], 1)


class FrozenEvidenceTableTests(TestCase):
    """Assessment must freeze table content, not the placeholders the PDF reader stores in page text."""

    def setUp(self):
        institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=institution)
        document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        DocumentPage.objects.create(document=document, page_number=1, tables=[TABLE],
                                    text='Criterion 4 infrastructure.\n' + _placeholder(1) + '\nPage 1/1')

    def frozen_text(self):
        run = create_run(institution_id=self.sprint.institution_id, sprint_id=self.sprint.pk, scope_mode='default')
        return frozen_sources(run)[0]['text']

    def test_frozen_evidence_includes_table_content_and_no_placeholder(self):
        text = self.frozen_text()
        self.assertIn('AI laboratory budget (lakhs): 40', text)
        self.assertNotIn('AIOSTABLEMARKER', text)

    def test_diagnostic_rendering_matches_what_assessment_freezes(self):
        page = DocumentPage.objects.get()
        rendered = stages.rendered_sources([{'id': str(page.pk), 'text': ''}],
            [{'id': str(page.pk), 'document_id': str(page.document_id), 'page_number': 1, 'text': page.text, 'tables': page.tables}])
        self.assertEqual(rendered[0]['text'], self.frozen_text())


class ExtractionTests(SimpleTestCase):
    def test_quotation_location_separates_table_text_from_unmatched_quotations(self):
        sources = [page(1, 'Infrastructure.\n' + _placeholder(1)), page(2, 'The AI policy was approved by the council.')]
        rendered = stages.rendered_sources(sources, stored(sources, {'page-1': [TABLE]}))
        ledger = {'claims': [claim('in-text', 2, 'The AI policy was approved', grounding='exact'),
                             claim('in-table', 1, 'AI laboratory budget (lakhs): 40'),
                             claim('paraphrased', 2, 'Council adopted an AI policy'),
                             claim('wrong-page', 7, 'The AI policy was approved')]}
        health = stages.extraction_health(ledger, sources, rendered)
        self.assertEqual(health['quotation_location'], {'frozen_page_text': 1, 'only_with_tables': 1,
                                                        'not_in_page_text': 1, 'cited_page_not_in_sources': 1})
        self.assertEqual(health['grounding_status'], {'exact': 1, 'not_found': 3})


class RetrievalTests(SimpleTestCase):
    def test_retrieval_is_compared_with_tagged_pages_and_chance(self):
        indicator = next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.3')
        sources = [page(n, FILLER * 25) for n in range(1, 21)]
        sources.append(page(21, 'Budget allocation and resource commitment for computing laboratory infrastructure. ' * 30))
        traces = [{'indicator': 'AIQIF-C1.3', 'source_excerpts': [window(sources[0])]}]
        tags = stages.tagged_pages([
            {'indicator_code': 'AIQIF-C1.3', 'document_id': DOC, 'page': '21', 'relationship': 'direct', 'review_status': 'unreviewed'},
            {'indicator_code': 'AIQIF-C1.3', 'document_id': DOC, 'page': '5', 'relationship': 'contextual', 'review_status': 'unreviewed'},
            {'indicator_code': 'AIQIF-C1.3', 'document_id': DOC, 'page': '6', 'relationship': 'direct', 'review_status': 'rejected'}])
        self.assertEqual(tags, {'AIQIF-C1.3': {(DOC, 21)}})
        result = stages.retrieval_against_tags({'indicators': [indicator]}, traces, tags, rendered=sources)
        self.assertEqual((result['tagged_pages'], result['tagged_pages_selected']), (1, 0))
        self.assertEqual(result['tagged_pages_selected_with_tables'], 1)
        sweep = stages.retrieval_sweep({'indicators': [indicator]}, tags, sources, budgets=(18000,))
        size = sum(len(s['text']) for s in sources)
        self.assertEqual(sweep[0]['frozen'], {'tagged_pages_selected': 1, 'chance_expectation': round(min(1, 18000 / size), 1)})


def export_with(states, *, blocked=(), issues=None, excerpts=None, rubric=None):
    """A saved-run shape built from explicit decisions, for scoring and funnel tests."""
    rubric = rubric or release()
    records, traces = [], []
    for indicator in rubric['indicators']:
        for condition in indicator['conditions']:
            state = states.get(condition['id'], 'unknown')
            issue = (issues or {}).get(condition['id'], '')
            records.append({'condition_id': condition['id'], 'state': state, 'reason': issue or 'Not established in the supplied passages.',
                            'validation_issue': issue, 'citations': [], 'scope_supported': state == 'met', 'period_supported': state == 'met'})
        error = ('Reviewed-evidence context exceeds the bounded input allowance. Capability is unknown; no model request was made.'
                 if indicator['code'] in blocked else '')
        traces.append({'indicator': indicator['code'], 'model_call_attempted': not error, 'error': error,
                       'source_excerpts': (excerpts or {}).get(indicator['code'], [])})
    return {'rubric': rubric, 'source_manifest': [{'document_id': DOC, 'filename': 'ssr.pdf', 'pages': []}],
            'assessment': {'records': records, 'traces': traces}}


class IntervalTests(SimpleTestCase):
    def test_interval_is_split_exactly_across_causes(self):
        rubric = release()
        first, second = rubric['indicators'][0], rubric['indicators'][1]
        states = {first['conditions'][0]['id']: 'met', first['conditions'][1]['id']: 'met'}
        export = export_with(states, blocked={second['code']})
        result = stages.interval_attribution(export)
        saved = assess({r['condition_id']: r['state'] for r in export['assessment']['records']}, rubric)
        self.assertEqual((result['lower'], result['upper']), (saved['lower'], saved['upper']))
        self.assertEqual(result['upper'], 100.0)
        self.assertAlmostEqual(sum(result['width_by_cause'].values()), result['width'], places=1)
        self.assertGreater(result['width_by_cause']['not_evaluated:reviewed_evidence_allowance'], 0)

    def test_upper_bound_falls_only_through_not_met(self):
        rubric = release()
        condition = rubric['indicators'][0]['conditions'][0]['id']
        result = stages.interval_attribution(export_with({condition: 'not_met'}))
        self.assertEqual(result['not_met_decisions'], 1)
        self.assertAlmostEqual(result['upper'], 100 - result['upper_lost_to_not_met'], places=2)
        self.assertLess(result['upper'], 100)


class GoldFunnelTests(SimpleTestCase):
    """Person-labelled evidence, each item stopping at a different stage."""

    def test_first_failing_stage_for_each_labelled_item(self):
        rubric = {'indicators': [i for i in release()['indicators'] if i['code'] in ('AIQIF-C1.3', 'AIQIF-C1.4')]}
        c13, c14 = rubric['indicators']
        ids = [c['id'] for c in c13['conditions']]
        selected = page(1, 'The approved plan commits a recurring budget to the computing laboratory for 2024-25.')
        unselected = page(2, 'Separately, the incubation centre received a dedicated innovation fund in 2024-25.')
        tables = page(3, 'Infrastructure.\n' + _placeholder(1))
        sources = [selected, unselected, tables] + [page(n, FILLER * 30) for n in range(4, 12)]
        rendered = stages.rendered_sources(sources, stored(sources, {'page-3': [TABLE]}))
        export = export_with({ids[0]: 'met'}, blocked={'AIQIF-C1.4'},
                             issues={ids[2]: 'Quote does not match a supplied source passage.'},
                             excerpts={'AIQIF-C1.3': [window(selected)], 'AIQIF-C1.4': [window(selected)]}, rubric=rubric)
        gold = [
            {'condition_id': ids[0], 'page': 1, 'quote': 'commits a recurring budget to the computing laboratory'},
            {'condition_id': ids[1], 'page': 1, 'quote': 'commits a recurring budget to the computing laboratory'},
            {'condition_id': ids[2], 'page': 1, 'quote': 'commits a recurring budget'},
            {'condition_id': ids[3], 'page': 2, 'quote': 'received a dedicated innovation fund'},
            {'condition_id': ids[4], 'page': 3, 'quote': 'AI laboratory budget (lakhs): 40', 'document': 'ssr.pdf'},
            {'condition_id': ids[5], 'page': 1, 'quote': 'this sentence was never in the document'},
            {'condition_id': c14['conditions'][0]['id'], 'page': 1, 'quote': 'commits a recurring budget'},
            {'condition_id': c14['conditions'][1]['id'], 'page': 99, 'quote': 'anything'},
        ]
        result = stages.gold_funnel(export, sources, gold, rendered=rendered)
        self.assertEqual([r['stage'] for r in result['items']],
                         ['credited', 'model_unknown', 'validation_downgraded', 'not_retrieved', 'quote_only_in_tables',
                          'quote_not_in_any_text', 'batch_blocked', 'page_missing'])
        # The hand-built trace selected less than retrieval does: a replay reaches the page at the default budget.
        self.assertEqual(result['items'][3]['retrieval_budget_needed'], 18000)
        self.assertLessEqual(set(result['first_failure_counts']), set(stages.STAGES))


@unittest.skipUnless(os.environ.get('CAPABILITY_REFERENCE_EXPORT'), 'Set CAPABILITY_REFERENCE_EXPORT to a private export path.')
class ReferenceIntervalTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.export = json.loads(Path(os.environ['CAPABILITY_REFERENCE_EXPORT']).read_text(encoding='utf-8'))

    def test_interval_attribution_reproduces_the_reported_bounds_and_explains_all_width(self):
        result = stages.interval_attribution(self.export)
        saved = self.export['assessment']['result']
        self.assertEqual((result['lower'], result['upper']), (saved['lower'], saved['upper']))
        self.assertAlmostEqual(sum(result['width_by_cause'].values()), result['width'], places=1)

    @unittest.expectedFailure
    def test_claim_quotations_occur_in_the_text_assessment_reads(self):
        # Page text is not in an export, so this checks the stored grounding status the extractor recorded.
        claims = self.export['reviewed_evidence']['claims']
        grounded = sum(c['verification'].get('grounding') in ('exact', 'ocr_variant') for c in claims)
        self.assertGreaterEqual(grounded / len(claims), stages.FIDELITY_THRESHOLD)


class FidelityGateTests(SimpleTestCase):
    def test_gate_measures_quotations_in_assessed_text_and_with_tables(self):
        health = {'claims': 10, 'quotation_location': {'frozen_page_text': 6, 'only_with_tables': 3, 'not_in_page_text': 1}}
        gate = stages.extraction_fidelity(health)
        self.assertEqual((gate['rate'], gate['rate_with_tables'], gate['passes']), (0.6, 0.9, False))
        self.assertTrue(stages.extraction_fidelity({'claims': 2, 'quotation_location': {'frozen_page_text': 2}})['passes'])
        self.assertFalse(stages.extraction_fidelity({'claims': 1, 'quotation_location': {'no_quotation': 1}})['passes'])


class ProvisionalGoldAndOracleTests(SimpleTestCase):
    def setUp(self):
        self.sources = [page(1, 'Infrastructure.\n' + _placeholder(1)), page(2, 'The council   approved\nthe AI policy in 2024.')]
        self.rendered = stages.rendered_sources(self.sources, stored(self.sources, {'page-1': [TABLE]}))

    def mapping(self, **kw):
        return {'indicator_code': 'AIQIF-C1.3', 'relationship': 'direct', 'review_status': 'unreviewed', 'auto_accepted': True,
                'document_id': DOC, 'page': '1', 'quote': 'AI laboratory budget (lakhs): 40', 'fact_id': 'f1', **kw}

    def test_provisional_labels_keep_only_accepted_located_evidence_tags(self):
        gold = stages.provisional_gold([
            self.mapping(),
            self.mapping(fact_id='f2', relationship='contextual'),
            self.mapping(fact_id='f3', auto_accepted=False),
            self.mapping(fact_id='f4', review_status='rejected'),
            self.mapping(fact_id='f5', quote='a quotation found nowhere'),
            self.mapping(fact_id='f6', indicator_code='AIQIF-C2.1', page='2', quote='council approved the AI policy',
                         auto_accepted=False, review_status='confirmed')], self.rendered)
        self.assertEqual([(g['indicator'], g['page']) for g in gold], [('AIQIF-C2.1', 2), ('AIQIF-C1.3', 1)])
        self.assertTrue(all(g['note'].startswith('provisional') for g in gold))

    def test_indicator_level_label_is_credited_by_any_met_requirement(self):
        rubric = {'indicators': [i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.3']}
        ids = [c['id'] for c in rubric['indicators'][0]['conditions']]
        export = export_with({ids[4]: 'met'}, rubric=rubric, excerpts={'AIQIF-C1.3': [window(self.sources[1])]})
        result = stages.gold_funnel(export, self.sources, [{'indicator': 'AIQIF-C1.3', 'page': 2, 'quote': 'council approved the AI policy'}])
        self.assertEqual(result['items'][0]['stage'], 'credited')

    def test_oracle_context_adds_a_window_around_each_labelled_quotation(self):
        rubric = {'indicators': [i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.3']}
        export = export_with({}, rubric=rubric, excerpts={'AIQIF-C1.3': [window(self.sources[1])]})
        contexts, items = stages.oracle_contexts(export, self.rendered, [
            {'indicator': 'AIQIF-C1.3', 'page': 1, 'quote': 'AI laboratory budget (lakhs): 40'},
            {'indicator': 'AIQIF-C1.3', 'page': 1, 'quote': 'not on the page'}])
        self.assertEqual(len(contexts['AIQIF-C1.3']), 2)
        self.assertIn('AI laboratory budget (lakhs): 40', contexts['AIQIF-C1.3'][1]['text'])
        self.assertEqual([i['oracle_window_found'] for i in items['AIQIF-C1.3']], [True, False])
        self.assertIsNotNone(stages.oracle_window(self.sources[1], 'council approved the AI policy'))
