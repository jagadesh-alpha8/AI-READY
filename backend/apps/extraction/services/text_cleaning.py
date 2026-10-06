"""Text quality check and cleanup for page text, whether it came from a PDF's
own text layer (PyMuPDF) or from OCR (PaddleOCR).

Runs between "read every page" and "chunk for the AI" in `pdf_reader.py`:
the per-page structure is kept (each fact cites a page number), but every
page's text is normalised, and running headers/footers that repeat on most
pages are dropped so they don't waste chunk space or get mistaken for facts.
"""
import re
import unicodedata
from collections import Counter

_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
# Only letters either side: "intro-\nduction" -> "introduction", but a
# "2023-\n24" academic year is left alone.
_HYPHEN_WRAP_RE = re.compile(r'([A-Za-z])-\n([a-z])')
_SPACES_RE = re.compile(r'[ \t  -​]+')
_BLANK_LINES_RE = re.compile(r'\n{3,}')
_DIGITS_RE = re.compile(r'\d+')
_PAGE_NUMBER_LINE_RE = re.compile(r'^(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?$', re.IGNORECASE)

#: Lines this close to the top/bottom of a page are header/footer candidates.
_EDGE_LINES = 1


def is_meaningful_text(text, min_chars):
    """The "Is meaningful?" check: enough characters, and mostly real
    letters/digits rather than symbols or unmapped-glyph garbage (a PDF with
    a broken font map extracts as boxes and punctuation, which is as useless
    to the AI as no text at all and should go to OCR instead)."""
    stripped = (text or '').strip()
    if len(stripped) < min_chars:
        return False
    visible = [c for c in stripped if not c.isspace()]
    if not visible:
        return False
    alnum_ratio = sum(c.isalnum() for c in visible) / len(visible)
    garbage_ratio = stripped.count('�') / len(visible)
    return alnum_ratio >= 0.5 and garbage_ratio <= 0.1


def clean_text(text):
    """Normalise one page's text: unicode forms, control characters, words
    hyphenated across a line break, runs of spaces, and excess blank lines."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('­', '')  # soft hyphen
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _CONTROL_CHARS_RE.sub('', text)
    text = _HYPHEN_WRAP_RE.sub(r'\1\2', text)
    text = '\n'.join(_SPACES_RE.sub(' ', line).strip() for line in text.split('\n'))
    text = _BLANK_LINES_RE.sub('\n\n', text)
    return text.strip()


def remove_repeated_headers_footers(page_texts, min_pages=4, min_share=0.6):
    """Drop lines that sit at the top/bottom of most pages (institution name
    banners, "Confidential", "Page 3 of 40", ...).

    A line counts as repeated when, with its digits masked, it appears in the
    very first/last line of at least `min_share` of the pages -- only the
    outermost line, so a table's column-header row repeated under a page
    title is kept (it carries the meaning of the columns). Only
    applied to documents of `min_pages`+ pages -- on a short document a
    "repeat" is as likely to be real content. Bare page-number lines at the
    edges are always dropped.
    """
    if len(page_texts) < min_pages:
        return [_drop_edge_page_numbers(t) for t in page_texts]

    def key(line):
        return _DIGITS_RE.sub('#', line.strip().lower())

    counts = Counter()
    for text in page_texts:
        lines = [l for l in text.split('\n') if l.strip()]
        edge = lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]
        counts.update({key(l) for l in edge})

    threshold = max(3, int(len(page_texts) * min_share))
    repeated = {k for k, n in counts.items() if n >= threshold and len(k) <= 120}

    cleaned = []
    for text in page_texts:
        lines = text.split('\n')
        non_blank = [i for i, l in enumerate(lines) if l.strip()]
        edge_idx = set(non_blank[:_EDGE_LINES] + non_blank[-_EDGE_LINES:])
        kept = [
            line for i, line in enumerate(lines)
            if not (i in edge_idx and (key(line) in repeated or _PAGE_NUMBER_LINE_RE.match(line.strip())))
        ]
        cleaned.append('\n'.join(kept))
    return cleaned


def _drop_edge_page_numbers(text):
    lines = text.split('\n')
    non_blank = [i for i, l in enumerate(lines) if l.strip()]
    edge_idx = set(non_blank[:1] + non_blank[-1:])
    return '\n'.join(
        line for i, line in enumerate(lines)
        if not (i in edge_idx and _PAGE_NUMBER_LINE_RE.match(line.strip()))
    )
