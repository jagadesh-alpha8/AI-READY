"""Shared sprint lookup + institution-access check for the nested
`/sprints/<id>/...` sub-resource views (documents, extraction, facts, gaps,
scoring, recommendations, reports). Those views fetch their sprint manually
via a URL kwarg rather than through DRF's generic get_object(), so they
can't rely on a permission class's has_object_permission() alone -- this
gives them the same institution-scoping check as a single call.
"""
from django.shortcuts import get_object_or_404

from apps.accounts.permissions import require_institution_access

from .models import Sprint


def get_authorized_sprint(user, sprint_id):
    sprint = get_object_or_404(Sprint, pk=sprint_id)
    require_institution_access(user, sprint)
    return sprint
