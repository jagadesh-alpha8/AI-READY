"""Display mask for demos: shows an institution under another name wherever text leaves the server.

Switched on with DEMO_NAME_MASK=<list name>, which names a term list in apps/demo_mask/terms/<list name>.json. Off (the
default, empty): nothing is changed anywhere. Stored data is never changed: the mask applies only to what is sent.

Where it applies (decided 25 Nov 2026):
- every API response with a text body (JSON, HTML, plain text, CSV), its download file name included
  (middleware.NameMaskMiddleware);
- the capability reports in every format, PDFs included: the report's data is masked before it is rendered
  (report_views), so the PDF never holds the names;
- binary downloads the mask cannot rewrite (uploaded source documents, the older stored report files) are refused
  while the mask is on, so a letterhead or logo can't leak through them.
Not masked, for now (27 Nov 2026): the facts check and the follow-up questions (middleware.UNMASKED), whose answers go
back to the server and on to judging.

A term list is a JSON array of {"find": text, "replace": text}. A find text is matched as a whole word (letters on either
side stop a match; digits don't), ignoring case,
with spaces, commas, "&"/"and", apostrophes and the space before "(" matched loosely, so one entry covers the forms
documents use ("Vels Institute of Science, Technology & Advanced Studies (VISTAS)", "VELS INSTITUTE OF SCIENCE
TECHNOLOGY AND ADVANCED STUDIES(VISTAS)"). Longer entries are applied first. Programme names and facts are not masked.
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

TERMS_DIR = Path(__file__).resolve().parent / 'terms'
SPACE = r'(?:\s|\\[nrt])+'   # whitespace, or the "\n" / "\t" a JSON body writes inside a string
#: A term must not sit inside a longer word. Next to a term that ends in a letter, digits don't count ("VISTAS2021"
#: is masked; 25 Nov audit); next to one that ends in a digit, they do (a postcode inside a phone number is not one).
_LETTER = r'[A-Za-zÀ-ɏ]'
_WORD = r'[0-9A-Za-zÀ-ɏ]'


def active():
    return bool(_name())


def _name():
    return (getattr(settings, 'DEMO_NAME_MASK', '') or '').strip()


def _piece(char):
    if char.isspace():
        return SPACE   # whitespace, or a JSON body's escaped line break inside a string ("\n")
    if char in "'’`":
        return r"(?:'|’|`|\\u2019)?"   # the raw "’" is how an ASCII-only JSON body spells it
    if char == '&':
        return r'(?:&amp;|&|\\u0026|and)'
    if char == ',':
        return r',?'
    if char == '(':
        return r'\s*\('
    if char == '.':
        return r'\.?\s*'
    return re.escape(char)


def pattern(find):
    """The compiled pattern for one find text (see the module notes)."""
    words = find.strip()
    body = ''.join(_piece(c) for c in words)
    gap, gaps = SPACE, SPACE[:-1] + '*'
    body = body.replace(gap + r'(?:&amp;|&|\\u0026|and)' + gap, gaps + r'(?:&amp;|&|\\u0026|and)' + gaps)
    body = body.replace(gap + 'and' + gap, gaps + r'(?:&amp;|&|\\u0026|and)' + gaps)   # "and" also matches "&"
    body = body.replace(r',?' + gap, r',?' + gaps)
    body = body.replace(gap + r'\s*\(', r'\s*\(')
    body = body.replace(r'\.?\s*' + gap, r'\.?' + gaps)   # "P.V. Road" also matches "P.V.Road"
    # Whole words: not inside a longer word, but a term right after a JSON "\n" still counts. A find text that starts or
    # ends with punctuation ("(VISTA") needs no boundary on that side.
    edge = lambda char: _WORD if char.isdigit() else _LETTER
    before = rf'(?:(?<!{edge(words[0])})|(?<=\\[nrt]))' if re.match(r'\w', words) else ''
    after = rf'(?!{edge(words[-1])})' if re.search(r'\w$', words) else ''
    return re.compile(before + body + after, re.IGNORECASE)


@lru_cache(maxsize=4)
def _compiled(name):
    path = TERMS_DIR / f'{name}.json'
    if not re.fullmatch(r'[a-z0-9_-]+', name) or not path.is_file():
        raise ValueError(f'DEMO_NAME_MASK={name!r}: no term list apps/demo_mask/terms/{name}.json.')
    entries = json.loads(path.read_text(encoding='utf-8'))
    out = []
    for entry in sorted(entries, key=lambda e: len(e['find']), reverse=True):
        if not entry.get('find') or '"' in entry['replace'] or '\\' in entry['replace']:
            raise ValueError(f'Bad term list entry: {entry!r}')
        out.append((pattern(entry['find']), entry['replace']))
    return tuple(out), hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def terms():
    return _compiled(_name())[0] if active() else ()


def fingerprint():
    """'' when off; else the list name and a hash of its file, for cache keys and version markers."""
    return f'{_name()}:{_compiled(_name())[1]}' if active() else ''


def text(value):
    if not active() or not isinstance(value, str) or not value:
        return value
    for compiled, replacement in terms():
        value = compiled.sub(replacement, value)
    return value


def data(value):
    """`value` with every string inside it masked (dicts, lists and tuples walked; keys left as they are)."""
    if not active():
        return value
    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        return {k: data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(data(v) for v in value)
    return value
