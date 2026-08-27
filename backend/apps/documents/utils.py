import hashlib
import os
import uuid


def document_upload_path(instance, filename):
    """Structured, non-guessable storage path -- never the client's raw path.

    `os.path.basename` strips any directory components a crafted filename
    might carry, and the uuid prefix means two uploads with the same
    filename never collide or overwrite each other.
    """
    safe_name = os.path.basename(filename)
    return f'sprints/{instance.sprint_id}/documents/{uuid.uuid4().hex}_{safe_name}'


def compute_file_checksum(file_obj):
    """SHA-256 of the file's actual bytes, used for real duplicate detection."""
    hasher = hashlib.sha256()
    for chunk in file_obj.chunks():
        hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()


def humanize_filename(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    name = name.replace('_', ' ').replace('-', ' ').strip()
    return name.title() if name else filename
