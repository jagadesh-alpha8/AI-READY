"""Add one source from the Studio (instead of a Source Register import row).

    doc, version = create_source(user, data, upload=None)

Same model and rules as the register import (services/register_import.py):
the authority is an existing one or a new one (name + kind; code derived the
same way), the framework is "<authority>-C<category number>", and the source
starts with ONE draft version -- approval stays a separate step.

Initial collection status follows what was given:
  a file was uploaded       -> downloaded (stored content-addressed, SHA-256
                               computed; intake "Stored")
  licensed standard         -> licensed - link only (a file is refused)
  an official / direct URL  -> found - link only
  nothing                   -> to find

Things the import would flag (URL not on an official domain, empty
"applies to", no source role) are saved as the version's review_flags, so
the source shows "to review" exactly like an imported one.
"""
import os
import re
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Authority, Framework, SourceAuditEvent, SourceDocument, SourceVersion
from . import file_intake
from .register_import import authority_code, domain, is_official

MAX_FILE_BYTES = 25 * 1024 * 1024
SOURCE_CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{1,39}$')


def supported_extensions():
    from apps.extraction.services.pdf_reader import SUPPORTED_EXTENSIONS
    return sorted(SUPPORTED_EXTENSIONS)


class SourceCreateError(Exception):
    """Field errors: {field: message}."""

    def __init__(self, errors):
        super().__init__('; '.join(f'{k}: {v}' for k, v in errors.items()))
        self.errors = errors


def _text(data, key, limit):
    return (str(data.get(key) or '')).strip()[:limit]


def _date(value, field, errors):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors[field] = 'Use the date format YYYY-MM-DD.'
        return None


def _url(value, field, errors):
    value = (value or '').strip()
    if value and not re.match(r'^https?://[^\s/$.?#].\S*$', value, re.I):
        errors[field] = 'Enter a full web address starting with http:// or https://.'
    return value


