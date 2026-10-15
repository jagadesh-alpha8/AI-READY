"""Stage 5 rules. Every check lives here; the views only translate HTTP.

Lifecycle of an assessment cycle:
  not_started  benchmarks chosen from the current published release (rules engine);
               a reviewer settles any "requires review" ones
  in_progress  the college uploads evidence for each evidence request
  submitted    the college says it is done (InGage can send it back)
  reviewed     InGage reviewed the evidence and calculated the scores
  finalized    frozen: scores, weights, release and evidence decisions never change

Scores (each 0-100, kept separate -- ARCHITECTURE.md "Scoring contract"):
  compliance           share of the mandatory foundational (L3) evidence requests met;
                       empty for InGage-proposed benchmarks (nothing legal to comply with)
  maturity             level reached: none 0, L3 33.33, L2 66.67, L1 100. A level counts only
                       when every mandatory request for it (and the levels below) is met
  evidence confidence  average of the reviewers' five quality scores over counted evidence
  outcome              entered by the assessor from measured results (empty until then)
  composite            only with weights the benchmark owner approved for the active
                       scoring model; empty while any weighted part is empty
"""
import hashlib
import os
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.benchmarks.models import (
    APPROVAL_BODIES, AUTONOMOUS_STATUSES, ApplicabilityRule, BenchmarkReleaseItem, EvidenceType, InstitutionType,
    ProgrammeType, SourceAuditEvent,
)
from apps.benchmarks.services.applicability import Profile, evaluate_snapshot
from apps.benchmarks.services.releases import current_release

from .models import (
    LEVELS, ApplicableBenchmark, AssessmentCycle, BenchmarkAssessment, BenchmarkProfile, BenchmarkScoreRule,
    EvidenceItem, EvidenceReview, Programme, ScoringModel,
)

Status = AssessmentCycle.Status
LEVEL_ORDER = [LEVELS.L3, LEVELS.L2, LEVELS.L1]
MATURITY_POINTS = {'': Decimal('0'), 'L3': Decimal('33.33'), 'L2': Decimal('66.67'), 'L1': Decimal('100')}
MAX_FILE_BYTES = 25 * 1024 * 1024
ALLOWED_EXT = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.txt'}
SCORING_METHOD = 'stage5-v1'
CENT = Decimal('0.01')


class AssessmentError(Exception):
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


def _audit(user, action, obj, after=None, reason='', before=None):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type=type(obj).__name__,
                                    object_id=str(obj.pk), before=before, after=after, reason=reason)


def _require(cycle, *statuses):
    if cycle.status not in statuses:
        names = ' or '.join(Status(s).label.lower() for s in statuses)
        raise AssessmentError(f'This assessment is "{cycle.get_status_display().lower()}"; this needs it to be {names}.')


def _pct(value, field):
    if value in (None, ''):
        return None
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise AssessmentError(f'{field} must be a number from 0 to 100.')
    if not 0 <= d <= 100:
        raise AssessmentError(f'{field} must be from 0 to 100.')
    return d.quantize(CENT)


def _date(value, field):
    if value in (None, ''):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise AssessmentError(f'{field} must be a date like 2026-07-31.')


def _months_before(d, months):
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue


# -- institution profile ------------------------------------------------------------------

def profile_for(institution):
    try:
        p = institution.benchmark_profile
    except BenchmarkProfile.DoesNotExist:
        raise AssessmentError('This college has no benchmark profile yet (type, status, programmes).')
    programmes = list(institution.benchmark_programmes.filter(active=True).select_related('programme_type'))
    return Profile(institution_type=p.institution_type.code, autonomous_status=p.autonomous_status,
                   programme_types={x.programme_type.code for x in programmes},
                   approval_bodies=set(p.approval_bodies) | {x.approval_body for x in programmes if x.approval_body},
                   jurisdiction=p.jurisdiction)


