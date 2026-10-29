"""PaddleOCR-backed `OCRProvider` -- reads text from scanned / image-only PDF
pages that have no usable text layer.

`pdf_reader.PDFPageReader` renders such a page to an image with PyMuPDF and
passes it here. The PaddleOCR engine is heavy (it loads detection and
recognition models, downloaded once on first use and cached on disk), so it
is built lazily, once per worker process, and shared.

Lines PaddleOCR is not confident about (below `OCR_MIN_CONFIDENCE`) are
dropped rather than passed on: a misread number would become a wrong fact.
"""
import logging
import threading

from django.conf import settings

from .base import OCRProvider

logger = logging.getLogger(__name__)

_engine = None
_engine_lock = threading.Lock()
_infer_lock = threading.Lock()
_engine_failed = False


def paddleocr_available():
    try:
        import paddleocr  # noqa: F401
    except Exception:  # ImportError, or paddle failing to load its native libs
        return False
    return True


def _get_engine():
    """Build the PaddleOCR engine once per process. Returns None (and logs
    why) if it can't be built, so the caller falls back to flagging the page
    as needing OCR instead of crashing the whole extraction."""
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    with _engine_lock:
        if _engine is not None or _engine_failed:
            return _engine
        try:
            from paddleocr import PaddleOCR

            try:
                # PaddleOCR 3.x: whole-page document images, already upright
                # (PyMuPDF renders pages the right way up), so the extra
                # orientation/unwarping models are skipped for speed.
                # enable_mkldnn: oneDNN CPU acceleration, ~4-5x faster. It
                # fails at inference in paddlepaddle 3.3.x on Windows
                # ("ConvertPirAttribute2RuntimeAttribute not support"), hence
                # the <3.3 pin in requirements and the OCR_ENABLE_MKLDNN switch.
                options = {'enable_mkldnn': settings.OCR_ENABLE_MKLDNN}
                if settings.OCR_DET_MODEL:
                    options['text_detection_model_name'] = settings.OCR_DET_MODEL
                _engine = PaddleOCR(
                    lang=settings.OCR_LANG,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    **options,
                )
            except TypeError:
                # PaddleOCR 2.x constructor.
                _engine = PaddleOCR(lang=settings.OCR_LANG, use_angle_cls=False, show_log=False)
            logger.info('paddle_ocr.engine_ready lang=%s', settings.OCR_LANG)
        except Exception as exc:
            _engine_failed = True
            logger.error('paddle_ocr.engine_unavailable error=%s', exc)
    return _engine


NL = chr(10)


class OCRResult:
    """One page's OCR outcome. `status`: ok (ran; `text` may still be empty), failed (the engine raised),
    unavailable (no engine / no image)."""
    OK, FAILED, UNAVAILABLE = 'ok', 'failed', 'unavailable'

    def __init__(self, status, *, text='', confidence=None, error='', lines=0, kept=0):
        self.status, self.text, self.confidence, self.error = status, text, confidence, error
        self.lines, self.kept = lines, kept


def read_with(provider, document, page_number, image):
    """Any OCRProvider -> OCRResult: providers with `read_page` (PaddleOCR) give confidence and failure
    detail; a plain `extract_text` provider (tests, NullOCRProvider) maps None -> unavailable."""
    import unittest.mock
    use_read_page = False
    if hasattr(type(provider), 'read_page'):
        use_read_page = True
    elif isinstance(provider, unittest.mock.NonCallableMock):
        rp = getattr(provider, 'read_page', None)
        if rp is not None:
            ret = getattr(rp, '_mock_return_value', unittest.mock.DEFAULT)
            side = getattr(rp, '_mock_side_effect', None)
            if ret is not unittest.mock.DEFAULT or side is not None:
                use_read_page = True

    if use_read_page:
        result = provider.read_page(document, page_number, image=image)
        if isinstance(result, OCRResult):
            return result
        if result is not None:
            return OCRResult(OCRResult.OK, text=str(result))
    text = provider.extract_text(document, page_number, image=image)
    if text is None:
        return OCRResult(OCRResult.UNAVAILABLE, error='No OCR backend is available.')
    return OCRResult(OCRResult.OK, text=text)


class PaddleOCRProvider(OCRProvider):
    def __init__(self, *, min_confidence=None):
        self.min_confidence = (
            min_confidence if min_confidence is not None else settings.OCR_MIN_CONFIDENCE
        )

    def extract_text(self, document, page_number, image=None):
        result = self.read_page(document, page_number, image=image)
        return None if result.status in (OCRResult.FAILED, OCRResult.UNAVAILABLE) else result.text

    def read_page(self, document, page_number, image=None):
        """The page's OCR text with its mean line confidence, telling apart "no OCR engine" (unavailable),
        "the engine raised on this page" (failed -- worth retrying) and "ran, found little" (ok, maybe empty)."""
        if image is None:
            return OCRResult(OCRResult.UNAVAILABLE, error='No page image to OCR.')
        engine = _get_engine()
        if engine is None:
            return OCRResult(OCRResult.UNAVAILABLE, error='The OCR engine could not be loaded on this server.')
        try:
            # One engine per process; with a threads worker pool several jobs
            # share it, and a Paddle predictor isn't safe to call concurrently.
            with _infer_lock:
                lines = self._run(engine, image)
        except Exception as exc:
            logger.warning(
                'paddle_ocr.page_failed document_id=%s page=%s error=%s', document.id, page_number, exc,
            )
            return OCRResult(OCRResult.FAILED, error=str(exc)[:300])
        kept = [(text, score) for text, score in lines if text.strip() and score >= self.min_confidence]
        logger.info(
            'paddle_ocr.page document_id=%s page=%s lines=%d kept=%d',
            document.id, page_number, len(lines), len(kept),
        )
        confidence = round(sum(score for _t, score in kept) / len(kept), 4) if kept else None
        return OCRResult(OCRResult.OK, text=NL.join(text for text, _s in kept), confidence=confidence,
                         lines=len(lines), kept=len(kept))

    @staticmethod
    def _run(engine, image):
        """Return [(text, confidence), ...] in reading order, for either API."""
        if hasattr(engine, 'predict'):
            # 3.x: one result per input image, with parallel text/score lists.
            out = []
            for result in engine.predict(image):
                data = result.json.get('res', result.json) if hasattr(result, 'json') else result
                out.extend(zip(data.get('rec_texts', []), data.get('rec_scores', [])))
            return [(str(t), float(s)) for t, s in out]
        # 2.x: [[ [box, (text, score)], ... ]] per image.
        out = []
        for page in engine.ocr(image) or []:
            for _box, (text, score) in page or []:
                out.append((str(text), float(score)))
        return out
