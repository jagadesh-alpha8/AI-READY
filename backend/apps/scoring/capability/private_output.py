"""Where offline commands may write files that carry an institution's text: never inside the code.

In a checkout the code is the repository (the folder above backend/). In the Docker image the backend is copied to
/app, whose parent is /, so "outside the repository" meant nowhere and every export refused (25 Nov audit, finding 4);
there the code is /app itself.
"""
from pathlib import Path

from django.conf import settings


def code_root():
    backend = Path(settings.BASE_DIR).resolve()
    parent = backend.parent
    return backend if parent == Path(parent.anchor) else parent


def inside_code(target):
    root = code_root()
    target = Path(target).resolve()
    return target == root or root in target.parents
