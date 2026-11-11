"""Exact citation normalization. Omitted spans never become invented quotations."""
import re


def normalize(text):
    return ' '.join(text.split())


#: Typographic characters models often substitute when quoting (curly quotes, dashes, a bullet). One character for
#: one, so positions in the folded text are positions in the original.
_FOLD = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201b': "'", '\u201c': '"', '\u201d': '"',
                       '\u201e': '"', '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-', '\u2014': '-',
                       '\u2212': '-', '\u2022': '*', '\u00b4': "'", '`': "'"})


def _folded_match(quote, texts):
    """The verbatim source text a quote matches once curly quotes and dashes are folded, or None. The returned
    quotation is always the source's own characters, so exact checks downstream still hold."""
    folded = quote.translate(_FOLD)
    for text in texts:
        at = text.translate(_FOLD).find(folded)
        if at >= 0:
            return text[at:at + len(quote)]
    return None


def expand_citation(citation, windows):
    """Return exact citations; ellipsis fragments must occur in order in ONE supplied window."""
    if not isinstance(citation, dict) or not isinstance(citation.get('quote'), str):
        raise ValueError('Invalid citation record.')
    quote = normalize(citation['quote'])
    texts = [normalize(w['text']) for w in windows]
    if any((w.get('evidence_role') == 'report_timestamp' and quote == w['text'])
           or (w.get('report_timestamp') and quote == w['text'][w['report_timestamp']['start']:])
           for w in windows):
        return [{'source_id': citation['source_id'], 'quote': quote}]
    if len(quote) < 20:
        raise ValueError('Quotation is too short.')
    if any(quote in text for text in texts):
        return [{'source_id': citation['source_id'], 'quote': quote}]
    verbatim = _folded_match(quote, texts)
    if verbatim is not None:
        return [{'source_id': citation['source_id'], 'quote': verbatim}]
    parts = [normalize(p) for p in re.split(r'\.{3}|…', quote)]
    if not 2 <= len(parts) <= 8 or any(len(p) < 20 for p in parts):
        raise ValueError('Quote does not match a supplied source passage.')
    for text in texts:
        end = 0
        for part in parts:
            start = text.find(part, end)
            if start < 0:
                break
            end = start + len(part)
        else:
            return [{'source_id': citation['source_id'], 'quote': part} for part in parts]
    raise ValueError('Quote fragments do not match one supplied passage in order.')
