"""Every expected page reaches the stored page rows the assessment freezes, or the gap is reported.

Covers: a locked page write is retried, a page that still cannot be saved fails the read (recoverable)
instead of letting a job report complete, image files store a page row, the coverage accounting, and the
page_coverage command's read-only report and repair.
"""
import hashlib
import io
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from fpdf import FPDF
from PIL import Image

from apps.documents.models import Document
from apps.extraction.exceptions import RecoverableExtractionError
from apps.extraction.models import DocumentPage
from apps.extraction.services import pdf_reader, stub
from apps.extraction.services.pdf_reader import PDFPageReader
from apps.institutions.models import Institution
from apps.scoring.capability.pipeline_diagnostics import page_coverage
from apps.scoring.capability.report_projection import build_report_view
from apps.scoring.test_report_projection import report_fixture
from apps.sprints.models import Sprint

TEXT = 'Native text on this page, comfortably longer than the minimum meaningful length. Page '


def pdf_bytes(pages):
    pdf = FPDF()
    for n in range(1, pages + 1):
        pdf.add_page()
        pdf.set_font('Helvetica', size=12)
        pdf.cell(0, 10, f'{TEXT}{n}.')
    return bytes(pdf.output())


def png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (40, 20), 'white').save(buf, format='PNG')
    return buf.getvalue()


class _Base(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='Test University', city='Metro', state='TS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.ocr = MagicMock()
        self.ocr.extract_text.return_value = 'Publications log: 120 journal articles and 4 patents recorded in 2023.'

    def document(self, name, data, pages):
        return Document.objects.create(
            sprint=self.sprint, document_type='naac_ssr', original_filename=name, page_count=pages,
            checksum=hashlib.sha256(data).hexdigest(), status=Document.Status.PROCESSED,
            file=SimpleUploadedFile(name, data))


@patch.object(pdf_reader, 'PAGE_SAVE_RETRY_DELAYS', (0, 0, 0))
class PageSaveTests(_Base):
    def test_locked_write_is_retried_until_saved(self):
        doc = self.document('a.pdf', pdf_bytes(2), 2)
        real = DocumentPage.objects.update_or_create
        calls = {'n': 0}

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] <= 2:
                raise OperationalError('database is locked')
            return real(*args, **kwargs)

        with patch.object(DocumentPage.objects, 'update_or_create', side_effect=flaky):
            PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        self.assertEqual(sorted(DocumentPage.objects.filter(document=doc).values_list('page_number', flat=True)), [1, 2])

    def test_page_that_cannot_be_saved_fails_the_read_instead_of_completing(self):
        doc = self.document('b.pdf', pdf_bytes(3), 3)
        real = DocumentPage.objects.update_or_create

        def lock_page_two(*args, **kwargs):
            if kwargs.get('page_number') == 2:
                raise OperationalError('database is locked')
            return real(*args, **kwargs)

        with patch.object(DocumentPage.objects, 'update_or_create', side_effect=lock_page_two):
            with self.assertRaises(RecoverableExtractionError) as ctx:
                PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        self.assertIn('pages 2', str(ctx.exception))
        # The retry reuses the saved pages and re-reads only the missing one.
        PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        self.assertEqual(DocumentPage.objects.filter(document=doc).count(), 3)

    def test_non_lock_error_is_not_retried(self):
        doc = self.document('c.pdf', pdf_bytes(1), 1)
        with patch.object(DocumentPage.objects, 'update_or_create', side_effect=ValueError('bad')) as mocked:
            with self.assertRaises(RecoverableExtractionError):
                PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        self.assertEqual(mocked.call_count, 2)  # the page loop and the one final pass, no backoff retries


class ImagePageRowTests(_Base):
    def test_image_stores_a_citable_page_row(self):
        doc = self.document('log.png', png_bytes(), 1)
        PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        row = DocumentPage.objects.get(document=doc, page_number=1)
        self.assertEqual((row.status, row.text_source), ('ok', 'ocr'))
        self.assertIn('120 journal articles', row.text)

    def test_image_without_ocr_is_recorded_as_unavailable_not_missing(self):
        doc = self.document('scan.png', png_bytes(), 1)
        PDFPageReader(ocr_provider=stub.NullOCRProvider()).read_pages(doc)
        row = DocumentPage.objects.get(document=doc, page_number=1)
        self.assertEqual((row.status, row.text_source), ('ocr_unavailable', 'none'))


