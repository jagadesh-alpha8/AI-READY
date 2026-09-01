class DriveImportError(Exception):
    """Base class for Google Drive import errors."""


class RecoverableDriveImportError(DriveImportError):
    """Transient failure (network hiccup, Drive 5xx) worth retrying."""


class PermanentDriveImportError(DriveImportError):
    """Won't be fixed by retrying (bad URL, folder not public, 404/403)."""
