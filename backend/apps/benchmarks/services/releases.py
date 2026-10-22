"""Stage 3.6: benchmark releases.

    create_release(label, user, notes)        draft; carries forward the current published release as 'unchanged'
    add_item / remove_item                     draft only
    submit(release, user)                      draft -> review; every added/updated benchmark must pass readiness
    approve(release, user)                     review -> approved; approver must not be the submitter
    publish(release, user)                     approved -> published; freezes snapshots + hashes, locks benchmarks,
                                               retires the previous published release (kept, never changed)
    reopen_benchmark(benchmark, user, reason)  active -> draft (new version label) for the next release
    current_release()                          the one release new scorecards may use
    diff(release)                              what changes against the release it is based on

Developer guide: only a published release can be used for a new scorecard; a
published change never overwrites historic assessments.
"""
import hashlib
import json
import re

from django.db import transaction
from django.utils import timezone

from ..models import (
    ApplicabilityRule, Benchmark, BenchmarkRelease, BenchmarkReleaseItem, EvidenceRule, SourceAuditEvent,
)
from .authoring import readiness

PILOT_MIN, PILOT_MAX = 20, 30  # first release: 20-30 benchmarks (developer guide)
Item = BenchmarkReleaseItem.ChangeType


class ReleaseError(Exception):
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


def _audit(user, action, release, after=None, reason=''):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type='BenchmarkRelease',
                                    object_id=str(release.pk), after=after, reason=reason)


def current_release():
    return BenchmarkRelease.objects.filter(status=BenchmarkRelease.Status.PUBLISHED).order_by('-published_at').first()


def _require(release, *statuses):
    if release.status not in statuses:
        raise ReleaseError(f'{release.release_label} is {release.status}; this needs {" or ".join(statuses)}.')


def eligibility(release, ready_map=None):
    """Every draft benchmark, whether it is in this release, and what (if anything) keeps it out.
    [{benchmark, code, title, included, ready, missing: [labels]}] sorted by code."""
    in_release = set(release.items.values_list('benchmark_id', flat=True))
    rows = []
    for b in Benchmark.objects.filter(status=Benchmark.Status.DRAFT).order_by('benchmark_code'):
        r = (ready_map or {}).get(b.pk) or readiness(b)
        missing = [c['label'] for c in r['checks'] if c['severity'] == 'required' and not c['ok']]
        rows.append({'benchmark': b, 'code': b.benchmark_code, 'title': b.title, 'included': b.pk in in_release,
                     'ready': not missing, 'missing': missing})
    return rows


def prefill(release, user):
    """Add every draft benchmark that passes its required checks and is not in the release yet.
    Returns (added codes, omitted [(code, missing)]). Never duplicates an item."""
    _require(release, BenchmarkRelease.Status.DRAFT)
    added, omitted = [], []
    for row in eligibility(release):
        if row['included']:
            continue
        if row['ready']:
            add_item(release, row['benchmark'], user, impact_summary='Added by "include all ready benchmarks".')
            added.append(row['code'])
        else:
            omitted.append((row['code'], row['missing']))
    _audit(user, 'release.prefilled', release, {'added': added, 'omitted': [c for c, _ in omitted]})
    return added, omitted


def set_requires_composite(release, user, value):
    _require(release, BenchmarkRelease.Status.DRAFT)
    value = bool(value)
    if release.requires_composite != value:
        release.requires_composite = value
        release.save(update_fields=['requires_composite'])
        _audit(user, 'release.requires_composite', release, {'requires_composite': value})
    return release


def scoring_summary(release):
    """Which included benchmarks can produce a composite score under the active scoring model."""
    from .release_gates import active_scoring_model, score_rule_status
    model = active_scoring_model()
    missing = []
    for item in release.items.exclude(change_type=Item.RETIRED).select_related('benchmark').order_by('benchmark__benchmark_code'):
        ok, detail = score_rule_status(item.benchmark, model)
        if not ok:
            missing.append({'benchmark_code': item.benchmark.benchmark_code, 'detail': detail})
    return {'requires_composite': release.requires_composite, 'scoring_model': model.code if model else None,
            'missing': missing, 'fully_scoreable': not missing}


