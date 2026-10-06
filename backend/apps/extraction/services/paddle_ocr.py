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


class PaddleOCRProvider(OCRProvider):
    def __init__(self, *, min_confidence=None):
        self.min_confidence = (
            min_confidence if min_confidence is not None else settings.OCR_MIN_CONFIDENCE
        )

    def extract_text(self, document, page_number, image=None):
        if image is None:
            return None
        engine = _get_engine()
        if engine is None:
            return None
        try:
            lines = self._run(engine, image)
        except Exception as exc:
            logger.warning(
                'paddle_ocr.page_failed document_id=%s page=%s error=%s', document.id, page_number, exc,
            )
            return None
        kept = [text for text, score in lines if text.strip() and score >= self.min_confidence]
        logger.info(
            'paddle_ocr.page document_id=%s page=%s lines=%d kept=%d',
            document.id, page_number, len(lines), len(kept),
        )
        return '\n'.join(kept)

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