def save_profile(institution, user, data):
    itype = InstitutionType.objects.filter(code=(data.get('institution_type') or '').strip()).first()
    if itype is None:
        raise AssessmentError('institution_type must be one of: '
                              + ', '.join(InstitutionType.objects.values_list('code', flat=True)))
    status = (data.get('autonomous_status') or '').strip()
    if status and status not in dict(AUTONOMOUS_STATUSES):
        raise AssessmentError(f'autonomous_status must be one of {list(dict(AUTONOMOUS_STATUSES))}.')
    bodies = list(dict.fromkeys(b.strip() for b in data.get('approval_bodies') or [] if b.strip()))
    progs = data.get('programmes') or []
    unknown = [b for b in bodies + [p.get('approval_body', '') for p in progs] if b and b not in APPROVAL_BODIES]
    if unknown:
        raise AssessmentError(f'Unknown approval bodies {unknown}; use {APPROVAL_BODIES}.')
    types = {t.code: t for t in ProgrammeType.objects.all()}
    for p in progs:
        if p.get('programme_type') not in types or not (p.get('name') or '').strip():
            raise AssessmentError('Each programme needs a name and a programme_type from: ' + ', '.join(types))
    with transaction.atomic():
        before = None
        if hasattr(institution, 'benchmark_profile'):
            old = institution.benchmark_profile
            before = {'institution_type': old.institution_type.code, 'autonomous_status': old.autonomous_status,
                      'approval_bodies': old.approval_bodies}
        BenchmarkProfile.objects.update_or_create(institution=institution, defaults={
            'institution_type': itype, 'autonomous_status': status, 'approval_bodies': bodies,
            'jurisdiction': (data.get('jurisdiction') or 'India').strip(), 'updated_by': user})
        institution.benchmark_programmes.all().delete()
        for p in progs:
            Programme.objects.create(institution=institution, programme_type=types[p['programme_type']],
                                     name=p['name'].strip()[:200], approval_body=(p.get('approval_body') or '').strip())
        _audit(user, 'assessment.profile_saved', institution, before=before,
               after={'institution_type': itype.code, 'autonomous_status': status, 'approval_bodies': bodies,
                      'programmes': [f"{p['programme_type']}: {p['name']}" for p in progs]})
    institution.refresh_from_db()
    return institution.benchmark_profile


# -- cycles ---------------------------------------------------------------------------

INCLUDED_BY_RESULT = {
    ApplicabilityRule.Result.APPLIES: True,
    ApplicabilityRule.Result.DOES_NOT_APPLY: False,
    ApplicabilityRule.Result.OPTIONAL: False,
    ApplicabilityRule.Result.REQUIRES_REVIEW: None,
}


def create_cycle(institution, user, name, opens_on, closes_on=None):
    release = current_release()
    if release is None:
        raise AssessmentError('No benchmark release has been published yet; a college can only be assessed '
                              'against a published release.')
    name = (name or '').strip()
    if not name:
        raise AssessmentError('Give the assessment a name, e.g. "AI readiness 2026-27".')
    opens = _date(opens_on, 'opens_on') or timezone.localdate()
    closes = _date(closes_on, 'closes_on')
    if closes and closes < opens:
        raise AssessmentError('closes_on must be after opens_on.')
    profile = profile_for(institution)
    items = (release.items.exclude(change_type=BenchmarkReleaseItem.ChangeType.RETIRED)
             .select_related('benchmark').order_by('benchmark__benchmark_code'))
    with transaction.atomic():
        cycle = AssessmentCycle.objects.create(
            institution=institution, name=name[:200], opens_on=opens, closes_on=closes, release=release,
            created_by=user, profile_snapshot={
                'institution_type': profile.institution_type, 'autonomous_status': profile.autonomous_status,
                'programme_types': sorted(profile.programme_types), 'approval_bodies': sorted(profile.approval_bodies),
                'jurisdiction': profile.jurisdiction})
        for item in items:
            d = evaluate_snapshot(item.snapshot.get('applicability_rules') or [], profile)
            ApplicableBenchmark.objects.create(
                cycle=cycle, benchmark=item.benchmark, release_item=item, applicability_result=d.result,
                applicability_reason={'result': d.result, 'reason': d.reason, 'rule': d.rule_id},
                included=INCLUDED_BY_RESULT.get(d.result))
        _audit(user, 'assessment.cycle_created', cycle,
               after={'institution': str(institution.pk), 'release': release.release_label,
                      'release_hash': release.content_hash, 'benchmarks': items.count()})
    return cycle


