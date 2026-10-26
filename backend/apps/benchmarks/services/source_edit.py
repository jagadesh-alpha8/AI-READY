"""Edit or delete a source in the Source Library (Benchmark Studio, InGage staff).

    update_source(doc, user, data)     # document details + its latest version's details
    delete_blockers(doc)               # why it cannot be deleted ([] = it can)
    delete_source(doc, user, reason)

Editing follows the Source Library's rules (models.py):
- the source code is the document's identity and never changes; the authority / framework stay as imported;
- a DRAFT version's details can all be edited; an approved (active / superseded / withdrawn) version is frozen --
  only its notes and the collector's status reading can change. A new edition is a new version.

Deleting removes a source that was added by mistake. It is refused once anything depends on it: an approved
version, an accepted requirement (which indicators may cite), a benchmark candidate or a detected change. Pending
AI requirement drafts, extracted text and watcher feeds of the source go with it. Every edit and deletion is in the
append-only audit log with the values before; a stored file is removed only when no other version uses it.
"""
import os

from django.db import transaction
from django.db.models import F as models_F

from ..models import (BenchmarkCandidate, Requirement, RequirementCandidate, SourceAuditEvent, SourceChangeEvent,
                      SourceDocument, SourceVersion)
from . import file_intake
from .source_create import SourceCreateError, _bool, _date, _text, _url

DOC_FIELDS = ('title', 'official_url', 'category', 'source_role', 'document_type', 'applies_to', 'programme_scope',
              'owner_team', 'review_cadence_months', 'licensed_content')
#: A draft version: every detail below. An approved one: only the non-frozen ones.
VERSION_FIELDS = ('version_label', 'issued_on', 'effective_from', 'direct_url', 'drive_url', 'pages', 'reported_status',
                  'notes')
VERSION_OPEN_WHEN_LOCKED = ('reported_status', 'notes')


def _latest(doc):
    return doc.versions.order_by('-issued_on', '-created_at').first()


def _clean(doc, data):
    """Only the fields sent are changed. Returns ({doc field: value}, {version field: value}) or raises."""
    errors, d, v = {}, {}, {}
    limits = {'title': 500, 'category': 60, 'source_role': 40, 'document_type': 40, 'applies_to': 300,
              'programme_scope': 300, 'owner_team': 100}
    for f, n in limits.items():
        if f in data:
            d[f] = _text(data, f, n)
    if 'title' in d and len(d['title']) < 5:
        errors['title'] = 'Enter the official title (at least 5 characters).'
    if d.get('source_role') and d['source_role'] not in SourceDocument.Role.values:
        errors['source_role'] = 'Choose a source role from the list.'
    if 'official_url' in data:
        d['official_url'] = _url(data.get('official_url'), 'official_url', errors)
    if 'licensed_content' in data:
        d['licensed_content'] = _bool(data.get('licensed_content'))
    if 'review_cadence_months' in data:
        try:
            d['review_cadence_months'] = int(data.get('review_cadence_months'))
            if not 1 <= d['review_cadence_months'] <= 120:
                raise ValueError
        except (TypeError, ValueError):
            errors['review_cadence_months'] = 'Review cadence must be 1-120 months.'

    if 'version_label' in data:
        v['version_label'] = _text(data, 'version_label', 120) or SourceVersion.UNVERSIONED
    for f in ('issued_on', 'effective_from'):
        if f in data:
            v[f] = _date(data.get(f), f, errors)
    for f in ('direct_url', 'drive_url'):
        if f in data:
            v[f] = _url(data.get(f), f, errors)
    if 'reported_status' in data:
        v['reported_status'] = _text(data, 'reported_status', 40)
    if 'notes' in data:
        v['notes'] = _text(data, 'notes', 2000)
    if 'pages' in data:
        raw = str(data.get('pages') or '').strip()
        if raw and not (raw.isdigit() and int(raw) > 0):
            errors['pages'] = 'Pages must be a whole number.'
        else:
            v['pages'] = int(raw) if raw else None
    if errors:
        raise SourceCreateError(errors)
    return d, v


def _audit(user, action, obj, before, after, reason=''):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type=type(obj).__name__,
                                    object_id=str(obj.pk), before=before, after=after, reason=reason)


