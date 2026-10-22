"""Deterministic comparisons for review screens (no AI): a source version against the one before it, and
requirement drafts against requirements already approved."""
import difflib

from ..models import Requirement, SourceVersion

MAX_DIFF_LINES = 200
DUPLICATE_SIMILARITY = 0.6


def _words(text):
    from .linking import tokens
    return tokens(text)


def similarity(a, b):
    wa, wb = _words(a), _words(b)
    return round(len(wa & wb) / len(wa | wb), 2) if wa and wb else 0.0


def previous_version(version):
    if version.supersedes_id:
        return version.supersedes
    return (SourceVersion.objects.filter(document=version.document).exclude(pk=version.pk)
            .exclude(status=SourceVersion.Status.WITHDRAWN).filter(created_at__lt=version.created_at)
            .order_by('-created_at').first())


def _lines(version):
    return [line.strip() for s in version.sections.order_by('ordinal') for line in s.text.splitlines() if line.strip()]


def compare_versions(version):
    """What changed from the previous version of the same source: file, page count, and the text lines
    added / removed (from the stored sections, when both versions have them)."""
    base = previous_version(version)
    if base is None:
        return {'base': None, 'note': 'No earlier version of this source to compare with.'}
    out = {
        'base': {'id': str(base.pk), 'version_label': base.version_label, 'status': base.status,
                 'issued_on': base.issued_on},
        'file_changed': bool(version.checksum_sha256 and base.checksum_sha256
                             and version.checksum_sha256 != base.checksum_sha256),
        'same_file': bool(version.checksum_sha256 and version.checksum_sha256 == base.checksum_sha256),
        'pages': {'before': base.pages, 'after': version.pages},
        'issued_on': {'before': base.issued_on, 'after': version.issued_on},
        'added': [], 'removed': [], 'note': '',
    }
    old, new = _lines(base), _lines(version)
    if not old or not new:
        out['note'] = ('Text comparison needs both versions read into sections (Draft requirements builds them).')
        return out
    for line in difflib.ndiff(old, new):
        if line.startswith('+ ') and len(out['added']) < MAX_DIFF_LINES:
            out['added'].append(line[2:])
        elif line.startswith('- ') and len(out['removed']) < MAX_DIFF_LINES:
            out['removed'].append(line[2:])
    out['requirements_on_base'] = base.requirements.count()
    return out


def similar_requirements(statement, *, exclude_id=None, limit=3):
    """Approved requirements whose statement is close to this one: [{code, statement, similarity}]."""
    rows = []
    for r in Requirement.objects.exclude(pk=exclude_id).only('code', 'statement'):
        sim = similarity(statement, r.statement)
        if sim >= DUPLICATE_SIMILARITY:
            rows.append({'code': r.code, 'statement': r.statement[:300], 'similarity': sim})
    return sorted(rows, key=lambda r: -r['similarity'])[:limit]