def decide_benchmark(ab, user, *, included=None, target_level=None, note=''):
    cycle = ab.cycle
    _require(cycle, Status.NOT_STARTED, Status.IN_PROGRESS)
    note = (note or '').strip()
    changes = {}
    if included is not None and included != ab.included:
        if cycle.status != Status.NOT_STARTED and ab.included and ab.evidence.exists():
            raise AssessmentError('Evidence has already been uploaded for this benchmark; it cannot be removed now.')
        engine = INCLUDED_BY_RESULT.get(ab.applicability_result)
        if engine is not None and included != engine and not note:
            raise AssessmentError('You are going against the applicability rules; add a note saying why.')
        changes['included'] = [ab.included, included]
        ab.included = included
        ab.selected_by = ApplicableBenchmark.SelectedBy.REVIEWER
    if target_level is not None and target_level != ab.target_level:
        if target_level not in LEVELS.values:
            raise AssessmentError(f'target_level must be one of {LEVELS.values}.')
        changes['target_level'] = [ab.target_level, target_level]
        ab.target_level = target_level
    if not changes:
        return ab
    ab.decision_note = note or ab.decision_note
    ab.save()
    _audit(user, 'assessment.benchmark_decided', ab, after={'benchmark': ab.benchmark.benchmark_code, **changes},
           reason=note)
    return ab


def open_cycle(cycle, user):
    _require(cycle, Status.NOT_STARTED)
    undecided = list(cycle.benchmarks.filter(included__isnull=True).values_list('benchmark__benchmark_code', flat=True))
    if undecided:
        raise AssessmentError('Decide whether these benchmarks apply first.', [f'{c}: requires review' for c in undecided])
    if not cycle.benchmarks.filter(included=True).exists():
        raise AssessmentError('No benchmark applies to this college; nothing to ask evidence for.')
    cycle.status = Status.IN_PROGRESS
    cycle.save(update_fields=['status'])
    _audit(user, 'assessment.cycle_opened', cycle)


def submit_cycle(cycle, user):
    _require(cycle, Status.IN_PROGRESS)
    if not EvidenceItem.objects.filter(cycle=cycle).exists():
        raise AssessmentError('Upload at least one piece of evidence before submitting.')
    cycle.status = Status.SUBMITTED
    cycle.save(update_fields=['status'])
    _audit(user, 'assessment.cycle_submitted', cycle)


def return_cycle(cycle, user, note):
    _require(cycle, Status.SUBMITTED, Status.REVIEWED)
    if not (note or '').strip():
        raise AssessmentError('Say what the college needs to add or fix.')
    cycle.status = Status.IN_PROGRESS
    cycle.save(update_fields=['status'])
    _audit(user, 'assessment.cycle_returned', cycle, reason=note.strip())


# -- evidence ------------------------------------------------------------------------

def rule_key(rule):
    return f"{rule.get('level') or 'any'}|{rule['evidence_type']}|{rule['title']}"


def evidence_requests(ab):
    """The release's evidence rules for this benchmark, each with the evidence submitted for it."""
    items = list(ab.evidence.select_related('evidence_type', 'submitted_by').prefetch_related('reviews__reviewer'))
    types = dict(EvidenceType.objects.values_list('code', 'name'))
    out = []
    for rule in ab.snapshot.get('evidence_rules') or []:
        key = rule_key(rule)
        out.append({**rule, 'key': key, 'evidence_type_name': types.get(rule['evidence_type'], rule['evidence_type']),
                    'items': [i for i in items if i.rule_key == key]})
    order = {'L3': 0, 'L2': 1, 'L1': 2, '': -1}
    return sorted(out, key=lambda r: (order.get(r.get('level') or '', 3), r['title']))


