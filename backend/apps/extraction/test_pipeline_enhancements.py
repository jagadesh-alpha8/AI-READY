import hashlib
import io
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from fpdf import FPDF
from PIL import Image

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.exceptions import (
    ExtractionCancelled,
    ExtractionContinues,
    ExtractionSuperseded,
    PermanentExtractionError,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderUnavailable,
    RecoverableExtractionError,
)
from apps.extraction.models import DocumentPage, ExtractionChunk, ExtractionJob
from apps.extraction.serializers import ExtractionJobSerializer
from apps.extraction.services import rate_limit
from apps.extraction.services.chunk_store import ChunkStore, chunk_hash, chunk_text
from apps.extraction.services.job_phase import phase, phase_label, provider_label
from apps.extraction.services.pdf_reader import PDFPageReader, _page_text
from apps.extraction.services.pipeline import ExtractionPipeline
from apps.extraction.services.recovery import broker_task_ids, recover
from apps.extraction.tasks import _claim, _set_status, retry_countdown
from apps.facts.models import ExtractedFact
from apps.institutions.models import Institution
from apps.sprints.models import Sprint


def make_pdf_bytes(page_texts=('Sample document text for extraction pipeline tests.',)):
    pdf = FPDF()
    for text in page_texts:
        pdf.add_page()
        if text:
            pdf.set_font('Helvetica', size=12)
            pdf.cell(0, 10, text)
    return bytes(pdf.output())


class PipelineEnhancementsTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Test University', city='Metro', state='TS')
        self.user = User.objects.create_user(
            email='coordinator@test.edu',
            username='coordinator',
            password='Password123!',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.institution,
        )
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        pdf_file = SimpleUploadedFile('sample.pdf', make_pdf_bytes(['Page 1 text', 'Page 2 text']), content_type='application/pdf')
        self.document = Document.objects.create(
            sprint=self.sprint,
            document_type='naac_ssr',
            original_filename='sample.pdf',
            file=pdf_file,
            status=Document.Status.UPLOADED,
        )
        self.job = ExtractionJob.objects.create(sprint=self.sprint, document=self.document, status=ExtractionJob.Status.PENDING)

    # -------------------------------------------------------------------------
    # 1. Complete extraction for large documents & ChunkStore
    # -------------------------------------------------------------------------
    def test_chunk_store_lifecycle_and_continuation_cap(self):
        chunks = [
            [{'page_number': 1, 'text': 'Chunk one text'}],
            [{'page_number': 2, 'text': 'Chunk two text'}],
            [{'page_number': 3, 'text': 'Chunk three text'}],
        ]
        # Allow only 2 new calls per attempt
        store = ChunkStore(self.job, max_new_calls=2)
        store.prepare(chunks)

        self.assertEqual(ExtractionChunk.objects.filter(job=self.job).count(), 3)
        self.assertEqual(store.total, 3)

        # Call chunk 1
        store.before_call(1)
        store.completed(1, [{'field_key': 'k1', 'value': 'v1'}])
        self.job.refresh_from_db()
        self.assertEqual(self.job.chunks_completed, 1)

        # Call chunk 2
        store.before_call(2)
        store.completed(2, [{'field_key': 'k2', 'value': 'v2'}])

        # Attempting chunk 3 exceeds the cap (max_new_calls=2), raises ExtractionContinues
        with self.assertRaises(ExtractionContinues) as ctx:
            store.before_call(3)
        self.assertEqual(ctx.exception.done, 2)
        self.assertEqual(ctx.exception.total, 3)

    def test_chunk_store_reuses_completed_chunks_on_retry(self):
        chunks = [
            [{'page_number': 1, 'text': 'Chunk one text'}],
            [{'page_number': 2, 'text': 'Chunk two text'}],
        ]
        store = ChunkStore(self.job)
        store.prepare(chunks)

        # Mark chunk 1 completed
        store.before_call(1)
        store.completed(1, [{'field_key': 'total_students', 'value': '500'}])

        # New store instance (simulating next attempt/worker)
        next_store = ChunkStore(self.job)
        next_store.prepare(chunks)

        reused = next_store.reusable(1)
        self.assertIsNotNone(reused)
        self.assertEqual(reused.facts, [{'field_key': 'total_students', 'value': '500'}])

        # Chunk 2 was not completed, so reusable returns None
        self.assertIsNone(next_store.reusable(2))

    # -------------------------------------------------------------------------
    # 2. Fact persistence idempotency & non-overwriting of reviewed facts
    # -------------------------------------------------------------------------
    def test_fact_idempotency_does_not_duplicate_and_preserves_reviewed_values(self):
        # Pre-existing human-reviewed fact
        existing_reviewed = ExtractedFact.objects.create(
            sprint=self.sprint,
            document=self.document,
            field_name='Total Faculty',
            field_key='total_faculty',
            value='45',
            status=ExtractedFact.Status.CONFIRMED,
            reviewed_by=self.user,
            reviewed_at=timezone.now(),
        )

        mapped_facts = [
            {
                'field_key': 'total_faculty',
                'field_name': 'Total Faculty',
                'value': '100',  # AI found 100, but human confirmed 45
                'confidence_score': 0.95,
            },
            {
                'field_key': 'total_students',
                'field_name': 'Total Students',
                'value': '1200',
                'confidence_score': 0.90,
            },
        ]

        count = ExtractionPipeline._persist_facts(self.job, mapped_facts)
        # 1 new unreviewed fact created; 1 reviewed fact kept untouched (not overwritten)
        self.assertEqual(count, 1)

        # Total faculty must NOT have been overwritten
        existing_reviewed.refresh_from_db()
        self.assertEqual(existing_reviewed.value, '45')
        self.assertEqual(existing_reviewed.status, ExtractedFact.Status.CONFIRMED)

        # Total students was created
        student_fact = ExtractedFact.objects.get(document=self.document, field_key='total_students')
        self.assertEqual(student_fact.value, '1200')

        # Reprocessing the exact same mapped facts again should NOT duplicate rows
        count2 = ExtractionPipeline._persist_facts(self.job, mapped_facts)
        self.assertEqual(count2, 1)
        self.assertEqual(ExtractedFact.objects.filter(document=self.document).count(), 2)

    # -------------------------------------------------------------------------
    # 3. OCR visibility, per-page DocumentPage records and unreadable pages
    # -------------------------------------------------------------------------
    def test_document_page_records_and_ocr_confidence(self):
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = 'Extracted through OCR test: this sentence has well over forty characters for the test.'
        reader = PDFPageReader(ocr_provider=mock_ocr)

        # Create a PDF with 1 digital page and 1 empty page (requiring OCR)
        pdf_bytes = make_pdf_bytes(['Real text on page 1 with more than twenty characters.', ''])
        doc = Document.objects.create(
            sprint=self.sprint,
            document_type='naac_ssr',
            original_filename='pages.pdf',
            file=SimpleUploadedFile('pages.pdf', pdf_bytes, content_type='application/pdf'),
            status=Document.Status.UPLOADED,
        )

        result = reader.read_pages(doc)
        pages = result['pages']
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]['text_source'], 'text')
        self.assertEqual(pages[1]['text_source'], 'ocr')

        # Check DocumentPage rows persisted in DB
        dp1 = DocumentPage.objects.get(document=doc, page_number=1)
        self.assertEqual(dp1.text_source, DocumentPage.Source.TEXT)
        self.assertEqual(dp1.status, DocumentPage.Status.OK)

        dp2 = DocumentPage.objects.get(document=doc, page_number=2)
        self.assertEqual(dp2.text_source, DocumentPage.Source.OCR)
        self.assertEqual(dp2.status, DocumentPage.Status.OK)

    def test_unreadable_page_marks_document_partial(self):
        # OCR provider that returns nothing (unreadable scan/photo)
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = ''
        reader = PDFPageReader(ocr_provider=mock_ocr)

        pdf_bytes = make_pdf_bytes([''])  # Blank page
        doc = Document.objects.create(
            sprint=self.sprint,
            document_type='naac_ssr',
            original_filename='blank.pdf',
            file=SimpleUploadedFile('blank.pdf', pdf_bytes, content_type='application/pdf'),
            status=Document.Status.UPLOADED,
        )

        result = reader.read_pages(doc)
        self.assertIn(1, result['unreadable_pages'])

        pipeline = ExtractionPipeline(page_reader=reader)
        pipeline._record_completeness(self.job, doc, result)
        self.job.refresh_from_db()

        self.assertEqual(self.job.completeness, ExtractionJob.Completeness.PARTIAL)
        self.assertTrue(any(w.get('kind') == 'unreadable_pages' for w in self.job.extraction_warnings))

    # -------------------------------------------------------------------------
    # 4. PDF Table extraction
    # -------------------------------------------------------------------------
    def test_pdf_table_extraction_configuration(self):
        # When PDF_TABLE_EXTRACTION is disabled, table finder is skipped
        with override_settings(PDF_TABLE_EXTRACTION=False):
            page_mock = MagicMock()
            page_mock.get_text.return_value = 'Plain page text'
            text, tables = _page_text(page_mock)
            self.assertEqual(text, 'Plain page text')
            self.assertEqual(tables, [])
            page_mock.find_tables.assert_not_called()

    # -------------------------------------------------------------------------
    # 5. Provider-aware retries & Redis rate limiting
    # -------------------------------------------------------------------------
    def test_rate_limit_retry_after_parsing(self):
        class FakeResponse:
            def __init__(self, headers):
                self.headers = headers

        class FakeError(Exception):
            def __init__(self, headers):
                self.response = FakeResponse(headers)

        # Seconds header
        err1 = FakeError({'retry-after': '45'})
        self.assertEqual(rate_limit.retry_after_seconds(err1), 45.0)

        # Milliseconds header
        err2 = FakeError({'retry-after-ms': '5500'})
        self.assertEqual(rate_limit.retry_after_seconds(err2), 5.5)

        # Rate reset header
        err3 = FakeError({'x-ratelimit-reset-requests': '2m0s'})
        self.assertEqual(rate_limit.retry_after_seconds(err3), 120.0)

    def test_provider_quota_exhausted_distinguishes_credit_and_quota(self):
        err_credit = ProviderQuotaExhausted('Insufficient funds', reason='credit balance is too low')
        self.assertEqual(err_credit.kind, 'credit_exhausted')

        err_quota = ProviderQuotaExhausted('Rate exceeded', reason='insufficient_quota')
        self.assertEqual(err_quota.kind, 'quota_exhausted')

    def test_retry_countdown_bounded_with_jitter_and_retry_after(self):
        countdown = retry_countdown(1)
        self.assertGreaterEqual(countdown, 15)
        self.assertLessEqual(countdown, settings.EXTRACTION_RETRY_BACKOFF_SECONDS)

        # With retry_after exceeding normal base
        err = RecoverableExtractionError(retry_after=60)
        countdown_after = retry_countdown(1, exc=err)
        self.assertGreaterEqual(countdown_after, 60)

    # -------------------------------------------------------------------------
    # 6. Worker interruption recovery
    # -------------------------------------------------------------------------
    def test_recovery_identifies_stale_and_unregistered_jobs(self):
        now = timezone.now()
        def _make_doc(name):
            return Document.objects.create(
                sprint=self.sprint,
                document_type='naac_ssr',
                original_filename=name,
                file=SimpleUploadedFile(name, make_pdf_bytes(['Doc text content']), content_type='application/pdf'),
                status=Document.Status.UPLOADED,
            )

        doc1 = _make_doc('doc1.pdf')
        doc2 = _make_doc('doc2.pdf')
        doc3 = _make_doc('doc3.pdf')

        # 1. never_published job
        unpub = ExtractionJob.objects.create(
            sprint=self.sprint, document=doc1, status=ExtractionJob.Status.PENDING,
            celery_task_id=''
        )
        # Update created_at directly in DB since auto_now_add protects it
        ExtractionJob.objects.filter(id=unpub.id).update(created_at=now - timedelta(seconds=settings.EXTRACTION_RECOVERY_GRACE_SECONDS + 10))

        # 2. worker_lost job (running with stale heartbeat)
        stale_running = ExtractionJob.objects.create(
            sprint=self.sprint, document=doc2, status=ExtractionJob.Status.RUNNING,
            heartbeat_at=now - timedelta(seconds=settings.EXTRACTION_STALE_SECONDS + 10)
        )

        # 3. Completed job (must NEVER be recovered)
        completed_job = ExtractionJob.objects.create(
            sprint=self.sprint, document=doc3, status=ExtractionJob.Status.COMPLETED
        )

        with patch('apps.extraction.services.recovery.broker_task_ids', return_value=set()):
            with patch('apps.extraction.services.recovery.live_workers', return_value=set()):
                report = recover(dry_run=True, now=now)

        recovered_ids = {r['job_id'] for r in report}
        self.assertIn(str(unpub.id), recovered_ids)
        self.assertIn(str(stale_running.id), recovered_ids)
        self.assertNotIn(str(completed_job.id), recovered_ids)

    def test_claim_prevents_duplicate_workers_processing_same_job(self):
        worker1 = 'worker-node-1'
        worker2 = 'worker-node-2'

        # First claim succeeds
        claimed = _claim(self.job, worker=worker1)
        self.assertTrue(claimed)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, ExtractionJob.Status.RUNNING)
        self.assertEqual(self.job.worker, worker1)

        # Second claim while heartbeat is fresh fails
        job_copy = ExtractionJob.objects.get(id=self.job.id)
        claimed_again = _claim(job_copy, worker=worker2)
        self.assertFalse(claimed_again)

    # -------------------------------------------------------------------------
    # 7. Truthful monitor status & serializer
    # -------------------------------------------------------------------------
    def test_monitor_serializer_phases_and_provider_display(self):
        self.job.status = ExtractionJob.Status.RUNNING
        self.job.current_step = ExtractionJob.Step.EXTRACTING_FACTS
        self.job.chunks_total = 8
        self.job.chunks_completed = 3
        self.job.pages_total = 20
        self.job.pages_done = 20
        self.job.ocr_pages = 4
        self.job.save()

        serializer = ExtractionJobSerializer(self.job)
        data = serializer.data

        self.assertEqual(data['phase'], 'extracting_facts')
        self.assertIn('3 of 8 chunks', data['phase_label'])
        self.assertEqual(data['chunks_total'], 8)
        self.assertEqual(data['chunks_completed'], 3)
        self.assertEqual(data['ocr_pages'], 4)

        # Single provider mode label never shows "no router"
        with override_settings(AI_PROCESSING_MODE='single', AI_BASE_URL='https://api.openai.com/v1', AI_MODEL='gpt-4o'):
            prov = provider_label(self.job)
            self.assertIn('single provider: api.openai.com, gpt-4o', prov)
            self.assertNotIn('no router', prov)
