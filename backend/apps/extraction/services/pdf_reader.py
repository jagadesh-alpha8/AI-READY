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

Word (.docx), Excel (.xlsx), CSV and images (.png/.jpg, via OCR) are read by
`office_reader` into the same page shape. Anything else (.doc, .xls, .zip) is
reported honestly as an unsupported format with a note the user is shown --
not guessed at, not silently treated as empty.
"""
import logging
import os

import pymupdf
import numpy as np
from django.conf import settings

from ..exceptions import PermanentExtractionError, RecoverableExtractionError
from . import stub
from .base import PageReader
from .paddle_ocr import OCRResult, read_with
from .text_cleaning import clean_text, is_meaningful_text, remove_repeated_headers_footers

logger = logging.getLogger(__name__)

from . import office_reader

SUPPORTED_EXTENSIONS = {'.pdf'} | office_reader.OFFICE_EXTENSIONS | office_reader.IMAGE_EXTENSIONS


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

    def read_pages(self, document, max_pages=None, job=None):
        job = job or getattr(self, 'job', None)
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
                'format_note': office_reader.UNREADABLE_NOTES.get(
                    ext, f'Files of type "{ext or "(no extension)"}" cannot be read; upload a PDF, Word, Excel, '
                         'CSV or image file.'),
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

        if ext != '.pdf':
            return self._read_other(document, ext, data, max_pages)

        try:
            pdf = pymupdf.open(stream=data, filetype='pdf')
        except Exception as exc:
            # Malformed/corrupt PDF -- retrying the same bytes won't help.
            logger.error('pdf_reader.parse_error document_id=%s error=%s', document.id, exc)
            raise PermanentExtractionError(f'Could not parse PDF: {exc}') from exc

        try:
            return self._read_pdf(document, pdf, max_pages, job=job)
        except (PermanentExtractionError, RecoverableExtractionError):
            raise
        except Exception as exc:
            logger.error('pdf_reader.parse_error document_id=%s error=%s', document.id, exc)
            raise PermanentExtractionError(f'Could not parse PDF: {exc}') from exc
        finally:
            pdf.close()

    def _read_pdf(self, document, pdf, max_pages, job=None):
        """Native text first, OCR only for pages without a usable text layer, vision fallback when OCR fails/finds
        no text, tables kept as rows and columns.

        Each page's outcome is saved as a DocumentPage (when `document` is a saved Document), so a later read
        of the same document -- a retry, the vector index, an evidence assessment -- reuses every page that was
        read fine and re-runs OCR/vision only on pages that failed or came back unreadable."""
        total_page_count = pdf.page_count
        pages_to_read = min(total_page_count, max_pages) if max_pages else total_page_count
        cache = _page_cache(document)

        raw_texts, reads = [], []
        ocr_done = vision_done = unreadable = reused = 0
        for index in range(pages_to_read):
            page_number = index + 1
            cached = cache.get(page_number)
            if cached is not None and cached.reusable:
                read = _PageRead(
                    cached.text, cached.text_source, 'ok', cached.ocr_confidence, '',
                    cached.tables, cached.ocr_attempts,
                    ocr_status=cached.ocr_status or '',
                    ocr_error=cached.ocr_error or '',
                    vision_status=cached.vision_status or '',
                    vision_error=cached.vision_error or '',
                    vision_attempts=cached.vision_attempts or 0,
                    vision_facts=cached.vision_facts or [],
                )
                reused += 1
            else:
                read = self._read_page(
                    document, pdf.load_page(index), page_number,
                    previous_attempts=cached.ocr_attempts if cached else 0,
                    previous_vision_attempts=cached.vision_attempts if cached else 0,
                    job=job,
                )
                _save_page(document, page_number, read)
            raw_texts.append(read.text)
            reads.append(read)
            ocr_done += read.source == 'ocr'
            vision_done += read.source == 'vision'
            unreadable += read.status != 'ok'
            self._progress(index + 1, pages_to_read, ocr_done, unreadable, vision_done)

        cleaned = [
            _with_tables(clean_text(t), read.tables, page_number)
            for page_number, (t, read) in enumerate(
                zip(remove_repeated_headers_footers([clean_text(t) for t in raw_texts]), reads), start=1)
        ]

        pages_out = [
            {
                'page_number': index + 1,
                'text': text,
                'char_count': len(text),
                'text_source': read.source,  # 'text' (PDF text layer) | 'ocr' | 'vision' | 'none'
                'requires_ocr': read.source == 'none',
                'read_status': read.status,  # ok | unreadable | ocr_failed | ocr_unavailable | vision_failed | vision_unavailable
                'ocr_confidence': read.confidence,
                'warning': read.warning,
                'tables': read.tables,
                'ocr_status': read.ocr_status,
                'ocr_error': read.ocr_error,
                'vision_status': read.vision_status,
                'vision_error': read.vision_error,
                'vision_facts': read.vision_facts,
            }
            for index, (text, read) in enumerate(zip(cleaned, reads))
        ]
        ocr_warnings = [read.warning for read in reads if read.warning]
        all_vision_facts = [fact for read in reads for fact in (read.vision_facts or [])]

        result = {
            'pages': pages_out,
            'page_count': total_page_count,
            'pages_read': len(pages_out),
            'ocr_pages': ocr_done,
            'vision_pages': vision_done,
            'requires_ocr': any(p['requires_ocr'] for p in pages_out),
            'ocr_warnings': ocr_warnings,
            'unreadable_pages': [p['page_number'] for p in pages_out if p['read_status'] != 'ok'],
            'tables': sum(len(p['tables']) for p in pages_out),
            'vision_facts': all_vision_facts,
            'metadata': {k: v for k, v in (pdf.metadata or {}).items() if v},
            'format_supported': True,
        }
        logger.info(
            'pdf_reader.read document_id=%s page_count=%d pages_read=%d ocr_pages=%d vision_pages=%d unreadable_pages=%d '
            'tables=%d reused=%d',
            document.id, total_page_count, len(pages_out), result['ocr_pages'], result['vision_pages'],
            len(ocr_warnings), result['tables'], reused,
        )
        return result

    def _read_page(self, document, page, page_number, previous_attempts=0, previous_vision_attempts=0, job=None):
        """One page: its text layer (with tables), else OCR, else Vision Fallback."""
        from .vision_fallback import run_vision_fallback, supports_vision

        text, tables = _page_text(page)
        if is_meaningful_text(text, self.min_text_chars_per_page):
            return _PageRead(
                text, 'text', 'ok', None, '', tables, previous_attempts,
                ocr_status='skipped', vision_status='skipped',
                vision_attempts=previous_vision_attempts,
            )

        # Local OCR step
        ocr_attempts = previous_attempts
        ocr_status = ''
        ocr_error = ''
        ocr_confidence = None
        ocr_text = text

        if isinstance(self.ocr_provider, stub.NullOCRProvider):
            ocr_status = 'ocr_unavailable'
            ocr_error = 'no OCR backend available'
        else:
            result = None
            for dpi in dict.fromkeys(d for d in (self.ocr_dpi, settings.OCR_RETRY_DPI) if d):
                ocr_attempts += 1
                result = read_with(self.ocr_provider, document, page_number, self._render(page, dpi))
                if result.status != OCRResult.OK or is_meaningful_text(result.text, self.min_text_chars_per_page):
                    break
            if result.status == OCRResult.UNAVAILABLE:
                ocr_status = 'ocr_unavailable'
                ocr_error = result.error or 'OCR backend unavailable'
            elif result.status == OCRResult.FAILED:
                ocr_status = 'ocr_failed'
                ocr_error = result.error or 'engine error'
            elif is_meaningful_text(result.text, self.min_text_chars_per_page):
                # OCR succeeded!
                return _PageRead(
                    result.text, 'ocr', 'ok', result.confidence, '', [], ocr_attempts,
                    ocr_status='ok', ocr_error='', vision_status='skipped',
                    vision_attempts=previous_vision_attempts,
                )
            else:
                # OCR ran but found nothing readable
                ocr_status = 'no_text'
                ocr_confidence = result.confidence
                if len(result.text.strip()) > len(text.strip()):
                    ocr_text = result.text

        # At this point, native text is not meaningful, and local OCR either failed, was unavailable, or returned no text.
        # Check if vision fallback is supported
        if not supports_vision():
            # Vision fallback is unavailable for current model/provider/settings
            warning = (
                f'Page {page_number}: local text extraction and OCR found no readable text, '
                f'and vision fallback was unavailable.'
            )
            return _PageRead(
                ocr_text, 'none', 'unreadable', ocr_confidence, warning, [], ocr_attempts,
                ocr_status=ocr_status, ocr_error=ocr_error, vision_status='unavailable',
                vision_error='Vision fallback unavailable or not supported by model',
                vision_attempts=previous_vision_attempts,
            )

        # Run vision fallback
        vision_attempts = previous_vision_attempts + 1
        vision_res = run_vision_fallback(document, page, page_number, job=job)

        if vision_res.status == 'ok':
            page_text = vision_res.text if vision_res.text.strip() else ocr_text
            return _PageRead(
                page_text, 'vision', 'ok', vision_res.confidence, '', [], ocr_attempts,
                ocr_status=ocr_status, ocr_error=ocr_error, vision_status='ok',
                vision_error='', vision_attempts=vision_attempts,
                vision_facts=vision_res.facts,
            )
        elif vision_res.status == 'no_text':
            warning = f'Page {page_number} has no readable text, even after vision fallback.'
            return _PageRead(
                ocr_text, 'none', 'unreadable', ocr_confidence, warning, [], ocr_attempts,
                ocr_status=ocr_status, ocr_error=ocr_error, vision_status='no_text',
                vision_error='', vision_attempts=vision_attempts,
            )
        else:  # 'failed' or other error
            warning = (
                f'Page {page_number}: vision fallback failed ({vision_res.error or "error"}); '
                f'it is tried again when the document is processed again.'
            )
            return _PageRead(
                ocr_text, 'none', 'unreadable', ocr_confidence, warning, [], ocr_attempts,
                ocr_status=ocr_status, ocr_error=ocr_error, vision_status='failed',
                vision_error=vision_res.error or '', vision_attempts=vision_attempts,
            )

    def _progress(self, done, total, ocr_done, unreadable, vision_done=0):
        callback = getattr(self, 'on_progress', None)
        if callback is not None:
            callback(done=done, total=total, ocr=ocr_done, unreadable=unreadable, vision=vision_done)

    def _read_other(self, document, ext, data, max_pages):
        """Word / Excel / CSV / image -> the same result shape as a PDF."""
        warnings = []
        try:
            if ext == '.docx':
                texts = office_reader.read_docx(data)
            elif ext == '.xlsx':
                texts = office_reader.read_xlsx(data)
            elif ext == '.csv':
                texts = office_reader.read_csv(data)
            else:  # image
                image = office_reader.image_to_bgr(data)
                ocr_text = (None if isinstance(self.ocr_provider, stub.NullOCRProvider)
                            else self.ocr_provider.extract_text(document, 1, image=image))
                if not ocr_text or not is_meaningful_text(ocr_text, self.min_text_chars_per_page):
                    warnings.append('No readable text was found in this image'
                                    + (' (OCR is not available on this server).' if ocr_text is None else '.'))
                texts = [ocr_text or '']
        except Exception as exc:
            logger.error('office_reader.parse_error document_id=%s ext=%s error=%s', document.id, ext, exc)
            raise PermanentExtractionError(f'Could not read the {ext} file: {exc}') from exc
        if max_pages:
            texts = texts[:max_pages]
        source = 'ocr' if ext in office_reader.IMAGE_EXTENSIONS else 'text'
        pages_out = [
            {'page_number': i + 1, 'text': clean_text(t), 'char_count': len(t), 'text_source': source if t.strip() else 'none',
             'requires_ocr': False, 'tables': []}
            for i, t in enumerate(texts)
        ]
        if not pages_out and not warnings:
            warnings.append(f'The {ext} file contains no text.')
        logger.info('office_reader.read document_id=%s ext=%s pages=%d', document.id, ext, len(pages_out))
        return {
            'pages': pages_out, 'page_count': len(pages_out), 'pages_read': len(pages_out),
            'ocr_pages': len(pages_out) if source == 'ocr' else 0, 'requires_ocr': bool(warnings) and source == 'ocr',
            'ocr_warnings': warnings, 'metadata': {'format': ext.lstrip('.')}, 'format_supported': True,
        }

    def _render(self, page, dpi=None):
        """Page -> BGR uint8 image at `dpi` (default OCR_DPI), the layout PaddleOCR expects."""
        pix = page.get_pixmap(dpi=dpi or self.ocr_dpi, colorspace=pymupdf.csRGB, alpha=False)
        # Rows can be padded (stride > width*3), so slice by stride first.
        rows = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
        rgb = rows[:, :pix.width * 3].reshape(pix.height, pix.width, 3)
        return np.ascontiguousarray(rgb[:, :, ::-1])


class _PageRead:
    """One page's outcome (saved as a DocumentPage)."""

    def __init__(self, text, source, status, confidence, warning, tables, attempts,
                 ocr_status='', ocr_error='', vision_status='', vision_error='',
                 vision_attempts=0, vision_facts=None):
        self.text, self.source, self.status = text, source, status
        self.confidence = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None
        self.warning, self.tables, self.attempts = warning, tables or [], attempts
        self.ocr_status = ocr_status or ''
        self.ocr_error = ocr_error or ''
        self.vision_status = vision_status or ''
        self.vision_error = vision_error or ''
        self.vision_attempts = vision_attempts or 0
        self.vision_facts = vision_facts or []


