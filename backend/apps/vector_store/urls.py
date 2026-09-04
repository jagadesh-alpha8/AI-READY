"""Standalone routes for this app.

The sprint-scoped endpoints are NOT here: they live in `apps/sprints/urls.py`
alongside every other `/sprints/<id>/...` sub-resource, matching how documents,
facts, gaps and scoring already compose their nested routes. This module exists
so the app owns a URLConf if a non-nested route is ever needed.
"""
from django.urls import path

urlpatterns: list[path] = []