def create_release(label, user, notes='', *, requires_composite=False, prefill_ready=False):
    label = (label or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._ -]{1,40}', label):
        raise ReleaseError('Release label: up to 40 letters, digits, spaces, dots, dashes (e.g. "Release 1.0").')
    if BenchmarkRelease.objects.filter(release_label=label).exists():
        raise ReleaseError(f'A release called "{label}" already exists.')
    if BenchmarkRelease.objects.exclude(status__in=[BenchmarkRelease.Status.PUBLISHED, BenchmarkRelease.Status.RETIRED]).exists():
        raise ReleaseError('Finish (publish) or delete the release already in progress before starting another.')
    base = current_release()
    with transaction.atomic():
        release = BenchmarkRelease.objects.create(release_label=label, release_notes=notes, based_on=base, created_by=user,
                                                  requires_composite=bool(requires_composite))
        if base:
            for item in base.items.exclude(change_type=Item.RETIRED).select_related('benchmark'):
                BenchmarkReleaseItem.objects.create(release=release, benchmark=item.benchmark, change_type=Item.UNCHANGED,
                                                    impact_summary='Carried forward unchanged.')
        _audit(user, 'release.created', release, {'label': label, 'based_on': base.release_label if base else None,
                                                  'requires_composite': bool(requires_composite)})
        if prefill_ready:
            prefill(release, user)
    return release


def _was_published(benchmark):
    return BenchmarkReleaseItem.objects.filter(
        benchmark=benchmark, release__status__in=[BenchmarkRelease.Status.PUBLISHED, BenchmarkRelease.Status.RETIRED],
    ).exists()


def add_item(release, benchmark, user, *, retire=False, impact_summary=''):
    _require(release, BenchmarkRelease.Status.DRAFT)
    if retire:
        if benchmark.status != Benchmark.Status.ACTIVE:
            raise ReleaseError(f'Only an active benchmark can be retired ({benchmark.benchmark_code} is {benchmark.status}).')
        change = Item.RETIRED
    else:
        if benchmark.status != Benchmark.Status.DRAFT:
            raise ReleaseError(f'{benchmark.benchmark_code} is {benchmark.status}; reopen it as a draft to change it.')
        change = Item.UPDATED if _was_published(benchmark) else Item.ADDED
    item, created = BenchmarkReleaseItem.objects.update_or_create(
        release=release, benchmark=benchmark, defaults={'change_type': change, 'impact_summary': impact_summary.strip()})
    _audit(user, 'release.item_set', release, {'benchmark': benchmark.benchmark_code, 'change_type': change})
    return item


def remove_item(release, benchmark, user):
    _require(release, BenchmarkRelease.Status.DRAFT)
    item = release.items.filter(benchmark=benchmark).first()
    if item is None:
        raise ReleaseError(f'{benchmark.benchmark_code} is not in {release.release_label}.')
    if item.change_type == Item.UNCHANGED:
        raise ReleaseError(f'{benchmark.benchmark_code} is carried forward from the current release; '
                           'mark it retired instead of removing it.')
    item.delete()
    _audit(user, 'release.item_removed', release, {'benchmark': benchmark.benchmark_code})


def check_release(release):
    """(problems, warnings): problems block review/approval/publish."""
    items = list(release.items.select_related('benchmark'))
    problems, warnings = [], []
    if not items:
        problems.append('The release has no benchmarks.')
    for item in items:
        if item.change_type in (Item.ADDED, Item.UPDATED):
            if item.benchmark.status != Benchmark.Status.DRAFT:
                problems.append(f'{item.benchmark.benchmark_code}: is {item.benchmark.status}, expected a draft.')
            missing = [c['label'] for c in readiness(item.benchmark)['checks'] if c['severity'] == 'required' and not c['ok']]
            if missing:
                problems.append(f'{item.benchmark.benchmark_code}: ' + '; '.join(missing))
    live = sum(1 for i in items if i.change_type != Item.RETIRED)
    if release.based_on is None and not PILOT_MIN <= live <= PILOT_MAX:
        warnings.append(f'Pilot size (guidance only, does not block submission): the first release is suggested to '
                        f'hold {PILOT_MIN}-{PILOT_MAX} pilot benchmarks; this one has {live}.')
    # Approved scoring weights are a required readiness check for every added/updated benchmark (above).
    # Carried-forward items were scored when published; their weights are reported, never re-checked here.
    return problems, warnings