def submit_evidence(ab, user, data, upload=None):
    cycle = ab.cycle
    _require(cycle, Status.IN_PROGRESS)
    if not ab.included:
        raise AssessmentError('This benchmark is not part of the assessment.')
    rules = {rule_key(r): r for r in ab.snapshot.get('evidence_rules') or []}
    rule = rules.get(data.get('rule_key') or '')
    if rule is None:
        raise AssessmentError('Choose which evidence request this answers.')
    title = (data.get('title') or '').strip()
    url = (data.get('source_url') or '').strip()
    if not title:
        raise AssessmentError('Give the evidence a title.')
    sprint_doc = None
    if data.get('sprint_document'):
        from apps.documents.models import Document
        sprint_doc = Document.objects.filter(pk=data['sprint_document'],
                                             sprint__institution_id=cycle.institution_id).first()
        if sprint_doc is None or not sprint_doc.file:
            raise AssessmentError('That audit document was not found for this college.')
    if upload is None and not url and sprint_doc is None:
        raise AssessmentError('Attach a file, give a link, or choose a document from an audit sprint.')
    if url and not url.lower().startswith(('https://', 'http://')):
        raise AssessmentError('The link must start with https://')
    issued, valid = _date(data.get('issued_on'), 'issued_on'), _date(data.get('valid_until'), 'valid_until')
    if issued and issued > timezone.localdate():
        raise AssessmentError('issued_on cannot be in the future.')
    item = EvidenceItem(cycle=cycle, applicable=ab, rule_key=rule_key(rule), title=title[:300],
                        evidence_type=EvidenceType.objects.get(code=rule['evidence_type']),
                        description=(data.get('description') or '').strip(), source_url=url[:1000],
                        issued_on=issued, valid_until=valid, submitted_by=user, sprint_document=sprint_doc)
    if sprint_doc is not None and upload is None:
        item.original_filename = (sprint_doc.original_filename or sprint_doc.title or 'document')[:255]
        item.file_sha256 = sprint_doc.checksum or ''
    if upload is not None:
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in ALLOWED_EXT:
            raise AssessmentError(f'File type {ext or "(none)"} is not accepted; use {", ".join(sorted(ALLOWED_EXT))}.')
        if upload.size > MAX_FILE_BYTES:
            raise AssessmentError('Files must be 25 MB or smaller.')
        sha = hashlib.sha256()
        for chunk in upload.chunks():
            sha.update(chunk)
        upload.seek(0)
        item.file, item.original_filename, item.file_sha256 = upload, upload.name[:255], sha.hexdigest()
    item.save()
    _audit(user, 'assessment.evidence_submitted', item,
           after={'benchmark': ab.benchmark.benchmark_code, 'request': item.rule_key, 'sha256': item.file_sha256,
                  'url': item.source_url, 'sprint_document': str(sprint_doc.pk) if sprint_doc else None})
    return item


def review_evidence(item, user, data):
    _require(item.cycle, Status.IN_PROGRESS, Status.SUBMITTED, Status.REVIEWED)
    if item.submitted_by_id == user.pk:
        raise AssessmentError('Evidence must be reviewed by someone other than the person who uploaded it.')
    decision = data.get('decision')
    if decision not in EvidenceReview.Decision.values:
        raise AssessmentError(f'decision must be one of {EvidenceReview.Decision.values}.')
    notes = (data.get('notes') or '').strip()
    if decision != EvidenceReview.Decision.ACCEPTED and not notes:
        raise AssessmentError('Tell the college why, so they can fix it.')
    scores = {}
    for f in ('relevance', 'completeness', 'currency', 'authenticity', 'scope'):
        v = _pct(data.get(f'{f}_score'), f'{f}_score')
        if v is None:
            raise AssessmentError(f'{f}_score is needed (0-100).')
        scores[f'{f}_score'] = v
    with transaction.atomic():
        review = EvidenceReview.objects.create(item=item, reviewer=user, decision=decision, notes=notes, **scores)
        before = item.status
        item.status = decision
        item.save(update_fields=['status'])
        _audit(user, 'assessment.evidence_reviewed', item, before={'status': before},
               after={'status': decision, **{k: str(v) for k, v in scores.items()}}, reason=notes)
    return review


# -- scoring -------------------------------------------------------------------------

def _latest_review(item):
    return next(iter(item.reviews.all()), None)  # ordered newest first


def _counts(item, rule, ref):
    """(counted?, why not)."""
    if item.status != EvidenceItem.Status.ACCEPTED:
        return False, f'not accepted ({item.get_status_display().lower()})'
    if item.valid_until and item.valid_until < ref:
        return False, f'expired on {item.valid_until}'
    months = rule.get('minimum_currency_months')
    if months:
        if not item.issued_on:
            return False, 'issue date missing (needed to check it is recent)'
        if item.issued_on < _months_before(ref, months):
            return False, f'older than {months} months'
    return True, ''


