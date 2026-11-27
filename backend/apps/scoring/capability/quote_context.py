"""Whole sentences for cut-off quotations, for printing only (quote-context-1).

The judge quotes the college's documents exactly, and the quote check holds it to that. But the extractor breaks a
page's text at its line ends, so a quotation is often one printed line of a longer sentence: "The firewall is
upgraded to" on one line, "Sonicall NSA 4700 from Sophos NXG550." on the next. In test 13, 34 of 166 distinct
quotations could not be read on their own (presentation.unreadable), and about half of those were prose cut at a
line end. This module finds the whole sentence a prose shard belongs to, on the page the run itself read (the run's
frozen sources), so the reports and screens print the sentence instead of hiding the quotation.

Nothing here changes a score, a record or a stored citation: the record keeps the judge's exact quotation, and the
sentence is worked out again whenever a report is built. Table rows, headings and the extractor's own notes are left
alone; a wider stretch of a table is no easier to read. A sentence is used only when it contains the quotation, stays
within the page, and is itself readable.
"""
import re
from functools import lru_cache

VERSION = 'quote-context-1'
LIMIT = 320           # characters a sentence may reach on either side of the quotation
SENTENCE_MAX = 420    # a longer "sentence" is a run-on page fragment, not something to print

#: Where a sentence ends: end punctuation then a space or the page's end. A table cell divider, the extractor's
#: bracketed notes and bullets end it too.
_HARD = set('|[]•')
_ABBREVIATION = re.compile(r'(?:\b(?:Dr|Mr|Mrs|Ms|Prof|No|Nos|St|Sr|Jr|viz|etc|vs|Vol|Fig|approx)|\be\.g|\bi\.e|'
                           r'\b[A-Z])\.$')


def _normalize(text):
    return ' '.join(str(text or '').split())


#: A NAAC metric number ("6.3.1 The institution has ...") opens a new item, as a sentence start does.
_METRIC_CODE = re.compile(r'(?:^|(?<= ))\d+(?:\.\d+)+ ')


def _is_end(text, at):
    """Whether a sentence ends just before position `at`."""
    if at <= 0:
        return True
    if text[at - 1] in _HARD:
        return True
    if _METRIC_CODE.match(text, at):
        return True
    if text[at - 1] in '.!?' and (at >= len(text) or text[at] == ' '):
        return not _ABBREVIATION.search(text[max(0, at - 8):at])
    return False


def _locate(text, quote):
    at = text.find(quote)
    if at >= 0:
        return at
    from .citations import _FOLD
    return text.translate(_FOLD).find(quote.translate(_FOLD))


def prose_shard(quote):
    """Whether a quotation is a sentence cut off at a line end, the one kind this module can make whole."""
    from .presentation import unreadable
    q = _normalize(quote)
    reason = unreadable(q)
    if not reason or '|' in q or q.startswith('['):
        return False
    return reason in {'too short', 'starts mid-sentence', 'cut off mid-sentence'}


def sentence(page_text, quote):
    """The whole sentence (or sentences) of the page a prose shard belongs to, or None. The result is the page's own
    text, whitespace collapsed, and always contains the quotation."""
    from .presentation import unreadable
    if not prose_shard(quote):
        return None
    text, q = _normalize(page_text), _normalize(quote)
    at = _locate(text, q)
    if at < 0:
        return None
    end = at + len(q)
    start = at
    # A quotation that opens with a capital already starts its sentence; going back would only pick up the heading
    # or the line before it ("IT Infrastructure The firewall is ...").
    while not re.match(r'[A-Z0-9"\u201c(]', q) and start > 0 and at - start < LIMIT and not _is_end(text, start):
        start -= 1
    if at - start >= LIMIT:
        return None   # no sentence start within reach: the quotation sits inside a long run of text
    stop = end
    if not (text[end - 1] in '.!?' and _is_end(text, end)):
        while stop < len(text) and stop - end < LIMIT and not _is_end(text, stop):
            stop += 1
        if stop - end >= LIMIT:
            return None
    whole = _METRIC_CODE.sub('', text[start:stop].strip(' |[]•'), count=1) if _METRIC_CODE.match(text, start) else \
        text[start:stop].strip(' |[]•')
    if whole == q or _locate(whole, q) < 0 or not re.search(r'[.!?]["\u201d)]?$', whole):
        return None   # nothing added, or the stretch never reaches a sentence's end (a title, a cut page)
    from .presentation import _METRIC_HEADING, quote_quality
    if len(whole) > SENTENCE_MAX or unreadable(whole) or not quote_quality(whole, 1) or _METRIC_HEADING.search(whole):
        return None   # still not something a reader can take in: a title, a heading run or a metric's wording
    return whole


def key(source_id, quote):
    return f'{source_id}\n{_normalize(quote)}'


def sentences(records, sources):
    """{key(source_id, quote): sentence} for every cited prose shard in these records that a page of `sources` (the
    run's frozen sources: dicts with id and text) makes whole."""
    texts = {str(s.get('id')): s.get('text') or '' for s in sources or () if isinstance(s, dict)}
    out = {}
    for record in records or ():
        cites = list(record.get('citations') or [])
        for part in record.get('parts') or []:
            cites.extend(part.get('citations') or [])
        for cite in cites:
            if not isinstance(cite, dict) or not isinstance(cite.get('quote'), str):
                continue
            sid = str(cite.get('source_id'))
            k = key(sid, cite['quote'])
            if k in out or sid not in texts:
                continue
            found = sentence(texts[sid], cite['quote'])
            if found:
                out[k] = found
    return out


def whole(cites, found):
    """The citations with each prose shard's quotation replaced by its whole sentence, where one was found."""
    if not found:
        return cites
    out = []
    for cite in cites:
        if isinstance(cite, dict) and isinstance(cite.get('quote'), str):
            replacement = found.get(key(cite.get('source_id'), cite['quote']))
            if replacement:
                cite = {**cite, 'quote': replacement}
        out.append(cite)
    return out


def record_whole(record, found):
    """A copy of a record whose citations (its own and its parts') print whole sentences where found; the record
    itself is never changed."""
    if not found or not isinstance(record, dict):
        return record
    out = {**record}
    if record.get('citations'):
        out['citations'] = whole(record['citations'], found)
    if record.get('parts'):
        out['parts'] = [{**p, 'citations': whole(p.get('citations') or [], found)} if isinstance(p, dict) else p
                        for p in record['parts']]
    return out


@lru_cache(maxsize=64)
def _for_run_event(run_id, event_id):
    from apps.scoring.models import CapabilityRun, CapabilityRunEvent
    run = CapabilityRun.objects.filter(pk=run_id).only('inputs').first()
    event = CapabilityRunEvent.objects.filter(pk=event_id, run_id=run_id).only('payload').first() if event_id else None
    if run is None or event is None:
        return {}
    records = (event.payload or {}).get('records') or []
    return sentences(records, (run.inputs or {}).get('sources') or [])


def for_run(run, records, event_id=None):
    """The sentences for a run's records. A run's inputs and a completed event's records never change, so the result
    is kept per (run, event); without an event id it is worked out from the records given."""
    if run is None:
        return {}
    if event_id is not None:
        try:
            return _for_run_event(str(run.pk if hasattr(run, 'pk') else run), int(event_id))
        except (TypeError, ValueError):
            pass
    inputs = getattr(run, 'inputs', None) or {}
    return sentences(records, inputs.get('sources') or [])