def submit(release, user):
    _require(release, BenchmarkRelease.Status.DRAFT)
    problems, warnings = check_release(release)
    if problems:
        raise ReleaseError('Not ready for review.', problems)
    release.status, release.submitted_by, release.submitted_at = BenchmarkRelease.Status.REVIEW, user, timezone.now()
    release.save()
    _audit(user, 'release.submitted', release, {'warnings': warnings})
    return warnings


def send_back(release, user, reason):
    _require(release, BenchmarkRelease.Status.REVIEW, BenchmarkRelease.Status.APPROVED)
    if not (reason or '').strip():
        raise ReleaseError('Say what needs to change.')
    release.status = BenchmarkRelease.Status.DRAFT
    release.approved_by = release.approved_at = None
    release.save()
    _audit(user, 'release.sent_back', release, reason=reason)


def approve(release, user, note=''):
    _require(release, BenchmarkRelease.Status.REVIEW)
    if release.submitted_by_id == user.pk:
        raise ReleaseError('The person who submitted a release cannot approve it (four-eyes rule).')
    problems, _ = check_release(release)
    if problems:
        raise ReleaseError('Something changed since submission; send it back.', problems)
    release.status, release.approved_by, release.approved_at = BenchmarkRelease.Status.APPROVED, user, timezone.now()
    release.save()
    _audit(user, 'release.approved', release, reason=note)


def snapshot(benchmark):
    """Everything that defines the benchmark, frozen as plain data."""
    levels = {m.level: {'definition': m.definition, 'measurement_rule': m.measurement_rule,
                        'observable_requirements': m.observable_requirements, 'minimum_evidence': m.minimum_evidence,
                        'outcome_expectations': m.outcome_expectations, 'non_examples': m.non_examples,
                        'requires_manual_review': m.requires_manual_review}
              for m in benchmark.maturity_levels.all()}
    rules = EvidenceRule.objects.filter(benchmark=benchmark).select_related('evidence_type').order_by('level', 'title')
    applic = (ApplicabilityRule.objects.filter(benchmark=benchmark).prefetch_related('institution_types', 'programme_types')
              .order_by('priority', 'created_at'))
    links = benchmark.requirement_links.select_related('requirement__version__document').order_by('requirement__code')
    return {
        'benchmark_code': benchmark.benchmark_code, 'title': benchmark.title, 'pillar': benchmark.pillar.code,
        'kind': benchmark.benchmark_kind, 'version_label': benchmark.version_label,
        'capability': benchmark.capability.definition, 'expert_owner': benchmark.expert_owner,
        'target_guidance': benchmark.target_guidance,
        'framework': benchmark.framework.code if benchmark.framework_id else None,
        'weight': str(benchmark.weight) if benchmark.weight is not None else None,
        'pillar_weight': str(benchmark.pillar.weight) if benchmark.pillar.weight is not None else None,
        'naac_crosswalk': benchmark.naac_crosswalk,
        'evidence_types': sorted(benchmark.evidence_types.values_list('code', flat=True)),
        'levels': levels,
        'evidence_rules': [{'level': r.level, 'evidence_type': r.evidence_type.code, 'title': r.title,
                            'mandatory': r.mandatory, 'minimum_count': r.minimum_count,
                            'minimum_currency_months': r.minimum_currency_months, 'scope_rule': r.scope_rule,
                            'validation_method': r.validation_method, 'privacy': r.privacy_classification}
                           for r in rules],
        'applicability_rules': [{'priority': a.priority, 'result': a.result,
                                 'institution_types': sorted(a.institution_types.values_list('code', flat=True)),
                                 'autonomous_statuses': a.autonomous_statuses,
                                 'programme_types': sorted(a.programme_types.values_list('code', flat=True)),
                                 'approval_bodies': a.approval_bodies, 'jurisdiction': a.jurisdiction,
                                 'reason': a.reason} for a in applic],
        'requirements': [{'code': link.requirement.code, 'relationship': link.relationship,
                          'statement': link.requirement.statement, 'source_quote': link.requirement.source_quote,
                          'page': link.requirement.page, 'source_code': link.requirement.version.document.source_code,
                          'source_version': link.requirement.version.version_label} for link in links],
    }


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def publish(release, user):
    _require(release, BenchmarkRelease.Status.APPROVED)
    problems, _ = check_release(release)
    if problems:
        raise ReleaseError('Something changed since approval; send it back.', problems)
    with transaction.atomic():
        now = timezone.now()
        previous = current_release()
        hashes = []
        for item in release.items.select_related('benchmark').order_by('benchmark__benchmark_code'):
            if item.change_type == Item.UNCHANGED and release.based_on:
                old = release.based_on.items.filter(benchmark=item.benchmark).first()
                item.snapshot, item.snapshot_hash = old.snapshot, old.snapshot_hash
            else:
                item.snapshot = snapshot(item.benchmark)
                item.snapshot_hash = _hash(item.snapshot)
            item.save()
            hashes.append(f'{item.benchmark.benchmark_code}:{item.change_type}:{item.snapshot_hash}')
            bench = item.benchmark
            if item.change_type in (Item.ADDED, Item.UPDATED):
                bench.status = Benchmark.Status.ACTIVE
                bench.effective_from = bench.effective_from or now.date()
                bench.save()
            elif item.change_type == Item.RETIRED:
                bench.status, bench.effective_to = Benchmark.Status.WITHDRAWN, now.date()
                bench.save()
        release.content_hash = hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
        release.status, release.published_by, release.published_at = BenchmarkRelease.Status.PUBLISHED, user, now
        release.save()
        if previous and previous.pk != release.pk:
            previous.status, previous.retired_at = BenchmarkRelease.Status.RETIRED, now
            previous.save()
            _audit(user, 'release.retired', previous, {'replaced_by': release.release_label})
        _audit(user, 'release.published', release, {'content_hash': release.content_hash, 'items': len(hashes)})
        from .candidates import mark_published
        mark_published(release)  # approved candidates for these benchmarks are now in effect
    return release


