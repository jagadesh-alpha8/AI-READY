"""The manager workbook baseline: the standard catalogue frozen as the release assessments use.

    publish_workbook_baseline(workbook, sha256, actor, commit=False)

The manager-provided workbook is authoritative, so there is no portal draft / review / approve / publish workflow
for it. Instead the controlled import (`manage.py import_aiqif <file> --commit --baseline`) freezes every current
AI-QIF indicator -- definition, levels, applicability and evidence rules, weights, origin and source mappings -- into
a release of kind "workbook_baseline", labelled with the workbook's fingerprint. Assessments and CRI coverage read
the current published release as before (services/releases.current_release), so they use this baseline and record
exactly which workbook it came from; the earlier current release is retired and kept, unchanged, for history.

Nothing about an indicator is changed to make it look approved: its own status (draft / active) stays what it is.
Running the same workbook again changes nothing.
"""
import hashlib

from django.db import transaction
from django.utils import timezone

from ..models import Benchmark, BenchmarkRelease, BenchmarkReleaseItem, SourceAuditEvent
from .aiqif_import import FRAMEWORK_CODE, VERSION_LABEL
from .provenance import frozen
from .releases import _hash, current_release, snapshot


class BaselineError(Exception):
    pass


def label_for(sha256):
    return f'{VERSION_LABEL} baseline {sha256[:8]}'


def _indicators():
    return (Benchmark.objects.filter(framework__code=FRAMEWORK_CODE).exclude(status=Benchmark.Status.WITHDRAWN)
            .select_related('pillar', 'capability', 'framework').order_by('benchmark_code'))


def plan(sha256):
    """What publishing would do, without saving: {label, indicators, current, unchanged}."""
    current = current_release()
    items = {b.benchmark_code: _hash({**snapshot(b), 'provenance': frozen(b)}) for b in _indicators()}
    content = hashlib.sha256('\n'.join(f'{c}:added:{h}' for c, h in sorted(items.items())).encode()).hexdigest()
    unchanged = bool(current and current.kind == BenchmarkRelease.Kind.WORKBOOK_BASELINE
                     and current.workbook_sha256 == sha256 and current.content_hash == content)
    return {'label': label_for(sha256), 'indicators': len(items), 'unchanged': unchanged,
            'current': current.release_label if current else None, 'content_hash': content}


def publish_workbook_baseline(workbook, sha256, actor, *, commit=False):
    """Returns (plan, release or None). Dry run unless commit."""
    p = plan(sha256)
    if not p['indicators']:
        raise BaselineError(f'No {VERSION_LABEL} indicators to freeze; import the workbook first.')
    if p['unchanged'] or not commit:
        return p, None
    with transaction.atomic():
        label = p['label']
        if BenchmarkRelease.objects.filter(release_label=label).exists():  # same workbook, catalogue changed since
            label = f'{label} {timezone.now():%Y%m%d%H%M}'
        now = timezone.now()
        release = BenchmarkRelease.objects.create(
            release_label=label[:40], kind=BenchmarkRelease.Kind.WORKBOOK_BASELINE, workbook=workbook[:255],
            workbook_sha256=sha256, release_notes=f'{VERSION_LABEL} as imported from the manager workbook {workbook} '
                                                 f'(SHA-256 {sha256}). Standard catalogue; no portal review.')
        hashes = []
        for bench in _indicators():
            snap = {**snapshot(bench), 'provenance': frozen(bench)}
            item = BenchmarkReleaseItem.objects.create(release=release, benchmark=bench,
                                                       change_type=BenchmarkReleaseItem.ChangeType.ADDED,
                                                       snapshot=snap, snapshot_hash=_hash(snap))
            hashes.append(f'{bench.benchmark_code}:{item.change_type}:{item.snapshot_hash}')
        previous = current_release()
        release.content_hash = hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
        release.status, release.published_at = BenchmarkRelease.Status.PUBLISHED, now
        release.save()
        if previous:
            previous.status, previous.retired_at = BenchmarkRelease.Status.RETIRED, now
            previous.save(update_fields=['status', 'retired_at'])
        SourceAuditEvent.objects.create(
            actor=actor, action='release.workbook_baseline', object_type='BenchmarkRelease', object_id=str(release.pk),
            after={'release': release.release_label, 'workbook': workbook, 'workbook_sha256': sha256,
                   'indicators': len(hashes), 'content_hash': release.content_hash,
                   'retired': previous.release_label if previous else None},
            reason='Manager workbook baseline (controlled import)')
    return p, release
