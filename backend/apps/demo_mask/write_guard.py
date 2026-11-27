"""Stops the demo display mask from being saved over real data (27 Nov 2026).

The mask (mask.py) changes only what the server sends: the database keeps the real names. A screen that shows a masked
value and saves it back would therefore write the mask into the database. The institution profile did exactly that: it
sends the displayed name ("ABC University") with every save. While the mask is on, this middleware refuses, with a
message that says why:

1. Edits to a masked institution's own records: the institution, its departments, systems and leaders, its benchmark
   profile, and its sprints' details. "Masked" means the mask changes at least one of the institution's stored text
   fields, so other institutions on the same server can still be edited.
2. Any other write whose JSON body contains a distinctive mask replacement: one with "ABC" in capitals and another word, a bracketed
   placeholder ("[campus address]") or a made-up ".example" address. Such text can only have come from a masked screen,
   and judging would read it against documents that name the real institution. The generic replacements ("the
   founder", "Campus A", a rounded postcode) and a bare "ABC" are left out, because ordinary answers use those words.
   Writes to the screens left unmasked (middleware.UNMASKED) are not checked: they never show a stand-in.

Does nothing while DEMO_NAME_MASK is empty. Reads only JSON bodies; uploads are not checked.
"""
import json
import re

from django.http import JsonResponse

from . import mask

WRITES = ('POST', 'PUT', 'PATCH')
_ID = r'[0-9a-f-]{36}'
#: A masked institution's own records, by the institution's id (group 1) or its sprint's id (group 2).
INSTITUTION_RECORD = re.compile(rf'^/api/v\d+/(?:institutions/({_ID})(?:/(?:departments|systems|leaders)(?:/{_ID})?)?'
                                rf'|assessments/institutions/({_ID})/profile)/?$')
SPRINT_RECORD = re.compile(rf'^/api/v\d+/sprints/({_ID})/?$')
#: Sign-in and password requests are never checked: a password may contain anything.
AUTH = re.compile(r'^/api/v\d+/auth/')
INSTITUTION_TEXT = ('name', 'short_name', 'university_affiliation', 'location', 'city', 'state', 'accreditation_details')


def _distinctive(replacement):
    """A bare "ABC" (the stand-in for "Vel's" and "Velan") is left out (review of #116, finding 4): it is also the
    Academic Bank of Credits, which Indian colleges' records and answers name, so "ABC" alone proves nothing."""
    abc = re.search(r'\bABC\b', replacement) and len(replacement.split()) > 1
    return bool(abc or re.fullmatch(r'\[[^\]]+\]', replacement) or re.search(r'\.example\b', replacement))


def _replacements():
    return sorted({r for _, r in mask.terms() if r and _distinctive(r)}, key=len, reverse=True)


def _strings(value, path=''):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f'{path}.{key}' if path else str(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, f'{path}[{i}]')


def masked_text_in(body):
    """(field, replacement) for the first string in `body` holding a distinctive replacement, else None."""
    found = _replacements()
    if not found:
        return None
    for field, text in _strings(body):
        for replacement in found:
            if re.search(r'(?<!\w)' + re.escape(replacement) + r'(?!\w)', text):
                return field, replacement
    return None


def institution_is_masked(institution):
    return any(mask.text(getattr(institution, f, '') or '') != (getattr(institution, f, '') or '') for f in INSTITUTION_TEXT)


def _institution_for(path, method):
    from apps.institutions.models import Institution
    match = INSTITUTION_RECORD.match(path)
    if match:
        return Institution.objects.filter(pk=match.group(1) or match.group(2)).first()
    match = SPRINT_RECORD.match(path)
    if match and method in ('PUT', 'PATCH'):
        from apps.sprints.models import Sprint
        sprint = Sprint.objects.select_related('institution').filter(pk=match.group(1)).first()
        return sprint.institution if sprint else None
    return None


def _refuse(detail):
    return JsonResponse({'code': 'demo_mask_write_refused', 'detail': detail}, status=400)


class MaskedWriteGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (mask.active() and request.method in WRITES and request.path.startswith('/api/')
                and not AUTH.match(request.path)):
            refusal = self._check(request)
            if refusal is not None:
                return refusal
        return self.get_response(request)

    @staticmethod
    def _check(request):
        institution = _institution_for(request.path, request.method)
        # A status change (archiving a sprint) carries no names, so it stays allowed.
        if institution is not None and institution_is_masked(institution):
            body = _json(request)
            if not (SPRINT_RECORD.match(request.path) and isinstance(body, dict) and set(body) <= {'status'}):
                return _refuse('This institution\'s details can\'t be edited while the demo name mask is on: the screens '
                               'show a stand-in name, and saving would write it over the real one. Ask InGage to switch '
                               'the mask off to make this change.')
        # The screens left unmasked (middleware.UNMASKED: facts check, follow-up questions) never show a stand-in, so
        # what is written there cannot have come from the mask (review of #116, finding 4).
        from .middleware import UNMASKED
        if UNMASKED.match(request.path):
            return None
        body = _json(request)
        hit = masked_text_in(body) if body is not None else None
        if hit:
            field, replacement = hit
            return _refuse(f'"{replacement}" is the stand-in name the demo shows, not a name in your records, so it '
                           f'can\'t be saved ({field.replace("_", " ")}). Use the real name, or leave that text as it was.')
        return None


def _json(request):
    if (request.content_type or '').split(';')[0].strip().lower() != 'application/json':
        return None
    try:
        return json.loads(request.body or b'null')
    except (ValueError, UnicodeDecodeError):
        return None
