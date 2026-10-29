"""Page-level AI vision fallback for PDF reading.

When a PDF page has no extractable text layer and local OCR returns no readable
text (or fails/is unavailable), this module renders ONLY that single page as an
image and sends it to the configured AI provider, provided the model supports
vision/multimodal inputs.

Key behaviors:
- Do not resend pages already read successfully (managed via DocumentPage cache).
- Record OCR and vision status, extracted text, errors, and AI usage on DocumentPage.
- Extract page text and structured facts directly from the image.
- Validate extracted facts against page-specific quotes from the page text.
- Tag facts with extraction_method='vision' so the review workflow routes them to
  human review and auto_confirm never auto-confirms them.
- If the model or provider lacks vision support, mark the page as unreadable and
  report that fallback was unavailable.
"""
import base64
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import pymupdf
from django.conf import settings

from apps.facts.models import ExtractedFact
from .openai_fact_extractor import FACT_ITEM_SCHEMA, OpenAIFactExtractor

logger = logging.getLogger(__name__)

# Known models that do NOT support vision/multimodal input
NON_VISION_PATTERNS = [
    'gpt-3.5',
    'gpt-4-0',
    'gpt-4-32k',
    'gpt-4-base',
    'o1-mini',
    'o1-preview',
    'claude-2',
    'claude-instant',
    'text-embedding',
    'text-davinci',
    'babbage',
    'whisper',
    'tts',
]

# Known models / substrings that DO support vision/multimodal input
VISION_PATTERNS = [
    'gpt-4o',
    'gpt-4-turbo',
    'gpt-4-vision',
    'chatgpt-4o',
    'claude-3',
    'claude-haiku-4',
    'vision',
    '-vl',
    'gemini',
    'pixtral',
    'llava',
    'qwen-vl',
    'internvl',
]

VISION_SYSTEM_PROMPT = """You are analyzing one page image from an institutional audit document for a higher-education AI-readiness audit platform.

Perform two tasks:
1. Extract and faithfully transcribe all readable text visible on this page into `page_text`. Preserve paragraphs, tables, lists, and numbers accurately. If the page is completely blank or contains only non-text graphics/photos with no readable text, return an empty string for `page_text`.
2. Extract any structured facts visible on this page that describe institutional data, metrics, or AI capabilities (such as student/faculty counts, AI courses, computing facilities, MoUs, placements, research, policies).

Rules:
- Extract only information directly visible in the image. Never guess or extrapolate.
- Every fact must have an exact or closely quoted `source_snippet` that also appears verbatim in `page_text`.
- Set `source_page` to the current page number.
- `value` must always be a plain string as read off the page.
- `confidence_score` must be between 0.0 and 1.0 reflecting certainty.
- If no clear audit facts are present, return an empty list for `facts`.
"""

VISION_RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'page_text': {
            'type': 'string',
            'description': 'Full transcribed text visible on this page, or empty string if no legible text exists.',
        },
        'facts': {
            'type': 'array',
            'description': 'Structured facts visible on this page.',
            'items': FACT_ITEM_SCHEMA,
        },
    },
    'required': ['page_text', 'facts'],
    'additionalProperties': False,
}


@dataclass
class VisionResult:
    status: str  # 'ok', 'no_text', 'failed', 'unavailable'
    text: str = ''
    facts: List[dict] = field(default_factory=list)
    error: str = ''
    confidence: Optional[float] = None


def model_supports_vision(model: Optional[str], provider: Optional[str] = None) -> bool:
    """Return True if the model is known or configured to support vision/multimodal input."""
    if not getattr(settings, 'AI_VISION_ENABLED', True):
        return False
    if not model or not isinstance(model, str):
        return False

    model_clean = model.strip().lower()

    # Explicit whitelist in settings
    configured = getattr(settings, 'AI_VISION_MODELS', [])
    if configured and model_clean in [m.lower() for m in configured]:
        return True

    # Known non-vision blacklist
    for non_v in NON_VISION_PATTERNS:
        if non_v in model_clean:
            return False

    if model_clean == 'gpt-4':
        return False

    # Known vision indicators
    for v in VISION_PATTERNS:
        if v in model_clean:
            return True

    return False


def supports_vision(service=None) -> bool:
    """Check if the currently configured or provided AI service supports vision input."""
    if not getattr(settings, 'AI_VISION_ENABLED', True):
        return False
    if service is None:
        try:
            from .ai_service import get_ai_service
            service = get_ai_service()
        except Exception:
            return False

    if hasattr(service, 'supports_vision'):
        try:
            return bool(service.supports_vision())
        except Exception:
            pass

    model = getattr(service, 'model', None)
    return model_supports_vision(model)


