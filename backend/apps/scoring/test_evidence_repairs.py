"""Contract tests for table evidence, citation fidelity and bounded retrieval."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase as UnitTestCase
from unittest.mock import patch
from django.test import TestCase
from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.extraction.services.evidence_text import _placeholder, evidence_pages
from apps.extraction.services.openai_fact_extractor import OpenAIFactExtractor
from apps.facts.verification.grounding import page_text
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability.storage import evidence_snapshot, digest
from .capability.evaluation import select_context

TABLE = {'index': 1, 'header': ['Year', 'Faculty'], 'rows': [['2026', '42']]}

class EvidenceSnapshotRepairTests(TestCase):
    def test_table_survives_snapshot_and_grounding_and_invalidates_hash(self):
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        document = Document.objects.create(sprint=sprint, document_type='naac_ssr')
        page = DocumentPage.objects.create(document=document, page_number=1,
            text=_placeholder(1), tables=[TABLE])
        manifest, sources = evidence_snapshot(sprint)
        expected = evidence_pages([{'page_number': 1, 'text': page.text, 'tables': page.tables}])[0]['text']
        self.assertEqual(sources[0]['text'], expected)
        self.assertEqual(page_text(document, 1), expected)
        self.assertIn('Year: 2026 | Faculty: 42', expected)
        self.assertNotIn('AIOSTABLEMARKER', expected)
        page.tables = [{**TABLE, 'rows': [['2026', '43']]}]
        page.save()
        changed_manifest, changed_sources = evidence_snapshot(sprint)
        self.assertNotEqual(digest(manifest), digest(changed_manifest))
        self.assertIn('Faculty: 43', changed_sources[0]['text'])

    def test_paragraph_detected_as_header_is_printed_once_not_before_every_row(self):
        from apps.extraction.services.evidence_text import render_table
        question = '4.1.4 Average percentage of expenditure incurred, excluding salary, for infrastructure augmentation'
        rendered = render_table({'index': 1, 'header': ['Year', question], 'rows': [['2023', '40'], ['2024', '42']]}, 5)
        self.assertEqual(rendered.count(question), 1)
        self.assertIn('Year: 2023 | 40', rendered)
        self.assertIn('Year: 2024 | 42', rendered)

    def test_empty_page_text_does_not_discard_structured_table(self):
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        document = Document.objects.create(sprint=sprint, document_type='naac_ssr')
        DocumentPage.objects.create(document=document, page_number=1, text='', tables=[TABLE])
        self.assertIn('Faculty: 42', evidence_snapshot(sprint)[1][0]['text'])

    def test_only_current_exact_grounded_nonrejected_tags_supply_hints(self):
        from apps.facts.models import ExtractedFact, FactAIQIFMapping
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        document = Document.objects.create(sprint=sprint, document_type='naac_ssr')
        DocumentPage.objects.create(document=document, page_number=1, text='Faculty: 42')
        fact = ExtractedFact.objects.create(sprint=sprint, document=document, field_name='Faculty',
            field_key='faculty', value=42, source_page='1', source_snippet='Faculty: 42')
        mapping = FactAIQIFMapping.objects.create(fact=fact, criterion='aiqif_c4',
            indicator_code='AIQIF-C4.1', reason='Location hint', confidence=.9, status='mapped')
        source = evidence_snapshot(sprint)[1][0]
        self.assertEqual(source['retrieval_hints'][0]['indicator_code'], 'AIQIF-C4.1')
        mapping.review_status = 'rejected'
        mapping.save()
        self.assertEqual(evidence_snapshot(sprint)[1][0]['retrieval_hints'], [])
        mapping.review_status, mapping.relationship = 'confirmed', 'contextual'
        mapping.save()
        self.assertEqual(evidence_snapshot(sprint)[1][0]['retrieval_hints'], [])
        mapping.relationship = 'direct'
        mapping.save()
        self.assertEqual(len(evidence_snapshot(sprint)[1][0]['retrieval_hints']), 1)
        fact.source_snippet = 'Unprinted quotation'
        fact.save()
        self.assertEqual(evidence_snapshot(sprint)[1][0]['retrieval_hints'], [])


class ScopeLabelTests(TestCase):
    """Evidence cleanup drops repeated headers; the SSR header that names the institution must still be read."""

    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='Saved Profile Name'))
        document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        for n in range(1, 5):
            DocumentPage.objects.create(document=document, page_number=n, text=(
                f'Self Study Report of SAMPLE INSTITUTE OF TECHNOLOGY\nCriterion {n} narrative for this page.\n'
                f'Page {n}/4\n07-08-2024 09:21:4{n}'))

    def test_header_is_cleaned_from_evidence_but_identity_and_report_dates_are_still_declared(self):
        from rest_framework.exceptions import ValidationError
        from apps.facts.review_queue import identity_case
        from .capability.storage import create_run
        _, sources = evidence_snapshot(self.sprint)
        self.assertFalse(any('Self Study Report of' in s['text'] for s in sources))
        self.assertEqual(identity_case(self.sprint)['alternatives'][0]['value'], 'SAMPLE INSTITUTE OF TECHNOLOGY')
        with self.assertRaises(ValidationError):
            create_run(institution_id=self.sprint.institution_id, sprint_id=self.sprint.pk, scope_mode='default')
        run = create_run(institution_id=self.sprint.institution_id, sprint_id=self.sprint.pk, scope_mode='default',
                         confirmed_source_institution='SAMPLE INSTITUTE OF TECHNOLOGY')
        kinds = [d['kind'] for d in run.inputs['scope']['source_declarations']]
        self.assertEqual((kinds.count('institution_identity'), kinds.count('report_claim_date')), (4, 4))
        self.assertEqual(run.inputs['scope']['institution']['identity_status'], 'user_confirmed_for_this_run')


class TableReadabilityTests(UnitTestCase):
    def test_table_content_counts_before_ocr_fallback(self):
        from apps.extraction.services.pdf_reader import PDFPageReader
        reader = PDFPageReader(min_text_chars_per_page=40)
        with patch('apps.extraction.services.pdf_reader._page_text', return_value=('', [TABLE])):
            read = reader._read_page(SimpleNamespace(id='test'), object(), 1)
        self.assertEqual(read.source, 'text')
        self.assertEqual(read.tables, [TABLE])


class CitationRepairTests(UnitTestCase):
    def validate(self, page, quote, pages):
        extractor = object.__new__(OpenAIFactExtractor)
        fact = {'source_page': page, 'source_snippet': quote, 'tagging_notes': []}
        with patch.object(extractor, '_validate_fact', return_value=deepcopy(fact)):
            return extractor.validate_chunk(SimpleNamespace(id='test'), [{}], pages, 0)

    def test_unique_exact_quote_repairs_wrong_page(self):
        facts = self.validate('1', 'Faculty: 42', [{'page_number': 1, 'text': 'Other text'},
            {'page_number': 2, 'text': 'Year: 2026 | Faculty: 42'}])
        self.assertEqual(facts[0]['source_page'], '2')
        self.assertEqual(facts[0]['tagging_notes'][0]['kind'], 'citation_page_repaired')

    def test_paraphrase_is_not_accepted_as_a_quotation(self):
        self.assertEqual(self.validate('1', 'Forty-two faculty',
            [{'page_number': 1, 'text': 'Faculty: 42'}]), [])

    def test_whitespace_is_accepted_and_ambiguous_page_is_not_guessed(self):
        self.assertEqual(len(self.validate('1', 'Faculty: 42',
            [{'page_number': 1, 'text': 'Faculty:\n 42'}])), 1)
        self.assertEqual(self.validate(None, 'Faculty: 42', [
            {'page_number': 1, 'text': 'Faculty: 42'},
            {'page_number': 2, 'text': 'Faculty: 42'}]), [])

def raw_fact(**overrides):
    return {'field_name': 'Faculty', 'field_key': 'total_faculty', 'value': '42', 'data_type': 'number',
            'pillar': 'aiqif_c4', 'owner_role': 'hr_officer', 'source_page': '1', 'source_snippet': 'Faculty: 42',
            'confidence_score': .9, 'confidence_reason': 'Stated in the table.', **overrides}


class QuotationCheckTests(UnitTestCase):
    """Real fact validation (no mocked _validate_fact): repairs, rejections and their record."""
    pages = [{'page_number': 1, 'text': 'Other text'}, {'page_number': 2, 'text': 'Year: 2026 | Faculty: 42'}]

    def validate(self, *facts):
        extractor = object.__new__(OpenAIFactExtractor)
        extractor.report = {}
        return extractor.validate_chunk(SimpleNamespace(id='test'), list(facts), self.pages, 3), extractor.report['quotation_checks']

    def test_citation_outside_the_chunk_is_repaired_from_a_unique_quotation(self):
        facts, checks = self.validate(raw_fact(source_page='9'))
        self.assertEqual(facts[0]['source_page'], '2')
        self.assertEqual(facts[0]['tagging_notes'][-1], {'kind': 'citation_page_repaired', 'original_page': '9', 'page': '2'})
        self.assertEqual((checks['accepted'], checks['repaired'], checks['rejected']), (1, 1, 0))

    def test_every_dropped_fact_is_counted_with_a_bounded_example(self):
        facts, checks = self.validate(raw_fact(source_snippet='There are forty-two faculty'), raw_fact(data_type='colour'))
        self.assertEqual(facts, [])
        self.assertEqual((checks['rejected'], checks['other_rejected']), (1, 1))
        self.assertEqual([e['chunk'] for e in checks['rejected_examples']], [3, 3])
        self.assertEqual(checks['rejected_examples'][0]['quotation'], 'There are forty-two faculty')


class QuotationCheckPersistenceTests(TestCase):
    def test_checks_are_saved_on_the_job_without_marking_the_reading_partial(self):
        from apps.extraction.models import ExtractionJob
        from apps.extraction.services.pipeline import ExtractionPipeline
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        document = Document.objects.create(sprint=sprint, document_type='naac_ssr')
        job = ExtractionJob.objects.create(sprint=sprint, document=document)
        pipeline = object.__new__(ExtractionPipeline)
        pipeline.fact_extractor = SimpleNamespace(report={'chunks_total': 1, 'chunks_completed': 1, 'issues': [],
            'quotation_checks': {'accepted': 4, 'repaired': 1, 'rejected': 2, 'other_rejected': 0, 'rejected_examples': []}})
        pipeline._record_completeness(job, document, {'pages': [{'page_number': 1, 'read_status': 'ok'}]})
        job.refresh_from_db()
        self.assertEqual(job.completeness, ExtractionJob.Completeness.COMPLETE)
        warning = next(w for w in job.extraction_warnings if w['kind'] == 'quotation_checks')
        self.assertEqual((warning['rejected'], warning['repaired']), (2, 1))
        self.assertIn('2 extracted fact(s) were dropped', warning['detail'])


class RetrievalRepairTests(UnitTestCase):
    indicator = {'code': 'AIQIF-C6.3', 'name': 'Cyber security',
        'scoring_mode': 'independent_conditions', 'conditions': [{'text': 'A firewall and backup recovery policy.'}]}

    def test_repetition_does_not_outrank_precise_evidence_and_windows_do_not_overlap(self):
        sources = [{'id': 'noise', 'text': 'security ' * 3000},
            {'id': 'target', 'text': 'The firewall and backup recovery policy is approved.'}]
        result = select_context(self.indicator, sources, max_chars=4000)
        self.assertEqual(result[0]['id'], 'target')
        self.assertLessEqual(sum(len(s['text']) for s in result), 4000)
        self.assertEqual(result, select_context(self.indicator, sources[::-1], max_chars=4000))
        for i, a in enumerate(result):
            for b in result[i+1:]:
                if a['id'] == b['id']:
                    self.assertTrue(a['text_offset'] + len(a['text']) <= b['text_offset'] or
                        b['text_offset'] + len(b['text']) <= a['text_offset'])

    def test_relevant_content_after_page_prefix_is_retrieved(self):
        text = 'unrelated text ' * 700 + 'The firewall and backup recovery policy is approved.'
        result = select_context(self.indicator, [{'id': 'long', 'text': text}], max_chars=1800)
        self.assertIn('firewall and backup', result[0]['text'])

    def test_passage_across_a_window_boundary_stays_inside_one_window(self):
        # The strongest window (0-1800) cuts the passage; the window holding it overlaps that one.
        lead = 'The firewall and backup recovery policy is approved; the firewall policy and backup recovery plan are reviewed. '
        straddling = 'A recovery drill restored the backup.'
        text = lead + 'x ' * ((1780 - len(lead)) // 2) + straddling + ' y' * 1500
        start = text.index(straddling)
        self.assertLess(start, 1800)
        self.assertGreater(start + len(straddling), 1800)
        result = select_context(self.indicator, [{'id': 'page', 'text': text}], max_chars=4000)
        self.assertTrue(any(straddling in w['text'] for w in result))
        for i, a in enumerate(result):
            for b in result[i + 1:]:
                self.assertTrue(a['text_offset'] + len(a['text']) <= b['text_offset'] or
                                b['text_offset'] + len(b['text']) <= a['text_offset'])

    def test_grounded_tag_targets_an_exact_passage_without_keyword_overlap(self):
        source = {'id': 'tagged', 'text': 'x ' * 3000 + 'Annual register entry ZX17.',
                  'retrieval_hints': [{'indicator_code': 'AIQIF-C6.3', 'start': 6000, 'end': 6027}]}
        result = select_context(self.indicator, [source], max_chars=1800)
        self.assertIn('Annual register entry ZX17.', result[0]['text'])
        self.assertNotIn('retrieval_hints', result[0])
