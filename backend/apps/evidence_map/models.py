"""The evidence map: every page of a sprint read once against the rubric, and what it was found to be evidence of.

Specification: claude.ai project doc `claude/ai-ready-evidence-map-spec.md` (24 Nov 2026).

Tags route, they never credit: a tag can put a page in front of the judge; only the judge's cited quotation earns
credit. Nothing in this app is read by an assessment yet (pull request 1 of the build: tagging only).
"""
import uuid

from django.db import models


class MapPage(models.Model):
    """What one page text was found to be evidence of, under one map version and one model.

    Keyed by the hash of the page's rendered evidence text (whitespace and case ignored, as page deduplication
    compares pages), so identical pages anywhere share one row and a page re-read with new text gets a new one.
    `tags` holds the college's own words (quotations): private, exported only where facts are."""

    class Status(models.TextChoices):
        TAGGED = 'tagged', 'Tagged'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped (no readable text)'

    text_hash = models.CharField(max_length=64)
    map_version = models.CharField(max_length=64)
    model = models.CharField(max_length=150)
    status = models.CharField(max_length=10, choices=Status.choices)
    page_type = models.CharField(max_length=40, blank=True)
    #: [{indicator, requirements, strength, quote, quote_found, reason}], already checked (spec.validate).
    tags = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    #: The page the row was made from (a representative of every page with this text), for audits.
    page_id = models.CharField(max_length=36, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['text_hash', 'map_version', 'model'],
                                               name='evidence_map_page_unique')]
        indexes = [models.Index(fields=['map_version', 'model', 'status'])]

    def __str__(self):
        return f'MapPage({self.text_hash[:12]}, {self.status}, {len(self.tags)} tags)'


class MapJob(models.Model):
    """One tagging pass over a sprint: what it read, what it cost and how it ended. Re-running a sprint tags only
    the pages with no tagged row for the same map version and model."""

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        STOPPED = 'stopped', 'Stopped at the spend cap'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='evidence_map_jobs')
    map_version = models.CharField(max_length=64)
    model = models.CharField(max_length=150)
    shape = models.CharField(max_length=16)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    pages_total = models.PositiveIntegerField(default=0)
    #: Distinct page texts among the readable pages (identical pages are tagged once), and how many of those already
    #: had a tagged row when the pass started. The tagged share is measured on these, not on pages_total. Null on
    #: jobs from before they were recorded.
    pages_unique = models.PositiveIntegerField(null=True, blank=True)
    pages_done_before = models.PositiveIntegerField(null=True, blank=True)
    pages_to_tag = models.PositiveIntegerField(default=0)
    pages_tagged = models.PositiveIntegerField(default=0)
    pages_failed = models.PositiveIntegerField(default=0)
    pages_skipped = models.PositiveIntegerField(default=0)
    chunks_total = models.PositiveIntegerField(default=0)
    chunks_done = models.PositiveIntegerField(default=0)
    requests = models.PositiveIntegerField(default=0)
    spend_cap_usd = models.DecimalField(max_digits=10, decimal_places=4)
    spend_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    #: Counts from the checks (unknown IDs dropped, quotations not found, requirements moved...).
    checks = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'MapJob({self.sprint_id}, {self.status}, {self.pages_tagged}/{self.pages_to_tag})'