def compute(ab, assessment=None):
    """All four scores for one applicable benchmark, with the reasons. Pure: saves nothing."""
    snap = ab.snapshot
    ref = ab.cycle.opens_on
    rules = snap.get('evidence_rules') or []
    items = list(ab.evidence.prefetch_related('reviews'))
    rows, counted_items = [], {}
    for rule in rules:
        key = rule_key(rule)
        n, notes = 0, []
        for item in (i for i in items if i.rule_key == key):
            ok, why = _counts(item, rule, ref)
            if ok:
                n += 1
                counted_items[item.pk] = item
            else:
                notes.append(f'"{item.title}": {why}')
        rows.append({'key': key, 'level': rule.get('level') or '', 'title': rule['title'], 'mandatory': rule['mandatory'],
                     'minimum_count': rule['minimum_count'], 'counted': n, 'met': n >= rule['minimum_count'],
                     'notes': notes})

    level, level_notes = '', []
    for lv in LEVEL_ORDER:
        needed = [r for r in rows if r['mandatory'] and r['level'] in (lv, '')]
        if not needed:
            level_notes.append(f'{lv}: no mandatory evidence request in the release, so it cannot be shown.')
            break
        missing = [r['title'] for r in needed if not r['met']]
        if missing:
            level_notes.append(f'{lv} not reached: missing ' + '; '.join(missing))
            break
        level = lv
    override = assessment.level_override if assessment else ''
    final_level = override or level
    manual = bool(final_level and (snap.get('levels') or {}).get(final_level, {}).get('requires_manual_review')
                  and not override)

    if snap.get('kind') == 'proposed':
        compliance, compliance_why = None, 'InGage-proposed benchmark: there is no legal or accreditation requirement.'
    else:
        base = [r for r in rows if r['mandatory'] and r['level'] in ('L3', '')]
        if base:
            met = sum(r['met'] for r in base)
            compliance = (Decimal(100) * met / len(base)).quantize(CENT)
            compliance_why = f'{met} of {len(base)} mandatory foundational (L3) evidence requests met.'
        else:
            compliance, compliance_why = None, 'No mandatory foundational (L3) evidence request in the release.'

    qualities = [r.quality() for r in (_latest_review(i) for i in counted_items.values()) if r is not None]
    confidence = (sum(qualities) / len(qualities)).quantize(CENT) if qualities else Decimal('0.00')
    confidence_why = (f'Average review quality of {len(qualities)} accepted, current piece(s) of evidence.'
                      if qualities else 'No accepted, current evidence yet.')

    outcome = assessment.outcome_score if assessment else None
    scores = {'compliance': compliance, 'maturity': MATURITY_POINTS[final_level], 'evidence_confidence': confidence,
              'outcome': outcome}

    composite, composite_why, model, weights = None, '', ScoringModel.objects.filter(active=True).first(), {}
    rule = BenchmarkScoreRule.objects.filter(benchmark=ab.benchmark, scoring_model=model).first() if model else None
    if model is None:
        composite_why = 'No active scoring model.'
    elif rule is None:
        composite_why = f'The benchmark owner has not approved weights for {model.code} yet.'
    else:
        weights = {k: str(v) for k, v in rule.weights().items()}
        missing = [k for k, w in rule.weights().items() if w > 0 and scores[k] is None]
        if missing:
            composite_why = 'Waiting for: ' + ', '.join(m.replace('_', ' ') for m in missing) + '.'
        else:
            composite = sum((w * (scores[k] or 0) for k, w in rule.weights().items()), Decimal(0)).quantize(CENT)
            composite_why = ' + '.join(f'{w} x {k.replace("_", " ")}' for k, w in rule.weights().items() if w > 0)
    return {
        'computed_level': level, 'current_level': final_level, 'scores': scores, 'composite': composite,
        'model': model if rule else None, 'weights': weights,
        'detail': {'method': SCORING_METHOD, 'reference_date': str(ref), 'requests': rows, 'level_notes': level_notes,
                   'level_override': override, 'needs_assessor_confirmation': manual,
                   'compliance': compliance_why, 'maturity': f'Level reached: {final_level or "none"}'
                   + (' (set by the assessor)' if override else ''),
                   'evidence_confidence': confidence_why,
                   'outcome': 'Entered by the assessor.' if outcome is not None else 'Not assessed yet.',
                   'composite': composite_why},
    }


def _save_scores(ab, user):
    a, _ = BenchmarkAssessment.objects.get_or_create(applicable=ab)
    r = compute(ab, a)
    s = r['scores']
    a.computed_level, a.current_level = r['computed_level'], r['current_level']
    a.compliance_score, a.maturity_score = s['compliance'], s['maturity']
    a.evidence_confidence_score, a.outcome_score = s['evidence_confidence'], s['outcome']
    a.composite_score, a.scoring_model, a.weights, a.detail = r['composite'], r['model'], r['weights'], r['detail']
    a.scored_at, a.scored_by = timezone.now(), user
    a.save()
    return a


def score_cycle(cycle, user):
    _require(cycle, Status.SUBMITTED, Status.REVIEWED)
    waiting = EvidenceItem.objects.filter(cycle=cycle, status=EvidenceItem.Status.SUBMITTED).count()
    if waiting:
        raise AssessmentError(f'{waiting} piece(s) of evidence are still waiting for review.')
    with transaction.atomic():
        done = [_save_scores(ab, user) for ab in cycle.benchmarks.filter(included=True).select_related('release_item', 'benchmark')]
        cycle.status = Status.REVIEWED
        cycle.save(update_fields=['status'])
        _audit(user, 'assessment.cycle_scored', cycle, after={'benchmarks': len(done), 'method': SCORING_METHOD})
    return done


