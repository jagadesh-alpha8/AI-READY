"""Confirm a DRAFT benchmark's content (Studio > Benchmark Library).

Confirmation is a sign-off on what the draft says right now. It is separate from publishing:
a confirmed draft is still a draft, and it reaches assessments only when a release that
includes it is published (services/releases.py) -- nothing here touches releases.

- Only drafts, and only once the release checklist's required items pass.
- What was confirmed is fingerprinted (the same frozen snapshot a release would take). If the
  benchmark is edited afterwards -- levels, evidence or applicability rules, requirement links,
  owner, target -- it shows "changed since confirmed" until someone confirms it again.
- Reopening a published benchmark as the next draft version clears the confirmation (that version
  has not been confirmed yet).
- Every confirmation and withdrawal is written to the audit trail with the fingerprint, version and
  person; earlier confirmations stay there, so the history is kept.
- Source Library versions have their own approval (services/approval.py); this is not that.
"""
from django.db import transaction
from django.utils import timezone

from ..models import Benchmark, SourceAuditEvent
from . import authoring, releases

CONFIRMED, CHANGED, NONE = 'confirmed', 'changed', 'none'


class ConfirmationError(Exception):
    pass


def content_hash(benchmark):
    return releases._hash(releases.snapshot(benchmark))


def state(benchmark):
    """'confirmed' / 'changed' / 'none' for a draft; None once it is not a draft."""
    if benchmark.status != Benchmark.Status.DRAFT:
        return None
    if not benchmark.confirmed_hash:
        return NONE
    return CONFIRMED if benchmark.confirmed_hash == content_hash(benchmark) else CHANGED


def _audit(user, action, benchmark, before, after, reason):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type='Benchmark',
                                    object_id=str(benchmark.pk), before=before, after=after, reason=reason)


def _current(benchmark):
    return {'confirmed_hash': benchmark.confirmed_hash or None,
            'confirmed_by': benchmark.confirmed_by.email if benchmark.confirmed_by_id else None,
            'confirmed_at': benchmark.confirmed_at.isoformat() if benchmark.confirmed_at else None}


def confirm(benchmark, user, note=''):
    if benchmark.status != Benchmark.Status.DRAFT:
        raise ConfirmationError(f'{benchmark.benchmark_code} is {benchmark.status}; only a draft can be confirmed.')
    missing = [c['label'] for c in authoring.readiness(benchmark)['checks']
               if c['severity'] == 'required' and not c['ok']]
    if missing:
        raise ConfirmationError('Finish these before confirming: ' + '; '.join(missing) + '.')
    with transaction.atomic():
        row = Benchmark.objects.select_for_update().get(pk=benchmark.pk)  # the current row, locked
        fingerprint = content_hash(row)
        if row.confirmed_hash == fingerprint:
            raise ConfirmationError(f'{row.benchmark_code} is already confirmed and has not changed since.')
        before = _current(row)
        row.confirmed_by, row.confirmed_at, row.confirmed_hash = user, timezone.now(), fingerprint
        row.save(update_fields=['confirmed_by', 'confirmed_at', 'confirmed_hash', 'updated_at'])
        _audit(user, 'benchmark.confirmed', row, before, {**_current(row), 'version_label': row.version_label},
               (note or '').strip())
    _copy(row, benchmark)
    return benchmark


def withdraw_confirmation(benchmark, user, reason):
    if not (reason or '').strip():
        raise ConfirmationError('Give a reason for withdrawing the confirmation.')
    with transaction.atomic():
        row = Benchmark.objects.select_for_update().get(pk=benchmark.pk)
        if row.status != Benchmark.Status.DRAFT:
            raise ConfirmationError(f'{row.benchmark_code} is {row.status}; only a draft has a confirmation to withdraw.')
        if not row.confirmed_hash:
            raise ConfirmationError(f'{row.benchmark_code} is not confirmed.')
        before = _current(row)
        row.confirmed_by = row.confirmed_at = None
        row.confirmed_hash = ''
        row.save(update_fields=['confirmed_by', 'confirmed_at', 'confirmed_hash', 'updated_at'])
        _audit(user, 'benchmark.confirmation_withdrawn', row, before, {'version_label': row.version_label},
               reason.strip())
    _copy(row, benchmark)
    return benchmark


def _copy(src, dst):
    """Keep the caller's object in step with the saved row."""
    dst.confirmed_by, dst.confirmed_at, dst.confirmed_hash = src.confirmed_by, src.confirmed_at, src.confirmed_hash


def clear_for_new_version(benchmark):
    """Called when a published benchmark is reopened as the next draft version."""
    benchmark.confirmed_by = benchmark.confirmed_at = None
    benchmark.confirmed_hash = ''
