import re

import requests

from .constants import DRIVE_IMPORT_CHECKLIST
from .exceptions import PermanentDriveImportError, RecoverableDriveImportError

DRIVE_API_BASE = 'https://www.googleapis.com/drive/v3'
_LIST_TIMEOUT = 30
_DOWNLOAD_TIMEOUT = 60

#: Native Google Workspace types have no raw binary -- export to a real file
#: format instead, mapped to something ALLOWED_UPLOAD_EXTENSIONS accepts.
_EXPORT_MIME_MAP = {
    'application/vnd.google-apps.document': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.spreadsheet': (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx',
    ),
    'application/vnd.google-apps.presentation': ('application/pdf', '.pdf'),
}

_FOLDER_ID_RE = re.compile(r'/folders/([a-zA-Z0-9_-]+)')
_BARE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{10,}$')
_FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'


def parse_drive_folder_id(url):
    """Accepts .../drive/folders/<id>, .../drive/u/0/folders/<id>, or a bare
    folder ID. Raises PermanentDriveImportError if nothing recognizable is
    found -- a malformed link will never become valid on retry."""
    url = (url or '').strip()
    match = _FOLDER_ID_RE.search(url)
    if match:
        return match.group(1)
    if _BARE_ID_RE.match(url):
        return url
    raise PermanentDriveImportError(
        'Could not find a Drive folder ID in this link. Paste a folder link like '
        'https://drive.google.com/drive/folders/<id>, or the bare folder ID.',
    )


def list_drive_folder_files(folder_id, api_key, max_files, max_folders=200):
    """Return up to `max_files` {id, name, mimeType, size} dicts for
    non-trashed files anywhere under `folder_id`, walking subfolders
    recursively (breadth-first) and paging each folder's contents via
    pageToken. `max_folders` bounds how many folders total get walked, as a
    safety cap against a huge or deeply-nested tree; `visited` guards
    against revisiting a folder reachable through more than one path."""
    if not api_key:
        raise PermanentDriveImportError('GOOGLE_DRIVE_API_KEY is not configured on the server.')

    files = []
    folders_to_visit = [folder_id]
    visited = set()

    while folders_to_visit and len(files) < max_files and len(visited) < max_folders:
        current_folder = folders_to_visit.pop(0)
        if current_folder in visited:
            continue
        visited.add(current_folder)

        page_token = None
        while len(files) < max_files:
            params = {
                'q': f"'{current_folder}' in parents and trashed=false",
                'fields': 'nextPageToken, files(id,name,mimeType,size)',
                'pageSize': min(100, max_files - len(files)),
                'key': api_key,
            }
            if page_token:
                params['pageToken'] = page_token
            try:
                resp = requests.get(f'{DRIVE_API_BASE}/files', params=params, timeout=_LIST_TIMEOUT)
            except requests.RequestException as exc:
                raise RecoverableDriveImportError(f'Network error listing Drive folder: {exc}') from exc

            _raise_for_drive_status(resp, context='listing the folder')
            payload = resp.json()
            for entry in payload.get('files', []):
                if entry.get('mimeType') == _FOLDER_MIME_TYPE:
                    folders_to_visit.append(entry['id'])
                else:
                    files.append(entry)
                    if len(files) >= max_files:
                        break

            page_token = payload.get('nextPageToken')
            if not page_token or len(files) >= max_files:
                break

    return files[:max_files]


def download_drive_file(file_meta, api_key):
    """Return (content_bytes, filename_with_extension, mime_type) for one
    Drive file. Native Google Workspace types (Docs/Sheets/Slides) are
    exported to an allowed format; everything else is downloaded as-is via
    alt=media. Raises PermanentDriveImportError for an unsupported Google
    Workspace type (e.g. Forms/Drawings) that has no sensible export."""
    file_id = file_meta['id']
    mime_type = file_meta.get('mimeType', '')
    name = file_meta['name']

    if mime_type in _EXPORT_MIME_MAP:
        export_mime, ext = _EXPORT_MIME_MAP[mime_type]
        url = f'{DRIVE_API_BASE}/files/{file_id}/export'
        params = {'mimeType': export_mime, 'key': api_key}
        out_name = name if name.lower().endswith(ext) else f'{name}{ext}'
        out_mime = export_mime
    elif mime_type.startswith('application/vnd.google-apps.'):
        raise PermanentDriveImportError(
            f"'{name}' is a Google Workspace file type ({mime_type}) with no supported export format.",
        )
    else:
        url = f'{DRIVE_API_BASE}/files/{file_id}'
        params = {'alt': 'media', 'key': api_key}
        out_name = name
        out_mime = mime_type or 'application/octet-stream'

    try:
        resp = requests.get(url, params=params, timeout=_DOWNLOAD_TIMEOUT)
    except requests.RequestException as exc:
        raise RecoverableDriveImportError(f"Network error downloading '{name}': {exc}") from exc

    _raise_for_drive_status(resp, context=f"downloading '{name}'")
    return resp.content, out_name, out_mime


def _raise_for_drive_status(resp, *, context):
    if resp.status_code == 200:
        return
    if resp.status_code == 403:
        raise PermanentDriveImportError(
            f'Google Drive denied access while {context} (403). Confirm the folder is shared as '
            '"Anyone with the link — Viewer".',
        )
    if resp.status_code == 404:
        raise PermanentDriveImportError(f'Google Drive returned 404 while {context}. Check the link.')
    if resp.status_code >= 500:
        raise RecoverableDriveImportError(f'Google Drive returned {resp.status_code} while {context}.')
    raise PermanentDriveImportError(
        f'Google Drive rejected the request while {context} ({resp.status_code}): {resp.text[:200]}',
    )


def classify_filename(filename):
    """Return the DRIVE_IMPORT_CHECKLIST 'type' slug whose keywords appear
    (case-insensitive substring match) in `filename`, checked in
    DRIVE_IMPORT_CHECKLIST's own order; None if nothing matches. Does not
    know about already-claimed slots -- the caller (run_drive_import_job)
    tracks "first matching, unclaimed slot wins" itself."""
    lower = filename.lower()
    for item in DRIVE_IMPORT_CHECKLIST:
        if any(kw in lower for kw in item['keywords']):
            return item['type']
    return None