def update_assessment(ab, user, data):
    _require(ab.cycle, Status.SUBMITTED, Status.REVIEWED)
    a, _ = BenchmarkAssessment.objects.get_or_create(applicable=ab)
    before = {'outcome_score': str(a.outcome_score), 'level_override': a.level_override}
    if 'outcome_score' in data:
        a.outcome_score = _pct(data.get('outcome_score'), 'outcome_score')
        a.outcome_note = (data.get('outcome_note') or '').strip()
        if a.outcome_score is not None and not a.outcome_note:
            raise AssessmentError('Say which measured result the outcome score is based on.')
    if 'level_override' in data:
        lv = (data.get('level_override') or '').upper()
        if lv and lv not in LEVELS.values:
            raise AssessmentError(f'level_override must be one of {LEVELS.values} or empty.')
        a.level_override, a.override_note = lv, (data.get('override_note') or '').strip()
        if lv and not a.override_note:
            raise AssessmentError('Explain why the level differs from what the evidence shows.')
    if 'assessor_notes' in data:
        a.assessor_notes = (data.get('assessor_notes') or '').strip()
    a.save()
    _audit(user, 'assessment.assessor_input', a, before=before,
           after={'outcome_score': str(a.outcome_score), 'level_override': a.level_override},
           reason=a.outcome_note or a.override_note)
    if ab.cycle.status == Status.REVIEWED:
        _save_scores(ab, user)  # keep the scorecard in step
    return a


def finalize_cycle(cycle, user):
    _require(cycle, Status.REVIEWED)
    problems = []
    last_review = EvidenceReview.objects.filter(item__cycle=cycle).aggregate(t=Max('reviewed_at'))['t']
    for ab in cycle.benchmarks.filter(included=True).select_related('benchmark'):
        a = getattr(ab, 'assessment', None)
        if a is None or a.scored_at is None:
            problems.append(f'{ab.benchmark.benchmark_code}: not scored')
        elif last_review and a.scored_at < last_review:
            problems.append(f'{ab.benchmark.benchmark_code}: evidence reviewed after scoring; score again')
        elif a.detail.get('needs_assessor_confirmation'):
            problems.append(f'{ab.benchmark.benchmark_code}: level {a.current_level} needs the assessor to confirm it')
    if problems:
        raise AssessmentError('Not ready to finalize.', problems)
    cycle.status, cycle.finalized_by, cycle.finalized_at = Status.FINALIZED, user, timezone.now()
    cycle.save(update_fields=['status', 'finalized_by', 'finalized_at'])
    _audit(user, 'assessment.cycle_finalized', cycle, after={'release': cycle.release.release_label})


# -- weights ---------------------------------------------------------------------------

def set_score_rule(benchmark, user, data):
    model = ScoringModel.objects.filter(active=True).first()
    if model is None:
        raise AssessmentError('No active scoring model.')
    w = {}
    for f in ('compliance', 'maturity', 'evidence', 'outcome'):
        try:
            w[f] = Decimal(str(data.get(f'{f}_weight'))).quantize(Decimal('0.0001'))
        except InvalidOperation:
            raise AssessmentError(f'{f}_weight must be a number from 0 to 1.')
        if not 0 <= w[f] <= 1:
            raise AssessmentError(f'{f}_weight must be from 0 to 1.')
    if sum(w.values()) != 1:
        raise AssessmentError(f'The four weights must add up to 1 (they add up to {sum(w.values())}).')
    note = (data.get('note') or '').strip()
    if not note:
        raise AssessmentError('Record who approved these weights and why (e.g. "Approved by the benchmark owner").')
    rule, _ = BenchmarkScoreRule.objects.update_or_create(
        benchmark=benchmark, scoring_model=model,
        defaults={'compliance_weight': w['compliance'], 'maturity_weight': w['maturity'], 'evidence_weight': w['evidence'],
                  'outcome_weight': w['outcome'], 'approved_by': user, 'approved_at': timezone.now(), 'note': note})
    _audit(user, 'assessment.weights_set', rule, after={'benchmark': benchmark.benchmark_code, 'model': model.code,
                                                        **{k: str(v) for k, v in w.items()}}, reason=note)
    return rule
