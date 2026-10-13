"""Stage 1 step 3: copy each source file into app storage and verify it.

For every draft version that was downloaded, fetch its file (Drive file link,
via the same Drive API the Upload Data Pack import uses), compute SHA-256,
size and pages, and compare with what the collector recorded:

  verified  checksum matches the register      -> stored, file_uri set
  computed  register had no checksum            -> stored, checksum filled in
  mismatch  register checksum differs           -> NOT stored; needs a person
  skipped   licensed / folder link / no link    -> nothing fetched
  failed    Drive refused or network error      -> retry later

Files are stored content-addressed (media/source_library/ab/<sha256>.<ext>),
written once and never overwritten -- the same bytes always map to the same
path, so a stored file can't be swapped. Approved (locked) versions are
never touched.
"""
import hashlib
import os
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from ..models import SourceAuditEvent, SourceVersion

STORAGE_DIR = 'source_library'
#: Browser temp names of a download that never finished.
INCOMPLETE_EXTENSIONS = ('.crdownload', '.part', '.partial', '.download', '.tmp')
_DRIVE_FILE_ID = re.compile(r'(?:/file/d/|[?&]id=)([A-Za-z0-9_-]{10,})')


def drive_file_id(url):
    m = _DRIVE_FILE_ID.search(url or '')
    return m.group(1) if m else None


def fetch_from_drive(file_id):
    """(bytes, filename) for a Drive file shared 'anyone with the link'."""
    import requests

    from apps.documents.drive_import import DRIVE_API_BASE, _raise_for_drive_status, download_drive_file

    key = settings.GOOGLE_DRIVE_API_KEY
    if not key:
        raise RuntimeError('GOOGLE_DRIVE_API_KEY is not configured.')
    resp = requests.get(f'{DRIVE_API_BASE}/files/{file_id}',
                        params={'fields': 'id,name,mimeType,size', 'key': key}, timeout=30)
    _raise_for_drive_status(resp, context=f'reading Drive file {file_id}')
    content, name, _mime = download_drive_file(resp.json(), key)
    return content, name


def pdf_page_count(content):
    try:
        import pymupdf
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            return pdf.page_count
    except Exception:
        return None


def store(content, filename):
    """Write content-addressed, once. Returns (relative path, sha256)."""
    sha = hashlib.sha256(content).hexdigest()
    ext = os.path.splitext(filename)[1].lower()[:10] or '.bin'
    rel = f'{STORAGE_DIR}/{sha[:2]}/{sha}{ext}'
    path = os.path.join(settings.MEDIA_ROOT, rel)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.part'
        with open(tmp, 'wb') as fh:
            fh.write(content)
        os.replace(tmp, path)
    return rel, sha


def stored_path(version):
    return os.path.join(settings.MEDIA_ROOT, version.file_uri) if version.file_uri else None


@dataclass
class IntakeResult:
    version: SourceVersion
    status: str
    note: str = ''


@dataclass
class IntakeSummary:
    results: list = field(default_factory=list)

    def count(self, status):
        return sum(1 for r in self.results if r.status == status)


def candidates(codes=None, retry=False):
    qs = SourceVersion.objects.filter(status=SourceVersion.Status.DRAFT,
                                      collection_status=SourceVersion.Collection.DOWNLOADED,
                                      document__licensed_content=False).select_related('document')
    if codes:
        qs = qs.filter(document__source_code__in=codes)
    if not retry:
        qs = qs.filter(intake_status__in=[SourceVersion.Intake.NOT_RUN, SourceVersion.Intake.FAILED])
    return qs


def ingest(version, *, fetcher=None, actor='file_intake', dry_run=False):
    """Fetch, store and verify one version. Never touches a locked version."""
    fetcher = fetcher or fetch_from_drive  # looked up at call time (patchable)
    if version.is_locked:
        return IntakeResult(version, 'skipped', f'{version.status}: approved versions are never changed')
    if version.document.licensed_content:
        return _finish(version, SourceVersion.Intake.SKIPPED, 'Licensed standard: not stored.', actor, dry_run)
    file_id = drive_file_id(version.drive_url)
    if not file_id:
        why = 'Drive link is a folder - link the exact file.' if '/folders/' in version.drive_url else 'No Drive file link.'
        return _finish(version, SourceVersion.Intake.SKIPPED, why, actor, dry_run)
    try:
        content, name = fetcher(file_id)
    except Exception as exc:
        return _finish(version, SourceVersion.Intake.FAILED, f'Could not fetch from Drive: {exc}', actor, dry_run)

    if not content or name.lower().endswith(INCOMPLETE_EXTENSIONS):
        return _finish(version, SourceVersion.Intake.FAILED,
                       f'Drive file "{name}" is an incomplete or empty download - download it again.', actor, dry_run)
    sha = hashlib.sha256(content).hexdigest()
    recorded = (version.checksum_sha256 or '').lower()
    if recorded and recorded != sha:
        return _finish(version, SourceVersion.Intake.MISMATCH,
                       f'Register says {recorded[:16]}..., Drive file "{name}" is {sha[:16]}... - '
                       'the file changed or the wrong file is linked. Not stored.', actor, dry_run)
    if dry_run:
        return IntakeResult(version, 'verified' if recorded else 'computed', f'would store "{name}"')
    rel, sha = store(content, name)
    notes = []
    version.file_uri = rel
    if not recorded:
        version.checksum_sha256 = sha
    size_kb = round(len(content) / 1024)
    if version.file_size_kb and abs(version.file_size_kb - size_kb) > 1:
        notes.append(f'size recorded {version.file_size_kb} KB, actual {size_kb} KB')
    version.file_size_kb = size_kb
    pages = pdf_page_count(content) if name.lower().endswith('.pdf') else None
    if pages:
        if version.pages and version.pages != pages:
            notes.append(f'pages recorded {version.pages}, actual {pages}')
        version.pages = pages
    status = SourceVersion.Intake.VERIFIED if recorded else SourceVersion.Intake.COMPUTED
    note = f'Stored "{name}" ({size_kb} KB{f", {pages} pages" if pages else ""}).' + (
        ' Corrected: ' + '; '.join(notes) + '.' if notes else '')
    return _finish(version, status, note, actor, dry_run)


def _finish(version, status, note, actor, dry_run):
    if not dry_run:
        before = {'intake_status': version.intake_status}
        version.intake_status, version.intake_note, version.intake_at = status, note, timezone.now()
        version.save()
        SourceAuditEvent.objects.create(
            actor=actor, action=f'intake.{status}', object_type='SourceVersion', object_id=str(version.pk),
            before=before, after={'intake_status': status, 'file_uri': version.file_uri,
                                  'checksum_sha256': version.checksum_sha256, 'note': note})
    return IntakeResult(version, status, note)


def run_intake(codes=None, *, retry=False, dry_run=False, actor="file_intake", fetcher=None):
    summary = IntakeSummary()
    for version in candidates(codes, retry):
        summary.results.append(ingest(version, fetcher=fetcher, actor=actor, dry_run=dry_run))
    return summary
