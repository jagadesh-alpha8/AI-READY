import logging

from celery import shared_task
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from .constants import DRIVE_IMPORT_CHECKLIST
from .drive_import import classify_filename, download_drive_file, list_drive_folder_files, parse_drive_folder_id
from .exceptions import PermanentDriveImportError, RecoverableDriveImportError
from .services import DocumentValidationError, create_document_from_file

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=settings.GOOGLE_DRIVE_IMPORT_MAX_RETRIES, acks_late=True)
def run_drive_import_job(self, job_id):
    """Scan a Drive folder, classify its files against DRIVE_IMPORT_CHECKLIST,
    and import whatever matches through the same document-creation path as a
    manual upload. A single file's failure (bad export, validation reject)
    doesn't fail the whole job -- it's recorded in `results['skipped_files']`
    and the rest keep going.
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

    job.status = DriveImportJob.Status.SCANNING
    if job.started_at is None:
        job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
    logger.info('documents.drive_import.scanning job_id=%s attempt=%d', job.id, self.request.retries + 1)

    try:
        folder_id = parse_drive_folder_id(job.drive_url)
        files = list_drive_folder_files(
            folder_id, settings.GOOGLE_DRIVE_API_KEY, settings.GOOGLE_DRIVE_IMPORT_MAX_FILES,
            max_folders=settings.GOOGLE_DRIVE_IMPORT_MAX_FOLDERS,
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

    claimed = {}
    unmatched = []
    for f in files:
        slot = classify_filename(f['name'])
        if slot is None or slot in claimed:
            unmatched.append(f['name'])
            continue
        claimed[slot] = f

    job.status = DriveImportJob.Status.DOWNLOADING
    job.save(update_fields=['status', 'updated_at'])

    results = {}
    skipped = []
    imported = 0
    for item in DRIVE_IMPORT_CHECKLIST:
        slot = item['type']
        file_meta = claimed.get(slot)
        if file_meta is None:
            results[slot] = {'status': 'missing', 'filename': None, 'document_id': None}
            continue

        try:
            content, filename, mime_type = download_drive_file(file_meta, settings.GOOGLE_DRIVE_API_KEY)
        except (PermanentDriveImportError, RecoverableDriveImportError) as exc:
            skipped.append({'filename': file_meta['name'], 'reason': str(exc)})
            results[slot] = {'status': 'missing', 'filename': None, 'document_id': None}
            continue

        upload = SimpleUploadedFile(filename, content, content_type=mime_type)
        try:
            document = create_document_from_file(
                sprint=job.sprint, file_obj=upload, document_type=slot,
                owner_role=item['owner'], uploaded_by=job.created_by,
            )
        except DocumentValidationError as exc:
            skipped.append({'filename': filename, 'reason': str(exc.errors)})
            results[slot] = {'status': 'missing', 'filename': None, 'document_id': None}
            continue

        results[slot] = {'status': 'found', 'filename': filename, 'document_id': str(document.id)}
        imported += 1

    results['unmatched_files'] = unmatched
    results['skipped_files'] = skipped

    job.results = results
    job.files_imported = imported
    job.status = DriveImportJob.Status.COMPLETED
    job.completed_at = timezone.now()
    job.save(update_fields=['results', 'files_imported', 'status', 'completed_at', 'updated_at'])
    logger.info('documents.drive_import.completed job_id=%s imported=%d', job.id, imported)
    return str(job.id)


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
    job.status = DriveImportJob.Status.SCANNING
    job.error_message = str(exc)
    job.save(update_fields=['status', 'error_message', 'updated_at'])
    logger.warning('documents.drive_import.retrying job_id=%s attempt=%d error=%s', job.id, attempt, exc)

    countdown = settings.GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries)
    raise task.retry(exc=exc, countdown=countdown)


def _fail(job, message):
    from .models import DriveImportJob

    job.status = DriveImportJob.Status.FAILED
    job.error_message = message
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
