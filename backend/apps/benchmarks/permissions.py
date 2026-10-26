"""Benchmark Studio is read-only in the portal (settings.BENCHMARK_CATALOGUE_READ_ONLY).

The manager-provided workbooks are the authoritative standard catalogue. InGage staff can view, search and
inspect it; every add / edit / delete, AI drafting, watcher, candidate, confirmation and release action is
refused here, on the server. The catalogue changes only through the controlled import commands.
"""
from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

READ_ONLY_MESSAGE = ('The benchmark library is the manager-provided standard catalogue and is read-only in the '
                     'portal. It changes only through a controlled workbook import.')


class CatalogueReadOnly(BasePermission):
    """Reads always pass; writes only when the read-only lock is off."""
    message = READ_ONLY_MESSAGE

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return not settings.BENCHMARK_CATALOGUE_READ_ONLY


def catalogue_locked():
    return settings.BENCHMARK_CATALOGUE_READ_ONLY