def reopen_benchmark(benchmark, user, reason):
    """Active -> draft with a new version label, for the next release. Published snapshots are untouched."""
    if benchmark.status != Benchmark.Status.ACTIVE:
        raise ReleaseError(f'{benchmark.benchmark_code} is {benchmark.status}; only an active benchmark can be reopened.')
    if not (reason or '').strip():
        raise ReleaseError('Give a reason for reopening.')
    old = benchmark.version_label
    m = re.fullmatch(r'(.*)\.r(\d+)', old)
    benchmark.version_label = f'{m.group(1)}.r{int(m.group(2)) + 1}' if m else f'{old}.r1'
    benchmark.status = Benchmark.Status.DRAFT
    from .confirmation import clear_for_new_version
    clear_for_new_version(benchmark)  # the new version has not been confirmed yet
    benchmark.save()
    SourceAuditEvent.objects.create(actor=user.email, action='benchmark.reopened', object_type='Benchmark',
                                    object_id=str(benchmark.pk), before={'version_label': old, 'status': 'active'},
                                    after={'version_label': benchmark.version_label, 'status': 'draft'}, reason=reason)
    return benchmark


def diff(release):
    """Per benchmark: what this release changes against the release it is based on."""
    out = []
    for item in release.items.select_related('benchmark').order_by('benchmark__benchmark_code'):
        old = release.based_on.items.filter(benchmark=item.benchmark).first() if release.based_on else None
        new = item.snapshot or (snapshot(item.benchmark) if item.change_type != Item.RETIRED else None)
        changes = []
        if item.change_type == Item.UPDATED and old and old.snapshot and new:
            for key in ('title', 'levels', 'evidence_rules', 'applicability_rules', 'requirements', 'evidence_types',
                        'expert_owner', 'target_guidance'):
                if old.snapshot.get(key) != new.get(key):
                    changes.append(key)
        out.append({'benchmark_code': item.benchmark.benchmark_code, 'title': item.benchmark.title,
                    'change_type': item.change_type, 'changed': changes, 'impact_summary': item.impact_summary})
    return out
