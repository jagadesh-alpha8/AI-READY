import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

from celery import shared_task
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from .constants import DRIVE_IMPORT_CHECKLIST
from .drive_import import (
    classify_filename, download_drive_file, is_importable, list_drive_folder_files, parse_drive_folder_id,
)
from .exceptions import PermanentDriveImportError, RecoverableDriveImportError
from .services import DocumentValidationError, create_document_from_file

logger = logging.getLogger(__name__)

#: document_type for Drive files that don't fill a checklist slot -- they are
#: still imported so the whole folder lands in the sprint.
ADDITIONAL_DOCUMENT_TYPE = 'supporting_document'


@shared_task(bind=True, max_retries=settings.GOOGLE_DRIVE_IMPORT_MAX_RETRIES, acks_late=True)
def run_drive_import_job(self, job_id):
    """Scan a Drive folder (root + every subfolder) and import EVERY supported
    file through the same document-creation path as a manual upload. The
    first filename matching each DRIVE_IMPORT_CHECKLIST slot fills that slot;
    every other file is imported as a supporting document. A single file's
    failure (bad export, validation reject, unsupported type) doesn't fail the
    whole job -- it's recorded in `results['skipped_files']` and the rest keep
    going.
    """
    from .models import DriveImportJob

    try:
        job = DriveImportJob.objects.select_related('sprint').get(id=job_id)
    except DriveImportJob.DoesNotExist:
        logger.error('documents.drive_import.missing_job job_id=%s', job_id)
        return None

    if not settings.GOOGLE_DRIVE_API_KEY:
        _fail(
            job,
            'Google Drive is not configured on the server (GOOGLE_DRIVE_API_KEY is unset). '
            'Contact your administrator.',
        )
        return None

    if not _set_status(
        job, DriveImportJob.Status.SCANNING, started_at=job.started_at or timezone.now(), error_message='',
    ):
        logger.info('documents.drive_import.cancelled_before_start job_id=%s', job.id)
        return None
    logger.info('documents.drive_import.scanning job_id=%s attempt=%d', job.id, self.request.retries + 1)

    try:
        folder_id = parse_drive_folder_id(job.drive_url)
        # Walk the WHOLE tree -- root folder plus every subfolder. Every file
        # is imported, not just one per checklist slot, so there is no early
        # stop once the checklist fills up.
        files = list_drive_folder_files(
            folder_id, settings.GOOGLE_DRIVE_API_KEY, settings.GOOGLE_DRIVE_IMPORT_MAX_FILES,
            max_folders=settings.GOOGLE_DRIVE_IMPORT_MAX_FOLDERS,
            max_workers=settings.GOOGLE_DRIVE_IMPORT_CONCURRENCY,
        )
    except PermanentDriveImportError as exc:
        _fail(job, str(exc))
        return None
    except RecoverableDriveImportError as exc:
        return _handle_recoverable(self, job, exc)

    if not files:
        _fail(
            job,
            'No files were found in this Drive folder. Check the link, and make sure the '
            'folder is shared as "Anyone with the link — Viewer".',
        )
        return None

    job.files_scanned = len(files)
    job.save(update_fields=['files_scanned', 'updated_at'])

    skipped = []
    importable = []
    for entry in files:
        if is_importable(entry):
            importable.append(entry)
        else:
            skipped.append({'filename': _display_name(entry), 'reason': 'Unsupported file type.'})

    claimed = _claim_slots(importable)
    slot_by_file_id = {meta['id']: slot for slot, meta in claimed.items()}

    if not _set_status(job, DriveImportJob.Status.DOWNLOADING):
        logger.info('documents.drive_import.cancelled_after_scan job_id=%s', job.id)
        return str(job.id)

    checklist_by_slot = {item['type']: item for item in DRIVE_IMPORT_CHECKLIST}
    results = {
        item['type']: {'status': 'missing', 'filename': None, 'document_id': None}
        for item in DRIVE_IMPORT_CHECKLIST
    }
    additional = []
    imported = 0
    progress = {'processed': 0, 'total': len(importable), 'current_file': ''}
    results.update(additional_files=additional, skipped_files=skipped, progress=progress)

    # Files are handled one at a time, in listing order: each one is
    # downloaded, saved as a Document, and the job's progress is written
    # straight away -- so the Upload Data Pack page (which polls the job)
    # shows every document in the records table as soon as it lands, instead
    # of all at once at the end. Downloads still prefetch concurrently in the
    # background; only the save-and-report step is sequential.
    cancelled = False
    for entry, outcome in _iter_downloads(importable):
        # Checked before every file: a Stop click lands between two files,
        # keeping everything imported so far and importing nothing more.
        if _is_cancelled(job):
            cancelled = True
            break
        progress['current_file'] = _display_name(entry)
        if isinstance(outcome, Exception):
            skipped.append({'filename': _display_name(entry), 'reason': str(outcome)})
            _save_progress(job, results, imported, progress)
            continue
        content, filename, mime_type = outcome

        slot = slot_by_file_id.get(entry['id'])
        if slot:
            document_type, owner_role = slot, checklist_by_slot[slot]['owner']
        else:
            # Not a checklist match (or a second file for an already-claimed
            # slot): still imported, as a general supporting document.
            document_type, owner_role = ADDITIONAL_DOCUMENT_TYPE, ''

        upload = SimpleUploadedFile(filename, content, content_type=mime_type)
        try:
            document = create_document_from_file(
                sprint=job.sprint, file_obj=upload, document_type=document_type,
                owner_role=owner_role, uploaded_by=job.created_by,
            )
        except DocumentValidationError as exc:
            skipped.append({'filename': _display_name(entry, filename), 'reason': _flatten_errors(exc.errors)})
            _save_progress(job, results, imported, progress)
            continue

        imported += 1
        if slot:
            results[slot] = {'status': 'found', 'filename': filename, 'document_id': str(document.id)}
        else:
            additional.append({
                'filename': filename, 'folder': entry.get('folder_path', ''), 'document_id': str(document.id),
            })
        _save_progress(job, results, imported, progress)

    progress['current_file'] = ''
    job.results = results
    job.files_imported = imported
    job.save(update_fields=['results', 'files_imported', 'updated_at'])
    if cancelled or not _set_status(job, DriveImportJob.Status.COMPLETED, completed_at=timezone.now()):
        logger.info('documents.drive_import.cancelled job_id=%s imported=%d', job.id, imported)
    else:
        logger.info('documents.drive_import.completed job_id=%s imported=%d', job.id, imported)
    return str(job.id)