def update_source(doc, user, data):
    d, v = _clean(doc, data)
    version = _latest(doc)
    d = {k: val for k, val in d.items() if getattr(doc, k) != val}
    v = {k: val for k, val in v.items() if version is not None and getattr(version, k) != val}
    if version is not None and version.is_locked:
        frozen = [k for k in v if k not in VERSION_OPEN_WHEN_LOCKED]
        if frozen:
            raise SourceCreateError({k: f'Version {version.version_label} is {version.status}: it cannot change. '
                                        'Add a new version for a new edition.' for k in frozen})
    if 'version_label' in v and doc.versions.exclude(pk=version.pk).filter(version_label=v['version_label']).exists():
        raise SourceCreateError({'version_label': f'{doc.source_code} already has a version "{v["version_label"]}".'})
    if not d and not v:
        return doc
    with transaction.atomic():
        if d:
            before = {k: str(getattr(doc, k)) for k in d}
            for k, val in d.items():
                setattr(doc, k, val)
            doc.save()
            _audit(user, 'source.updated', doc, before, {k: str(val) for k, val in d.items()})
        if v:
            before = {k: str(getattr(version, k)) for k in v}
            for k, val in v.items():
                setattr(version, k, val)
            version.save()  # SourceVersion.save refuses frozen changes too
            _audit(user, 'version.updated', version, before, {k: str(val) for k, val in v.items()})
    return doc


def blocker_counts():
    """{document id: (approved versions, requirements, candidates, change events)} for every source, in 4 queries."""
    from django.db.models import Count
    out = {}
    queries = (
        SourceVersion.objects.exclude(status=SourceVersion.Status.DRAFT).values('document_id'),
        Requirement.objects.values(document_id=models_F('version__document_id')),
        BenchmarkCandidate.objects.filter(source_document__isnull=False).values(document_id=models_F('source_document_id')),
        SourceChangeEvent.objects.values('document_id'),
    )
    for i, qs in enumerate(queries):
        for row in qs.annotate(n=Count('pk')).values('document_id', 'n'):
            out.setdefault(str(row['document_id']), [0, 0, 0, 0])[i] = row['n']
    return out


def describe_blockers(counts):
    approved, reqs, cands, changes = counts or (0, 0, 0, 0)
    out = []
    if approved:
        out.append(f'{approved} version(s) are approved, superseded or withdrawn (approved versions are kept for ever).')
    if reqs:
        out.append(f'{reqs} accepted requirement(s) come from it.')
    if cands:
        out.append('A benchmark candidate refers to it.')
    if changes:
        out.append('The watcher has recorded changes for it.')
    return out


def delete_blockers(doc):
    """Plain reasons the source cannot be deleted; [] when it can."""
    return describe_blockers(blocker_counts().get(str(doc.pk)))


def delete_source(doc, user, reason):
    if not (reason or '').strip():
        raise SourceCreateError({'reason': 'Give a reason for deleting this source.'})
    blockers = delete_blockers(doc)
    if blockers:
        raise SourceCreateError({'detail': f'{doc.source_code} cannot be deleted: ' + ' '.join(blockers)})
    with transaction.atomic():
        versions = list(doc.versions.all())
        files = {v.file_uri for v in versions if v.file_uri}
        drafts = RequirementCandidate.objects.filter(version__document=doc).count()
        before = {'source_code': doc.source_code, 'title': doc.title, 'category': doc.category,
                  'official_url': doc.official_url,
                  'versions': [{'version_label': v.version_label, 'status': v.status, 'file_uri': v.file_uri,
                                'checksum_sha256': v.checksum_sha256} for v in versions],
                  'pending_ai_drafts_removed': drafts}
        doc.versions.update(supersedes=None)  # drafts only, so nothing frozen changes; lets them go in any order
        for v in doc.versions.all():
            v.delete()  # drafts only (checked above); its sections and AI drafts go with it
        doc_id, code = str(doc.pk), doc.source_code
        doc.delete()  # feeds and their snapshots go with it
        SourceAuditEvent.objects.create(actor=user.email, action='source.deleted', object_type='SourceDocument',
                                        object_id=doc_id, before=before, after=None, reason=reason.strip())
        orphans = [f for f in files if not SourceVersion.objects.filter(file_uri=f).exists()]
        transaction.on_commit(lambda: _remove_files(orphans))
    return code


def _remove_files(rel_paths):
    from django.conf import settings
    for rel in rel_paths:
        path = os.path.normpath(os.path.join(settings.MEDIA_ROOT, rel))
        root = os.path.normpath(os.path.join(settings.MEDIA_ROOT, file_intake.STORAGE_DIR))
        if path.startswith(root + os.sep) and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