def render_page_image(page, dpi: Optional[int] = None) -> str:
    """Render a PyMuPDF page to an in-memory PNG and return base64-encoded string."""
    render_dpi = dpi or getattr(settings, 'AI_VISION_DPI', 150)
    pix = page.get_pixmap(dpi=render_dpi, colorspace=pymupdf.csRGB, alpha=False)
    png_bytes = pix.tobytes('png')
    return base64.b64encode(png_bytes).decode('ascii')


def _quote_in_text(snippet: str, text: str) -> bool:
    """Check if snippet (or a normalized prefix) is grounded in the page text."""
    if not snippet or not text:
        return False
    clean_snippet = ' '.join(snippet.strip().lower().split())
    clean_text = ' '.join(text.strip().lower().split())
    if clean_snippet in clean_text:
        return True
    # If quote is long, check substantial 30-char slice
    if len(clean_snippet) > 30 and clean_snippet[:30] in clean_text:
        return True
    return False


def validate_vision_fact(raw_fact: dict, page_number: int, page_text: str) -> Optional[dict]:
    """Validate a fact extracted by vision AI against quotes and field constraints.

    Enforces:
    - extraction_method = 'vision'
    - source_page = str(page_number)
    - source_snippet must appear in page_text
    """
    if not isinstance(raw_fact, dict):
        return None

    snippet = raw_fact.get('source_snippet')
    if not snippet or not isinstance(snippet, str) or not snippet.strip():
        logger.info('vision_fallback.fact_rejected_no_snippet: %r', raw_fact)
        return None

    if page_text and not _quote_in_text(snippet, page_text):
        logger.info('vision_fallback.fact_rejected_unsupported_quote: %r', snippet)
        return None

    extractor = OpenAIFactExtractor()
    valid_pages = {str(page_number)}

    raw_copy = dict(raw_fact)
    raw_copy['source_page'] = str(page_number)

    try:
        validated = extractor._validate_fact(raw_copy, valid_pages, page_text)
        validated['extraction_method'] = 'vision'
        return validated
    except Exception as exc:
        logger.info('vision_fallback.fact_validation_error: %s', exc)
        return None


def run_vision_fallback(
    document,
    page,
    page_number: int,
    *,
    job=None,
    ai_service=None,
    dpi: Optional[int] = None,
) -> VisionResult:
    """Render page image, call configured AI vision model, validate text and facts."""
    if not getattr(settings, 'AI_VISION_ENABLED', True):
        return VisionResult(status='unavailable', error='Vision fallback disabled')

    service = ai_service
    if service is None:
        try:
            from .ai_service import get_ai_service
            service = get_ai_service()
        except Exception as exc:
            return VisionResult(status='unavailable', error=f'AI service unavailable: {exc}')

    if hasattr(service, 'supports_vision') and not service.supports_vision():
        model = getattr(service, 'model', 'unknown')
        return VisionResult(status='unavailable', error=f"Model '{model}' does not support vision")

    try:
        image_b64 = render_page_image(page, dpi=dpi)
    except Exception as exc:
        logger.warning('vision_fallback.render_failed page=%s error=%s', page_number, exc)
        return VisionResult(status='failed', error=f'Page render failed: {exc}')

    from apps.extraction.models import AIUsage
    from apps.extraction.usage import usage_scope

    user_content = f"Please transcribe the text and extract all structured facts from page {page_number}."
    try:
        with usage_scope(job=job, document=document, stage=AIUsage.Stage.VISION_FALLBACK):
            response = service.extract_structured_data(
                system_prompt=VISION_SYSTEM_PROMPT,
                user_content=user_content,
                response_schema=VISION_RESPONSE_SCHEMA,
                schema_name='page_vision_extraction',
                image_b64=image_b64,
            )
    except Exception as exc:
        logger.warning('vision_fallback.request_failed page=%s error=%s', page_number, exc)
        return VisionResult(status='failed', error=str(exc))

    if not isinstance(response, dict):
        return VisionResult(status='failed', error='Invalid response format from vision AI')

    page_text = (response.get('page_text') or '').strip()
    raw_facts = response.get('facts') or []

    valid_facts = []
    for raw in raw_facts:
        validated = validate_vision_fact(raw, page_number, page_text)
        if validated:
            valid_facts.append(validated)

    if not page_text and not valid_facts:
        return VisionResult(status='no_text', text='', facts=[], confidence=0.0)

    conf = (
        sum(f['confidence_score'] for f in valid_facts) / len(valid_facts)
        if valid_facts else 0.95
    )
    return VisionResult(status='ok', text=page_text, facts=valid_facts, confidence=conf)