def _page_cache(document):
    """{page_number: DocumentPage} of a saved Document; {} for anything else (e.g. a benchmark source file)."""
    from apps.documents.models import Document

    from ..models import DocumentPage

    if not isinstance(document, Document) or not document.pk:
        return {}
    return {p.page_number: p for p in DocumentPage.objects.filter(document=document)}


def _save_page(document, page_number, read):
    from apps.documents.models import Document

    from ..models import DocumentPage

    if not isinstance(document, Document) or not document.pk:
        return
    try:
        conf = float(read.confidence) if isinstance(read.confidence, (int, float)) and not isinstance(read.confidence, bool) else None
        DocumentPage.objects.update_or_create(document=document, page_number=page_number, defaults={
            'text': read.text, 'text_source': read.source, 'status': read.status, 'ocr_confidence': conf,
            'ocr_attempts': read.attempts, 'warning': read.warning, 'tables': read.tables,
            'ocr_status': read.ocr_status, 'ocr_error': read.ocr_error,
            'vision_status': read.vision_status, 'vision_error': read.vision_error,
            'vision_attempts': read.vision_attempts, 'vision_facts': read.vision_facts,
        })
    except Exception as exc:  # the read itself succeeded; a failed save only costs a re-read next time
        logger.warning('pdf_reader.page_cache_save_failed document_id=%s page=%s error=%s', document.id,
                       page_number, exc)