def _set_status(job, status, **fields):
    """Move the job to `status` unless the user already cancelled it.

    A conditional UPDATE rather than `job.save()`, so a Stop click that lands
    while this worker is mid-step can never be overwritten back to an active
    or completed status. Returns False if the job was cancelled.
    """
    from .models import DriveImportJob

    updated = DriveImportJob.objects.filter(id=job.id).exclude(
        status=DriveImportJob.Status.CANCELLED,
    ).update(status=status, updated_at=timezone.now(), **fields)
    if not updated:
        job.status = DriveImportJob.Status.CANCELLED
        return False
    job.status = status
    for name, value in fields.items():
        setattr(job, name, value)
    return True


def _is_cancelled(job):
    from .models import DriveImportJob

    return DriveImportJob.objects.filter(id=job.id, status=DriveImportJob.Status.CANCELLED).exists()


def _claim_slots(files):
    """Map each checklist slot to the FIRST file whose name matches it.

    First-match-wins in listing order, which is why the folder walk keeps its
    ordering deterministic even when it fetches folders concurrently.
    """
    claimed = {}
    for entry in files:
        slot = classify_filename(entry['name'])
        if slot is None or slot in claimed:
            continue
        claimed[slot] = entry
    return claimed


def _display_name(entry, filename=None):
    """'Reports/2024/AQAR.pdf' for a subfolder file, the plain name for root."""
    name = filename or entry['name']
    folder = entry.get('folder_path', '')
    return f'{folder}/{name}' if folder else name


def _flatten_errors(errors):
    """DRF serializer errors -> one readable line for the results panel."""
    if isinstance(errors, dict):
        return ' '.join(_flatten_errors(v) for v in errors.values())
    if isinstance(errors, (list, tuple)):
        return ' '.join(_flatten_errors(v) for v in errors)
    return str(errors)


def _save_progress(job, results, imported, progress):
    """Persist per-file progress so the polling page can update mid-import."""
    progress['processed'] += 1
    job.results = results
    job.files_imported = imported
    job.save(update_fields=['results', 'files_imported', 'updated_at'])


def _iter_downloads(entries):
    """Yield `(entry, (content, filename, mime_type) | Exception)` in listing
    order, one file at a time, as soon as each is ready.

    Downloads run concurrently in the background, but results are handed back
    strictly in order, so the caller can save each document the moment its
    bytes arrive. A failure is yielded rather than raised, because one bad
    export must not fail every other file in the folder.
    """
    if not entries:
        return

    api_key = settings.GOOGLE_DRIVE_API_KEY
    workers = min(settings.GOOGLE_DRIVE_IMPORT_CONCURRENCY, len(entries))

    def fetch(entry):
        try:
            return entry, download_drive_file(entry, api_key)
        except (PermanentDriveImportError, RecoverableDriveImportError) as exc:
            return entry, exc

    if workers <= 1:
        yield from (fetch(entry) for entry in entries)
        return

    # A bounded prefetch window (at most `workers` downloads in flight) rather
    # than `pool.map`, which submits every file up front: when the caller
    # stops early (user pressed Stop), only the in-flight handful is wasted,
    # and the rest are never fetched.
    pool = ThreadPoolExecutor(max_workers=workers)
    remaining = iter(entries)
    pending = deque(pool.submit(fetch, entry) for entry in islice(remaining, workers))
    try:
        while pending:
            result = pending.popleft().result()
            nxt = next(remaining, None)
            if nxt is not None:
                pending.append(pool.submit(fetch, nxt))
            yield result
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _handle_recoverable(task, job, exc):
    from .models import DriveImportJob

    max_retries = settings.GOOGLE_DRIVE_IMPORT_MAX_RETRIES
    attempt = task.request.retries + 1

    if attempt > max_retries:
        logger.error('documents.drive_import.retries_exhausted job_id=%s attempts=%d', job.id, attempt)
        _fail(job, f'Failed after {max_retries} retries: {exc}')
        return None

    # SCANNING doubles as the pre-download retry state -- DriveImportJob has
    # no separate RETRYING status (unlike ExtractionJob's 6-value enum),
    # since a retry here is always still pre-download.
    if not _set_status(job, DriveImportJob.Status.SCANNING, error_message=str(exc)):
        return None
    logger.warning('documents.drive_import.retrying job_id=%s attempt=%d error=%s', job.id, attempt, exc)

    countdown = settings.GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries)
    raise task.retry(exc=exc, countdown=countdown)


def _fail(job, message):
    from .models import DriveImportJob

    _set_status(job, DriveImportJob.Status.FAILED, error_message=message, completed_at=timezone.now())