def _bool(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def validate(data, upload=None):
    """Return cleaned values or raise SourceCreateError with every problem at once."""
    errors, warnings = {}, []
    v = {
        'source_code': _text(data, 'source_code', 40),
        'title': _text(data, 'title', 500),
        'category': _text(data, 'category', 60),
        'document_type': _text(data, 'document_type', 40),
        'applies_to': _text(data, 'applies_to', 300),
        'programme_scope': _text(data, 'programme_scope', 300),
        'source_role': _text(data, 'source_role', 40),
        'licensed_content': _bool(data.get('licensed_content')),
        'version_label': _text(data, 'version_label', 120) or SourceVersion.UNVERSIONED,
        'notes': _text(data, 'notes', 2000),
    }
    if not SOURCE_CODE.match(v['source_code']):
        errors['source_code'] = '2-40 letters, digits, dots, dashes or underscores (e.g. UGC-012).'
    elif SourceDocument.objects.filter(source_code__iexact=v['source_code']).exists():
        errors['source_code'] = f'{v["source_code"]} already exists. Open it in the list, or use another code.'
    if len(v['title']) < 5:
        errors['title'] = 'Enter the official title (at least 5 characters).'
    if v['source_role'] and v['source_role'] not in SourceDocument.Role.values:
        errors['source_role'] = 'Choose a source role from the list.'
    try:
        v['review_cadence_months'] = int(data.get('review_cadence_months') or 12)
        if not 1 <= v['review_cadence_months'] <= 120:
            raise ValueError
    except (TypeError, ValueError):
        errors['review_cadence_months'] = 'Review cadence must be 1-120 months.'

    # Authority: an existing code, or a new name + kind.
    code = _text(data, 'authority', 40).upper()
    if code:
        v['authority'] = Authority.objects.filter(code=code).first()
        if v['authority'] is None:
            errors['authority'] = 'Unknown authority; pick one from the list or add a new one.'
    else:
        name = _text(data, 'authority_name', 150)
        kind = _text(data, 'authority_kind', 30)
        if len(name) < 2:
            errors['authority_name'] = 'Pick an authority or enter the new authority\'s name.'
        if kind not in Authority.Kind.values:
            errors['authority_kind'] = 'Choose what kind of authority it is.'
        v['authority'] = None
        v['authority_name'], v['authority_kind'] = name, kind
        existing = Authority.objects.filter(code=authority_code(name)).first() if name else None
        if existing:
            v['authority'] = existing  # same code as an existing authority: reuse it

    v['official_url'] = _url(data.get('official_url'), 'official_url', errors)
    v['direct_url'] = _url(data.get('direct_url'), 'direct_url', errors)
    v['issued_on'] = _date(data.get('issued_on'), 'issued_on', errors)
    v['effective_from'] = _date(data.get('effective_from'), 'effective_from', errors)
    if v['issued_on'] and v['issued_on'] > timezone.localdate():
        errors['issued_on'] = 'The issue date cannot be in the future.'

    if upload is not None:
        ext = os.path.splitext(upload.name or '')[1].lower()
        if v['licensed_content']:
            errors['file'] = 'A licensed standard is kept as a link only; do not upload its file.'
        elif ext not in supported_extensions():
            errors['file'] = f'Unsupported file type "{ext or "none"}". Use one of: {", ".join(supported_extensions())}.'
        elif upload.size > MAX_FILE_BYTES:
            errors['file'] = 'The file is larger than 25 MB.'
        elif upload.size == 0 or ext in file_intake.INCOMPLETE_EXTENSIONS:
            errors['file'] = 'The file is empty or an incomplete download.'
    if errors:
        raise SourceCreateError(errors)

    for label, url in (('Official page URL', v['official_url']), ('Direct document URL', v['direct_url'])):
        if url and not is_official(url):
            warnings.append(f'{label} is on {domain(url)}, not an official domain.')
    if not v['applies_to']:
        warnings.append('Applies To is empty.')
    if not v['source_role']:
        warnings.append('Source Role is empty or not a list value.')
    v['warnings'] = warnings
    return v


def _audit(user, obj, after):
    SourceAuditEvent.objects.create(actor=user.email, action='source.create', object_type=type(obj).__name__,
                                    object_id=str(obj.pk), after=after, reason='Added in Benchmark Studio')


def create_source(user, data, upload=None):
    v = validate(data, upload)
    content = upload.read() if upload is not None else None
    with transaction.atomic():
        authority = v['authority']
        if authority is None:
            authority = Authority.objects.create(code=authority_code(v['authority_name']), name=v['authority_name'],
                                                 kind=v['authority_kind'])
            _audit(user, authority, {'code': authority.code, 'kind': authority.kind})
        cat_no = (re.match(r'(\d+)', v['category']) or [None, '0'])[1]
        framework, made = Framework.objects.get_or_create(
            code=f'{authority.code}-C{cat_no}',
            defaults={'authority': authority, 'name': f'{authority.name}: {v["category"] or "uncategorised"}',
                      'purpose': v['category'] or '-'})
        if made:
            _audit(user, framework, {'code': framework.code})
        try:
            doc = SourceDocument.objects.create(
                framework=framework, source_code=v['source_code'], title=v['title'], official_url=v['official_url'],
                licensed_content=v['licensed_content'], review_cadence_months=v['review_cadence_months'],
                category=v['category'], source_role=v['source_role'], document_type=v['document_type'],
                applies_to=v['applies_to'], programme_scope=v['programme_scope'])
        except IntegrityError:
            raise SourceCreateError({'source_code': f'{v["source_code"]} already exists.'})
        _audit(user, doc, {'source_code': doc.source_code, 'title': doc.title})

        if content is not None:
            collection = SourceVersion.Collection.DOWNLOADED
        elif v['licensed_content']:
            collection = SourceVersion.Collection.LICENSED
        elif v['official_url'] or v['direct_url']:
            collection = SourceVersion.Collection.LINK_ONLY
        else:
            collection = SourceVersion.Collection.TO_FIND
        version = SourceVersion(
            document=doc, version_label=v['version_label'], issued_on=v['issued_on'],
            effective_from=v['effective_from'], direct_url=v['direct_url'], collection_status=collection,
            notes=v['notes'], review_flags=v['warnings'])
        if content is not None:
            rel, sha = file_intake.store(content, upload.name)
            pages = file_intake.pdf_page_count(content) if upload.name.lower().endswith('.pdf') else None
            version.file_uri, version.checksum_sha256 = rel, sha
            version.file_size_kb, version.pages = round(len(content) / 1024), pages
            version.collected_on = timezone.localdate()
            version.intake_status, version.intake_at = SourceVersion.Intake.COMPUTED, timezone.now()
            version.intake_note = (f'Uploaded "{upload.name}" in Benchmark Studio by {user.email} '
                                   f'({version.file_size_kb} KB{f", {pages} pages" if pages else ""}).')
        version.save()
        _audit(user, version, {'version_label': version.version_label, 'collection_status': collection,
                               'checksum_sha256': version.checksum_sha256, 'review_flags': version.review_flags})
    return doc, version
