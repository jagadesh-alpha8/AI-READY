"""Real `PageReader` implementation for PDF documents -- digital and scanned.

Flow, per document:

    Open PDF with PyMuPDF
      -> for each page: extract the text layer
           -> meaningful?   yes: use it
                            no:  render the page to an image -> OCR (PaddleOCR)
      -> combine all pages, drop repeated headers/footers, clean each page
      -> (chunking happens next, in openai_fact_extractor._build_chunks)

Pages stay separate in the output (each fact the AI extracts cites a page
number); "combine" here means the header/footer pass looks across the whole
document. A page that has no usable text even after OCR is marked
`requires_ocr` rather than silently reported as empty.

Only PDF is implemented here. Anything else is reported honestly as an
unsupported format -- not guessed at, not silently treated as empty.
"""
import logging
import os

import pymupdf
import numpy as np
from django.conf import settings

from ..exceptions import PermanentExtractionError, RecoverableExtractionError
from . import stub
from .base import PageReader
from .text_cleaning import clean_text, is_meaningful_text, remove_repeated_headers_footers

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf'}


def default_ocr_provider():
    """PaddleOCR when enabled and installed; otherwise the honest no-op."""
    if settings.OCR_PROVIDER == 'paddle':
        from .paddle_ocr import PaddleOCRProvider, paddleocr_available

        if paddleocr_available():
            return PaddleOCRProvider()
        logger.warning('pdf_reader.ocr_unavailable provider=paddle reason=paddleocr not installed')
    return stub.NullOCRProvider()


class PDFPageReader(PageReader):
    """Reads a PDF's pages via PyMuPDF, falling back to OCR page by page.

    `ocr_provider` defaults to `default_ocr_provider()` (PaddleOCR, or
    `stub.NullOCRProvider` when OCR is disabled/unavailable) -- pass any
    `base.OCRProvider` to swap it.
    """

    def __init__(self, *, ocr_provider=None, min_text_chars_per_page=None, ocr_dpi=None):
        self.ocr_provider = ocr_provider or default_ocr_provider()
        self.min_text_chars_per_page = (
            min_text_chars_per_page
            if min_text_chars_per_page is not None
            else settings.PDF_MIN_TEXT_CHARS_PER_PAGE
        )
        self.ocr_dpi = ocr_dpi or settings.OCR_DPI

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
                data = document.file.read()
            finally:
                document.file.close()
        except OSError as exc:
            # Storage I/O hiccup reading the file itself -- worth a retry.
            logger.warning('pdf_reader.io_error document_id=%s error=%s', document.id, exc)
            raise RecoverableExtractionError(f'Could not read document file: {exc}') from exc

        try:
            pdf = pymupdf.open(stream=data, filetype='pdf')
        except Exception as exc:
            # Malformed/corrupt PDF -- retrying the same bytes won't help.
            logger.error('pdf_reader.parse_error document_id=%s error=%s', document.id, exc)
            raise PermanentExtractionError(f'Could not parse PDF: {exc}') from exc

        try:
            return self._read_pdf(document, pdf, max_pages)
        except (PermanentExtractionError, RecoverableExtractionError):
            raise
        except Exception as exc:
            logger.error('pdf_reader.parse_error document_id=%s error=%s', document.id, exc)
            raise PermanentExtractionError(f'Could not parse PDF: {exc}') from exc
        finally:
            pdf.close()

    def _read_pdf(self, document, pdf, max_pages):
        total_page_count = pdf.page_count
        pages_to_read = min(total_page_count, max_pages) if max_pages else total_page_count

        raw_texts = []
        sources = []
        ocr_warnings = []
        for index in range(pages_to_read):
            page_number = index + 1
            page = pdf.load_page(index)
            text = page.get_text('text', sort=True) or ''
            source = 'text'

            if not is_meaningful_text(text, self.min_text_chars_per_page):
                image = None if isinstance(self.ocr_provider, stub.NullOCRProvider) else self._render(page)
                ocr_text = self.ocr_provider.extract_text(document, page_number, image=image)
                if ocr_text is None:
                    source = 'none'
                    ocr_warnings.append(
                        f'Page {page_number} has little/no extractable text and requires OCR '
                        f'(no OCR backend available).'
                    )
                elif is_meaningful_text(ocr_text, self.min_text_chars_per_page):
                    text, source = ocr_text, 'ocr'
                else:
                    # OCR ran but found nothing readable: a blank, photo-only
                    # or illegible page. Keep whatever little there was.
                    text = text if len(text.strip()) >= len(ocr_text.strip()) else ocr_text
                    source = 'none'
                    ocr_warnings.append(
                        f'Page {page_number} has no readable text, even after OCR '
                        f'(blank, photo-only or illegible page).'
                    )
            raw_texts.append(text)
            sources.append(source)

        cleaned = [clean_text(t) for t in remove_repeated_headers_footers([clean_text(t) for t in raw_texts])]

        pages_out = [
            {
                'page_number': index + 1,
                'text': text,
                'char_count': len(text),
                'text_source': source,  # 'text' (PDF text layer) | 'ocr' | 'none'
                'requires_ocr': source == 'none',
                'tables': [],
            }
            for index, (text, source) in enumerate(zip(cleaned, sources))
        ]

        result = {
            'pages': pages_out,
            'page_count': total_page_count,
            'pages_read': len(pages_out),
            'ocr_pages': sources.count('ocr'),
            'requires_ocr': any(p['requires_ocr'] for p in pages_out),
            'ocr_warnings': ocr_warnings,
            'metadata': {k: v for k, v in (pdf.metadata or {}).items() if v},
            'format_supported': True,
        }
        logger.info(
            'pdf_reader.read document_id=%s page_count=%d pages_read=%d ocr_pages=%d unreadable_pages=%d',
            document.id, total_page_count, len(pages_out), result['ocr_pages'], len(ocr_warnings),
        )
        return result

    def _render(self, page):
        """Page -> BGR uint8 image at `ocr_dpi`, the layout PaddleOCR expects."""
        pix = page.get_pixmap(dpi=self.ocr_dpi, colorspace=pymupdf.csRGB, alpha=False)
        # Rows can be padded (stride > width*3), so slice by stride first.
        rows = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
        rgb = rows[:, :pix.width * 3].reshape(pix.height, pix.width, 3)
        return np.ascontiguousarray(rgb[:, :, ::-1])
