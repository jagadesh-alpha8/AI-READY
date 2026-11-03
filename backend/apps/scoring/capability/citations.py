"""Exact citation normalization. Omitted spans never become invented quotations."""
import re


def normalize(text):
    return ' '.join(text.split())


def expand_citation(citation, windows):
    """Return exact citations; ellipsis fragments must occur in order in ONE supplied window."""
    if not isinstance(citation, dict) or not isinstance(citation.get('quote'), str):
        raise ValueError('Invalid citation record.')
    quote = normalize(citation['quote'])
    texts = [normalize(w['text']) for w in windows]
    if len(quote) < 20:
        raise ValueError('Quotation is too short.')
    if any(quote in text for text in texts):
        return [{'source_id': citation['source_id'], 'quote': quote}]
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
