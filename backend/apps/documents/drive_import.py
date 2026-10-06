import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from .constants import ALLOWED_UPLOAD_EXTENSIONS, DRIVE_IMPORT_CHECKLIST
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


def _list_one_folder(folder_id, folder_path, api_key, max_files):
    """One folder's immediate contents, paging until exhausted or `max_files`.

    Returns `(files, subfolders)` where each file dict gains a `folder_path`
    ('' for the root folder, 'Reports/2024' for a nested one) and each
    subfolder is an `(id, path)` pair. Pure I/O over a single folder, so a
    whole level of the tree can be fetched concurrently.
    """
    files = []
    subfolders = []
    page_token = None

    while len(files) < max_files:
        params = {
            'q': f"'{folder_id}' in parents and trashed=false",
            'fields': 'nextPageToken, files(id,name,mimeType,size)',
            # Fixed page size. This used to be `min(100, max_files - len(files))`
            # against the GLOBAL running total, which shrank as the walk filled
            # up: at 199 of 200 files it asked for one record per round trip.
            # The global cap is applied once, after the walk.
            'pageSize': min(100, max_files),
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
                child_path = f"{folder_path}/{entry['name']}" if folder_path else entry['name']
                subfolders.append((entry['id'], child_path))
            else:
                files.append({**entry, 'folder_path': folder_path})

        page_token = payload.get('nextPageToken')
        if not page_token:
            break

    return files, subfolders


def list_drive_folder_files(
    folder_id, api_key, max_files, max_folders=200, *, stop_when=None, max_workers=8,
):
    """Return up to `max_files` {id, name, mimeType, size, folder_path} dicts
    for non-trashed files in `folder_id` itself AND anywhere under it, walking subfolders
    breadth-first. `max_folders` bounds how many folders total get walked, as
    a safety cap against a huge or deeply-nested tree; `visited` guards
    against revisiting a folder reachable through more than one path.

    **A whole level is fetched concurrently.** The walk used to be strictly
    serial — one HTTP round trip per folder, waiting for each before starting
    the next — so a tree of thirty folders cost thirty round trips end to end.
    Folders within a level are independent, so they go out together.

    Ordering is preserved regardless of which request finishes first: results
    are gathered in submission order, not completion order. That matters
    because the caller claims a checklist slot with the *first* matching
    filename, so a reordered listing would silently change which file wins.

    `stop_when`: optional predicate over the files found so far. When it
    returns True the walk stops immediately — the importer uses it to stop
    once every checklist slot is filled, rather than walking a 200-folder
    Drive to find twelve documents it already has.
    """
    if not api_key:
        raise PermanentDriveImportError('GOOGLE_DRIVE_API_KEY is not configured on the server.')

    files = []
    visited = set()
    level = [(folder_id, '')]

    while level and len(files) < max_files and len(visited) < max_folders:
        # Respect max_folders across the level, not just per folder.
        budget = max_folders - len(visited)
        current = []
        for fid, path in level:
            if fid not in visited and len(current) < budget:
                visited.add(fid)
                current.append((fid, path))
        if not current:
            break

        if len(current) == 1:
            results = [_list_one_folder(current[0][0], current[0][1], api_key, max_files)]
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(current))) as pool:
                # `map` yields in submission order, so the walk stays
                # deterministic even though the requests race.
                results = list(pool.map(
                    lambda node: _list_one_folder(node[0], node[1], api_key, max_files), current,
                ))

        next_level = []
        for folder_files, subfolders in results:
            files.extend(folder_files)
            next_level.extend(subfolders)

        if stop_when is not None and stop_when(files):
            break

        level = next_level

    return files[:max_files]


def is_importable(file_meta):
    """Cheap pre-download check: can this file possibly pass the upload
    extension allowlist? Workspace types are judged by their export format,
    everything else by the extension on its Drive filename. Lets the importer
    skip a folder's .txt/.mp4/etc. without pulling their bytes first."""
    mime_type = file_meta.get('mimeType', '')
    if mime_type in _EXPORT_MIME_MAP:
        return True
    if mime_type.startswith('application/vnd.google-apps.'):
        return False
    return os.path.splitext(file_meta['name'])[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


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
