"""Splits a document's already-read pages into embeddable chunks.

Pure and dependency-free: it takes the page dicts `apps.extraction.services.
pdf_reader.PDFPageReader` already produces and returns plain dicts. No Django
model, no Pinecone, no embedding provider — so the chunking rules can be unit
tested directly, and the same function serves any future caller that has page
text in hand.

Two rules shape the output:

* **A chunk never spans a page.** Page number is the citation this platform
  promises ("according to Faculty_Report.pdf, page 17"), and a chunk built
  from two pages could only cite one of them honestly.
* **A chunk never splits a sentence**, unless a single sentence is itself
  longer than the chunk budget — at which point it is hard-split rather than
  dropped, because losing text silently is worse than an awkward boundary.

Sizes come from settings (`VECTOR_CHUNK_*`), not from constants here, so the
configuration lives in one place alongside every other tunable.
"""
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

#: Sentence boundary: a `.`, `?` or `!` followed by whitespace. Deliberately
#: simple — a full NLP sentence splitter would be a heavy dependency for a
#: boundary that only needs to be *reasonable*, since overlap already covers
#: the cost of an occasional bad split.
_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')

#: Collapses the runs of whitespace and stray newlines that PDF text
#: extraction leaves behind, so an embedding is computed over prose rather
#: than over layout artefacts.
_WHITESPACE = re.compile(r'\s+')


def clean_text(text):
    """Normalise extracted text: collapse whitespace, strip the edges."""
    if not text:
        return ''
    return _WHITESPACE.sub(' ', text).strip()


def _split_sentences(text):
    return [s for s in _SENTENCE_BOUNDARY.split(text) if s]


def _hard_split(sentence, max_chars):
    """Last resort for a single 'sentence' longer than the whole chunk budget
    — usually a table flattened into one line, or a page with no punctuation
    at all. Split on width rather than discard the text."""
    return [sentence[i:i + max_chars] for i in range(0, len(sentence), max_chars)]


def _overlap_tail(text, overlap_chars):
    """The trailing `overlap_chars` of a chunk, trimmed forward to the next
    word boundary so the overlap never starts mid-word."""
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ''
    tail = text[-overlap_chars:]
    space = tail.find(' ')
    return tail[space + 1:] if space != -1 else tail


def _chunk_page_text(text, max_chars, overlap_chars):
    """Group one page's sentences into <= max_chars chunks with overlap."""
    sentences = _split_sentences(text)
    chunks = []
    current = ''

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ''
            chunks.extend(_hard_split(sentence, max_chars))
            continue

        candidate = f'{current} {sentence}'.strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current)
        overlap = _overlap_tail(current, overlap_chars)
        current = f'{overlap} {sentence}'.strip() if overlap else sentence

    if current:
        chunks.append(current)
    return chunks


def chunk_pages(pages, *, max_chars=None, overlap_chars=None, min_chars=None):
    """Turn page dicts into chunk dicts ready for embedding.

    Args:
        pages: iterable of `{'page_number': int, 'text': str, ...}` — exactly
            what `PDFPageReader.read_pages()['pages']` returns.
        max_chars / overlap_chars / min_chars: override the configured
            defaults; used by tests and by any caller that needs a different
            granularity.

    Returns:
        A list of `{'chunk_index', 'page_number', 'text', 'char_count'}`.
        `chunk_index` runs 0..N-1 across the **whole document**, not per page,
        because it is half of the deterministic vector ID — see
        `pinecone_client.build_vector_id`.

    A page whose cleaned text is shorter than `min_chars` is skipped: a page
    holding only a header or a page number embeds to noise that competes with
    real evidence at search time.
    """
    max_chars = max_chars if max_chars is not None else settings.VECTOR_CHUNK_MAX_CHARS
    overlap_chars = (
        overlap_chars if overlap_chars is not None else settings.VECTOR_CHUNK_OVERLAP_CHARS
    )
    min_chars = min_chars if min_chars is not None else settings.VECTOR_CHUNK_MIN_CHARS

    if overlap_chars >= max_chars:
        # Would make every chunk start with the whole of its predecessor and
        # never terminate. Caught here rather than looping forever.
        raise ValueError('VECTOR_CHUNK_OVERLAP_CHARS must be smaller than VECTOR_CHUNK_MAX_CHARS.')

    chunks = []
    for page in pages or []:
        text = clean_text(page.get('text'))
        if len(text) < min_chars:
            continue
        page_number = page.get('page_number')
        for piece in _chunk_page_text(text, max_chars, overlap_chars):
            piece = piece.strip()
            if len(piece) < min_chars:
                continue
            chunks.append({
                'chunk_index': len(chunks),
                'page_number': page_number,
                'text': piece,
                'char_count': len(piece),
            })

    logger.info('vector_store.chunking.complete pages=%d chunks=%d', len(pages or []), len(chunks))
    return chunks