# -- tables ---------------------------------------------------------------------------------------------------

def _placeholder(index):
    """A letters-only line marking where table `index` sits in the page text: header/footer removal masks
    digits, so a numbered marker repeated on many pages could be dropped as a footer."""
    return 'AIOSTABLEMARKER' + ''.join(chr(97 + int(c)) for c in str(index))


def _page_text(page):
    """(text, tables) of a page's text layer. Without tables, the plain sorted text (as before). With tables,
    the text outside them in reading order, each table replaced by a placeholder line; the tables themselves
    are returned as {index, header, rows, bbox} and rendered back in by _with_tables."""
    text = page.get_text('text', sort=True) or ''
    if not settings.PDF_TABLE_EXTRACTION:
        return text, []
    try:
        found = page.find_tables().tables
    except Exception as exc:  # table detection is an addition: never lose the page over it
        logger.warning('pdf_reader.table_detection_failed page=%s error=%s', page.number + 1, exc)
        return text, []
    tables = []
    for table in found:
        rows = [[_cell(c) for c in row] for row in (table.extract() or [])]
        rows = [row for row in rows if any(row)]
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue  # one line or one column: not a table worth restructuring
        header = [_cell(c) for c in (table.header.names if table.header and table.header.names else [])]
        if header and rows[0] == header:
            rows = rows[1:]
        elif not any(header):
            header, rows = rows[0], rows[1:]
        tables.append({'index': len(tables) + 1, 'header': header, 'rows': rows,
                       'bbox': [round(v, 1) for v in table.bbox]})
    if not tables:
        return text, []
    boxes = [pymupdf.Rect(t['bbox']) for t in tables]
    items = []
    for x0, y0, x1, y1, block_text, _no, kind in page.get_text('blocks', sort=True):
        if kind != 0:
            continue
        rect = pymupdf.Rect(x0, y0, x1, y1)
        if any(abs(rect & box) >= 0.5 * max(abs(rect), 1) for box in boxes):
            continue  # this text is a table cell: it is in the table rows
        items.append((y0, block_text.strip()))
    items += [(box.y0, _placeholder(t['index'])) for box, t in zip(boxes, tables)]
    return '\n'.join(line for _y, line in sorted(items, key=lambda item: item[0]) if line), tables


def _cell(value):
    return ' '.join(str(value).split()) if value is not None else ''


def render_table(table, page_number):
    """A table as text the AI reads row by row, with its header and page, e.g.
    [Table 1 on page 5 -- columns: Year | Students]
    Year: 2023 | Students: 420"""
    header = table.get('header') or []
    lines = [f'[Table {table["index"]} on page {page_number} -- columns: {" | ".join(header) or "(none)"}]']
    for row in table.get('rows') or []:
        if header and len(header) == len(row):
            lines.append(' | '.join(f'{h}: {v}' if h else v for h, v in zip(header, row)))
        else:
            lines.append(' | '.join(row))
    return '\n'.join(lines)


def _with_tables(text, tables, page_number):
    for table in tables or []:
        marker = _placeholder(table['index'])
        rendered = render_table(table, page_number)
        text = text.replace(marker, rendered) if marker in text else f'{text}\n{rendered}'.strip()
    return text
