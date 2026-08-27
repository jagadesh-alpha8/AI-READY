"""Real `PageReader` implementation for PDF documents.

Reads a PDF's real page text (and, where present, its tables and Info-dict
metadata) via `pdfplumber` -- pure Python, no system-level binary (poppler,
ghostscript, ...) required. A page with too little extractable text to be
real content is marked `requires_ocr` rather than silently reported as
empty; see `OCRProvider` in `base.py` for how a real OCR backend plugs in.

Only PDF is implemented here (per this task's scope). Anything else is
reported honestly as an unsupported format -- not guessed at, not silently
treated as empty content with no explanation.
"""
import logging
import os

import pdfplumber
from django.conf import settings

from ..exceptions import PermanentExtractionError, RecoverableExtractionError
from . import stub
from .base import PageReader

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf'}


class PDFPageReader(PageReader):
    """Reads a PDF's pages via pdfplumber, page by page.

    `ocr_provider` defaults to `stub.NullOCRProvider` (performs no OCR,
    honestly reports pages that need it) -- pass a real implementation of
    `base.OCRProvider` once one exists, without needing any other change
    here or in `ExtractionPipeline`.
    """

    def __init__(self, *, ocr_provider=None, min_text_chars_per_page=None):
        self.ocr_provider = ocr_provider or stub.NullOCRProvider()
        self.min_text_chars_per_page = (
            min_text_chars_per_page
            if min_text_chars_per_page is not None
            else settings.PDF_MIN_TEXT_CHARS_PER_PAGE
        )

    def read_pages(self, document, max_pages=None):
        if not document.file:
            raise PermanentExtractionError(f'Document {document.id} has no file attached.')

        ext = os.path.splitext(document.original_filename or document.file.name or '')[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.info('pdf_reader.unsupported_format document_id=%s ext=%s', document.id, ext)
            return {
                'pages': [],
                'page_count': None,
                'pages_read': 0,
                'requires_ocr': False,
                'ocr_warnings': [],
                'metadata': {},
                'format_supported': False,
                'format_note': f'PDFPageReader only reads PDF files; got "{ext or "(no extension)"}".',
            }

        try:
            document.file.open('rb')
            try:
                with pdfplumber.open(document.file) as pdf:
                    return self._read_pdf(document, pdf, max_pages)
            finally:
                document.file.close()
        except (PermanentExtractionError, RecoverableExtractionError):
            raise
        except OSError as exc:
            # Storage I/O hiccup reading the file itself -- worth a retry.
            logger.warning('pdf_reader.io_error document_id=%s error=%s', document.id, exc)
            raise RecoverableExtractionError(f'Could not read document file: {exc}') from exc
        except Exception as exc:
            # Anything pdfplumber/pdfminer raises for a malformed/corrupt
            # PDF -- retrying the same bytes won't produce a different result.
            logger.error('pdf_reader.parse_error document_id=%s error=%s', document.id, exc)
            raise PermanentExtractionError(f'Could not parse PDF: {exc}') from exc

    def _read_pdf(self, document, pdf, max_pages):
        total_page_count = len(pdf.pages)
        pages_to_read = pdf.pages[:max_pages] if max_pages else pdf.pages

        pages_out = []
        ocr_warnings = []
        for page_number, page in enumerate(pages_to_read, start=1):
            text = (page.extract_text() or '').strip()
            tables = page.extract_tables() or []
            requires_ocr = len(text) < self.min_text_chars_per_page

            if requires_ocr:
                ocr_text = self.ocr_provider.extract_text(document, page_number)
                if ocr_text:
                    text = ocr_text.strip()
                    requires_ocr = len(text) < self.min_text_chars_per_page
                if requires_ocr:
                    ocr_warnings.append(
                        f'Page {page_number} has little/no extractable text and requires OCR '
                        f'(no OCR backend configured yet).'
                    )

            pages_out.append({
                'page_number': page_number,
                'text': text,
                'char_count': len(text),
                'requires_ocr': requires_ocr,
                'tables': tables,
            })

        result = {
            'pages': pages_out,
            'page_count': total_page_count,
            'pages_read': len(pages_out),
            'requires_ocr': any(p['requires_ocr'] for p in pages_out),
            'ocr_warnings': ocr_warnings,
            'metadata': dict(pdf.metadata or {}),
            'format_supported': True,
        }
        logger.info(
            'pdf_reader.read document_id=%s page_count=%d pages_read=%d requires_ocr=%s',
            document.id, total_page_count, len(pages_out), result['requires_ocr'],
        )
        return result
