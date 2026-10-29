import base64
import os
import unittest
from unittest.mock import MagicMock, patch

import django
import pymupdf
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.models import AIUsage, DocumentPage, ExtractionJob
from apps.extraction.services import stub
from apps.extraction.services.openai_fact_extractor import IdentityAuditFieldMapper
from apps.extraction.services.pdf_reader import PDFPageReader
from apps.extraction.services.pipeline import ExtractionPipeline
from apps.extraction.services.vision_fallback import (
    VisionResult,
    model_supports_vision,
    render_page_image,
    run_vision_fallback,
    supports_vision,
    validate_vision_fact,
)
from apps.facts.auto_confirm import auto_confirm
from apps.facts.models import ExtractedFact
from apps.institutions.models import Institution
from apps.sprints.models import Sprint


def make_pdf_bytes(pages_text):
    """Create a minimal PDF in memory with the given text per page."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.django_db
class VisionFallbackUnitTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Test University')
        self.user = User.objects.create_user(username='tester', email='tester@test.com', role=User.Role.CONSULTANT)
        self.sprint = Sprint.objects.create(name='Audit Sprint', institution=self.institution, created_by=self.user)
        self.document = Document.objects.create(
            sprint=self.sprint,
            title='Audit Report',
            original_filename='audit.pdf',
            file=SimpleUploadedFile('audit.pdf', b'%PDF-1.4 dummy', content_type='application/pdf'),
        )

    def test_model_supports_vision_detection(self):
        # Vision models
        self.assertTrue(model_supports_vision('gpt-4o'))
        self.assertTrue(model_supports_vision('gpt-4o-mini'))
        self.assertTrue(model_supports_vision('gpt-4-turbo'))
        self.assertTrue(model_supports_vision('claude-3-5-sonnet-20241022'))
        self.assertTrue(model_supports_vision('claude-haiku-4-5-20251001'))
        self.assertTrue(model_supports_vision('custom-pixtral-12b'))
        self.assertTrue(model_supports_vision('qwen-vl-max'))

        # Non-vision models
        self.assertFalse(model_supports_vision('gpt-3.5-turbo'))
        self.assertFalse(model_supports_vision('gpt-4'))
        self.assertFalse(model_supports_vision('gpt-4-0613'))
        self.assertFalse(model_supports_vision('claude-2.1'))
        self.assertFalse(model_supports_vision('claude-instant-1.2'))
        self.assertFalse(model_supports_vision('o1-mini'))

        # Whitelist override via settings
        with override_settings(AI_VISION_MODELS=['my-special-model']):
            self.assertTrue(model_supports_vision('my-special-model'))

        # Disabled via settings
        with override_settings(AI_VISION_ENABLED=False):
            self.assertFalse(model_supports_vision('gpt-4o'))

    def test_render_page_image(self):
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        page.draw_rect(pymupdf.Rect(10, 10, 100, 100), color=(1, 0, 0))
        b64_str = render_page_image(page, dpi=72)
        doc.close()

        raw_bytes = base64.b64decode(b64_str)
        # Verify it is valid PNG
        self.assertTrue(raw_bytes.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_validate_vision_fact_quote_validation(self):
        page_text = 'The university has 350 full-time faculty members across all departments.'
        valid_raw = {
            'field_name': 'Total Faculty',
            'field_key': 'total_faculty',
            'value': '350',
            'data_type': 'number',
            'pillar': 'aiqif_c1',
            'owner_role': 'hr_officer',
            'source_page': '1',
            'source_snippet': 'has 350 full-time faculty members',
            'confidence_score': 0.95,
            'confidence_reason': 'Stated explicitly in report.',
            'fact_kind': 'context',
            'naac_metric': None,
            'profile_field': None,
            'aiqif_indicators': [],
        }

        # Valid fact with matching snippet
        validated = validate_vision_fact(valid_raw, 1, page_text)
        self.assertIsNotNone(validated)
        self.assertEqual(validated['extraction_method'], 'vision')
        self.assertEqual(validated['source_page'], '1')
        self.assertEqual(validated['value'], 350)

        # Invalid fact: hallucinated quote not in page text
        invalid_raw = dict(valid_raw)
        invalid_raw['source_snippet'] = 'We have 9999 AI researchers in the lab'
        rejected = validate_vision_fact(invalid_raw, 1, page_text)
        self.assertIsNone(rejected)

        # Invalid fact: missing snippet
        no_snippet = dict(valid_raw)
        no_snippet['source_snippet'] = ''
        self.assertIsNone(validate_vision_fact(no_snippet, 1, page_text))

    def test_auto_confirm_never_confirms_vision_facts(self):
        # Create a fact extracted via vision with 0.99 confidence
        fact = ExtractedFact.objects.create(
            sprint=self.sprint,
            document=self.document,
            field_name='AI Labs',
            field_key='ai_labs_count',
            value='4',
            normalized_value=4,
            data_type=ExtractedFact.DataType.NUMBER,
            pillar='aiqif_c1',
            owner_role='lab_admin',
            source_page='1',
            source_snippet='4 specialized AI laboratories',
            confidence_score=0.99,
            confidence_reason='Vision AI verified from lab layout table',
            extraction_method='vision',
            status=ExtractedFact.Status.EXTRACTED,
        )

        from django.test import override_settings
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            result = auto_confirm(self.document.extracted_facts.all())
        self.assertNotIn(str(fact.id), result['confirmed'])
        run = fact.verifications.get()
        self.assertIn('Read by the vision fallback; always reviewed by a person.', run.blockers)

        fact.refresh_from_db()
        # Remains in EXTRACTED state for human review
        self.assertEqual(fact.status, ExtractedFact.Status.EXTRACTED)

    @patch('apps.extraction.services.vision_fallback.run_vision_fallback')
    @patch('apps.extraction.services.vision_fallback.supports_vision', return_value=True)
    def test_pdf_reader_vision_fallback_triggered_on_scanned_page(self, mock_supports, mock_run_vision):
        # Blank/scanned PDF page (no native text)
        pdf_data = make_pdf_bytes([''])
        doc_file = SimpleUploadedFile('scanned.pdf', pdf_data, content_type='application/pdf')
        doc = Document.objects.create(sprint=self.sprint, title='Scanned Doc', file=doc_file)

        mock_fact = {
            'field_name': 'Student Count',
            'field_key': 'student_count',
            'value': '1200',
            'normalized_value': 1200,
            'data_type': 'number',
            'pillar': 'aiqif_c1',
            'owner_role': 'registrar',
            'source_page': '1',
            'source_snippet': 'Total student strength is 1200',
            'confidence_score': 0.95,
            'confidence_reason': 'Vision extraction from scanned certificate',
            'extraction_method': 'vision',
            'fact_kind': 'context',
            'naac_metric': '',
            'profile_field': '',
            'aiqif_mappings': [],
            'tagging_notes': [],
        }
        mock_run_vision.return_value = VisionResult(
            status='ok',
            text='Annual Report. Total student strength is 1200.',
            facts=[mock_fact],
            confidence=0.95,
        )

        reader = PDFPageReader(ocr_provider=stub.NullOCRProvider(), min_text_chars_per_page=20)
        res = reader.read_pages(doc)

        self.assertEqual(res['pages_read'], 1)
        self.assertEqual(res['vision_pages'], 1)
        page_0 = res['pages'][0]
        self.assertEqual(page_0['text_source'], 'vision')
        self.assertEqual(page_0['read_status'], 'ok')
        self.assertEqual(page_0['vision_status'], 'ok')
        self.assertEqual(len(page_0['vision_facts']), 1)

        # Verify DocumentPage cache saved
        dp = DocumentPage.objects.get(document=doc, page_number=1)
        self.assertEqual(dp.text_source, DocumentPage.Source.VISION)
        self.assertEqual(dp.status, DocumentPage.Status.OK)
        self.assertEqual(dp.vision_status, 'ok')
        self.assertEqual(len(dp.vision_facts), 1)

        # Idempotent second read: reuses cached page without calling vision fallback again
        mock_run_vision.reset_mock()
        second_res = reader.read_pages(doc)
        self.assertEqual(second_res['vision_pages'], 1)
        self.assertEqual(len(second_res['vision_facts']), 1)
        mock_run_vision.assert_not_called()

    @patch('apps.extraction.services.vision_fallback.supports_vision', return_value=False)
    def test_pdf_reader_vision_unavailable_marks_page_unreadable(self, mock_supports):
        # Scanned page with no native text, Null OCR, and vision unsupported
        pdf_data = make_pdf_bytes([''])
        doc_file = SimpleUploadedFile('scanned_no_vision.pdf', pdf_data, content_type='application/pdf')
        doc = Document.objects.create(sprint=self.sprint, title='Scanned No Vision', file=doc_file)

        reader = PDFPageReader(ocr_provider=stub.NullOCRProvider(), min_text_chars_per_page=20)
        res = reader.read_pages(doc)

        self.assertEqual(res['vision_pages'], 0)
        self.assertEqual(res['unreadable_pages'], [1])
        page_0 = res['pages'][0]
        self.assertEqual(page_0['read_status'], 'unreadable')
        self.assertEqual(page_0['vision_status'], 'unavailable')
        self.assertIn('vision fallback was unavailable', page_0['warning'])

        dp = DocumentPage.objects.get(document=doc, page_number=1)
        self.assertEqual(dp.status, DocumentPage.Status.UNREADABLE)
        self.assertEqual(dp.vision_status, 'unavailable')
        self.assertFalse(dp.reusable)

    @patch('apps.extraction.services.vision_fallback.run_vision_fallback')
    @patch('apps.extraction.services.vision_fallback.supports_vision', return_value=True)
    def test_pipeline_merges_vision_facts_and_idempotency(self, mock_supports, mock_run_vision):
        pdf_data = make_pdf_bytes([''])
        doc_file = SimpleUploadedFile('pipeline_vision.pdf', pdf_data, content_type='application/pdf')
        doc = Document.objects.create(sprint=self.sprint, title='Pipeline Vision Doc', file=doc_file)

        mock_fact = {
            'field_name': 'Placement Percentage',
            'field_key': 'placement_percentage',
            'value': '92%',
            'normalized_value': 92.0,
            'data_type': 'percentage',
            'pillar': 'aiqif_c1',
            'owner_role': 'placement_officer',
            'source_page': '1',
            'source_snippet': 'Achieved 92% placement rate',
            'confidence_score': 0.94,
            'confidence_reason': 'Extracted via vision fallback',
            'extraction_method': 'vision',
            'fact_kind': 'context',
            'naac_metric': '',
            'profile_field': '',
            'aiqif_mappings': [],
            'tagging_notes': [],
        }
        mock_run_vision.return_value = VisionResult(
            status='ok',
            text='Placement Cell: Achieved 92% placement rate this year.',
            facts=[mock_fact],
            confidence=0.94,
        )

        job = ExtractionJob.objects.create(document=doc, sprint=self.sprint)
        pipeline = ExtractionPipeline(
            page_reader=PDFPageReader(ocr_provider=stub.NullOCRProvider(), min_text_chars_per_page=20),
            classifier=stub.KnownMetadataClassifier(),
            fact_extractor=stub.NullFactExtractor(),
            field_mapper=IdentityAuditFieldMapper(),
            gap_detector=stub.NullGapDetector(),
            conflict_checker=stub.NullConflictChecker(),
        )

        pipeline.run(job)

        job.refresh_from_db()
        self.assertEqual(job.vision_pages, 1)

        # Check extracted fact
        facts = ExtractedFact.objects.filter(document=doc)
        self.assertEqual(facts.count(), 1)
        fact = facts.first()
        self.assertEqual(fact.field_key, 'placement_percentage')
        self.assertEqual(fact.extraction_method, 'vision')
        # Crucial: never auto-confirmed
        self.assertEqual(fact.status, ExtractedFact.Status.EXTRACTED)

        # Reprocessing must be idempotent (no duplicate rows)
        pipeline.run(job)
        self.assertEqual(ExtractedFact.objects.filter(document=doc).count(), 1)

    def test_ai_usage_recording_stage_vision_fallback(self):
        job = ExtractionJob.objects.create(document=self.document, sprint=self.sprint)
        from apps.extraction.usage import record_openai_usage, usage_scope

        mock_resp = MagicMock()
        mock_resp.usage.prompt_tokens = 450
        mock_resp.usage.completion_tokens = 120
        mock_resp.usage.prompt_tokens_details.cached_tokens = 0
        mock_resp.usage.completion_tokens_details.reasoning_tokens = 0

        with usage_scope(job=job, stage=AIUsage.Stage.VISION_FALLBACK):
            row = record_openai_usage(mock_resp, provider='openai', model='gpt-4o-mini', duration_ms=850)

        self.assertIsNotNone(row)
        self.assertEqual(row.stage, AIUsage.Stage.VISION_FALLBACK)
        self.assertEqual(row.extraction_job, job)
        self.assertEqual(row.input_tokens, 450)
        self.assertEqual(row.output_tokens, 120)