class PageCoverageTests(SimpleTestCase):
    def test_accounts_for_missing_unreadable_and_blank_pages(self):
        manifest = [
            {'document_id': 'a', 'filename': 'report.pdf', 'expected_pages': 5, 'pages': [
                {'page_id': 'a1', 'number': 1, 'status': 'ok'},
                {'page_id': 'a2', 'number': 2, 'status': 'ok'},
                {'page_id': 'a4', 'number': 4, 'status': 'unreadable'},
                {'page_id': 'a5', 'number': 5, 'status': 'ok'}]},
            {'document_id': 'b', 'filename': 'log.png', 'expected_pages': 1, 'pages': []},
        ]
        sources = [{'id': 'a1'}, {'id': 'a5'}]
        coverage = page_coverage(manifest, sources)
        a, b = coverage['documents']
        self.assertEqual((a['missing_rows'], a['not_ok'], a['blank_after_cleanup'], a['frozen']), ([3], [4], [2], 2))
        self.assertEqual(b['missing_rows'], [1])
        self.assertEqual(coverage['totals'], {'expected': 6, 'rows': 4, 'frozen': 2, 'missing_rows': 2,
                                              'not_ok': 1, 'blank_after_cleanup': 1})
        self.assertFalse(coverage['complete'])

    def test_blank_and_unreadable_pages_do_not_make_coverage_incomplete(self):
        manifest = [{'document_id': 'a', 'filename': 'x.pdf', 'expected_pages': 2, 'pages': [
            {'page_id': 'a1', 'number': 1, 'status': 'ok'}, {'page_id': 'a2', 'number': 2, 'status': 'unreadable'}]}]
        self.assertTrue(page_coverage(manifest, [])['complete'])


class EvidenceSummaryWordingTests(SimpleTestCase):
    def test_summary_states_expected_pages_when_some_are_unavailable(self):
        report, actions = report_fixture()
        report['diagnostics'] = {**report['diagnostics'], 'readable_pages': 792,
                                 'unreadable_or_unavailable_pages': 12, 'source_documents': 12}
        self.assertEqual(build_report_view(report, actions)['evidence_summary'],
                         '12 source documents and 792 of 804 expected pages were included in this saved assessment.')

    def test_summary_unchanged_when_every_page_is_readable(self):
        report, actions = report_fixture()
        self.assertEqual(build_report_view(report, actions)['evidence_summary'],
                         '1 source document and 1 readable page were included in this saved assessment.')


class PageCoverageCommandTests(_Base):
    def test_reports_gap_and_repairs_native_text_pages(self):
        doc = self.document('aqar.pdf', pdf_bytes(4), 4)
        PDFPageReader(ocr_provider=self.ocr).read_pages(doc)
        DocumentPage.objects.filter(document=doc, page_number__in=[2, 3]).delete()

        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command('page_coverage', str(self.sprint.pk), stdout=out)
        self.assertIn('2-3', out.getvalue())
        self.assertEqual(DocumentPage.objects.filter(document=doc).count(), 2)  # read-only by default

        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command('page_coverage', str(self.sprint.pk), '--repair', stdout=out)  # plan only
        self.assertIn('native text 2-3; needs OCR/vision -', out.getvalue())
        self.assertEqual(DocumentPage.objects.filter(document=doc).count(), 2)

        out = io.StringIO()
        call_command('page_coverage', str(self.sprint.pk), '--repair', '--apply', stdout=out)
        self.assertIn('COMPLETE', out.getvalue().split('After repair:')[1])
        self.assertEqual(DocumentPage.objects.filter(document=doc).count(), 4)
        self.assertIn(f'{TEXT}2.', DocumentPage.objects.get(document=doc, page_number=2).text)

    def test_repairs_image_with_no_page_row(self):
        doc = self.document('log.png', png_bytes(), 1)
        out = io.StringIO()
        with patch('apps.scoring.management.commands.page_coverage.PDFPageReader',
                   lambda: PDFPageReader(ocr_provider=self.ocr)):
            call_command('page_coverage', str(self.sprint.pk), '--repair', '--apply', stdout=out)
        self.assertTrue(DocumentPage.objects.filter(document=doc, page_number=1, status='ok').exists())

    def test_refuses_repair_when_stored_file_no_longer_matches_checksum(self):
        doc = self.document('ssr.pdf', pdf_bytes(2), 2)
        Document.objects.filter(pk=doc.pk).update(checksum='0' * 64)
        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command('page_coverage', str(self.sprint.pk), '--repair', '--apply', stdout=out)
        self.assertIn('checksum differs', out.getvalue())
        self.assertFalse(DocumentPage.objects.filter(document=doc).exists())
