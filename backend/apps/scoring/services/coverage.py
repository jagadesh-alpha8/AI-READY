"""AI-QIF evidence coverage and the coverage-adjusted CRI (formula AIQIF-COV-1).

The Raw CRI (cri_engine) scores the evidence a sprint has. It says nothing about how much of
the framework that evidence reaches: a college with three strong facts in one criterion can
score well. Coverage measures that reach, over the 36 AI-QIF key indicators:

    coverage              = covered applicable indicator weight / total applicable indicator weight
    coverage-adjusted CRI = Raw CRI x coverage

Rules (all deterministic -- no AI decides anything here):

- Applicable: every indicator of an active CRI pillar, except those the published benchmark
  release's applicability rules say explicitly do NOT apply to this college's benchmark profile.
  "requires review" (no rules, no profile, no published release, indicator not in the release)
  stays applicable and is reported as unresolved -- it never shrinks the denominator.
  "optional" stays applicable too (it is not "not applicable").
- Covered: at least one tag that counts (apps/facts/aiqif_tagging.counting_q): the fact is AI
  evidence and confirmed/corrected, the relationship is Direct or Supporting, and the tag was
  accepted -- automatically (NAAC crosswalk, or a confident AI tag of the fact's own criterion) or
  by a Super Admin -- and never rejected. Contextual links, context and profile facts, and tags
  waiting in the expert queue do not count. Distinct indicators: two facts on one indicator count
  it once; one fact may cover several indicators.
- Provisional: while the sprint's expert queue is not empty the coverage is marked provisional
  (`provisional`, `expert_queue`); a baseline cannot be decided until it is empty.
- Weights: the published release's approved key-indicator weights, when the release carries one
  for every indicator considered; otherwise equal weights within each criterion times the
  approved CRI pillar weight (scoring.Pillar.weight). No weight is invented.
"""
from decimal import Decimal, InvalidOperation

from apps.facts.models import ExtractedFact, FactAIQIFMapping

from ..constants import AIQIF_INDICATORS, COVERAGE_FORMULA_VERSION

FORMULA = ('Coverage-adjusted CRI = Raw CRI x (covered applicable AI-QIF indicator weight / '
           'total applicable AI-QIF indicator weight)')

APPLIES, OPTIONAL, REQUIRES_REVIEW, DOES_NOT_APPLY = 'applies', 'optional', 'requires_review', 'does_not_apply'


def _number(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return float(number) if number.is_finite() and number >= 0 else None


def _release_items():
    """(release, {indicator_code: release item snapshot}) of the current published release."""
    from apps.benchmarks.models import BenchmarkReleaseItem
    from apps.benchmarks.services.releases import current_release

    release = current_release()
    if release is None:
        return None, {}
    items = release.items.exclude(change_type=BenchmarkReleaseItem.ChangeType.RETIRED)
    return release, {(item.snapshot or {}).get('benchmark_code'): item.snapshot or {} for item in items}


def _profile(institution):
    from apps.assessments.services import AssessmentError, profile_for
    try:
        return profile_for(institution)
    except AssessmentError:
        return None


def _applicability(codes, release, items, profile):
    """{code: (result, reason)} and a sprint-level note when nothing could be resolved."""
    from apps.benchmarks.services.applicability import evaluate_snapshot

    if release is None:
        note = 'No benchmark release is published yet, so applicability is unresolved for every indicator.'
        return {c: (REQUIRES_REVIEW, 'No published benchmark release.') for c in codes}, note
    if profile is None:
        note = ('This college has no benchmark profile (type, status, programmes), so applicability is '
                'unresolved for every indicator.')
        return {c: (REQUIRES_REVIEW, 'No benchmark profile for this college.') for c in codes}, note
    out = {}
    for code in codes:
        snapshot = items.get(code)
        if snapshot is None:
            out[code] = (REQUIRES_REVIEW, f'Not in release {release.release_label}.')
            continue
        decision = evaluate_snapshot(snapshot.get('applicability_rules') or [], profile)
        out[code] = (decision.result, decision.reason)
    return out, ''


def _weights(codes, items, pillar_weights):
    """({code: weight}, source, note)."""
    release_weights = {code: _number((items.get(code) or {}).get('weight')) for code in codes}
    if codes and all(w is not None for w in release_weights.values()):
        return release_weights, 'release', 'Approved key-indicator weights of the published benchmark release.'
    per_criterion = {}
    for code in codes:
        per_criterion.setdefault(AIQIF_INDICATORS[code][0], []).append(code)
    weights = {}
    for criterion, members in per_criterion.items():
        for code in members:
            weights[code] = pillar_weights[criterion] / len(members)
    note = ('Equal weights within each criterion x the approved CRI pillar weight (the published release does '
            'not carry an approved weight for every indicator).')
    return weights, 'equal_within_criterion', note


def compute_coverage(sprint, pillars):
    """The coverage block stored on a ScoringRun (`evidence_coverage`). `pillars` are the active
    scoring.Pillar rows the run used."""
    pillar_weights = {p.key: float(p.weight) for p in pillars}
    codes = [code for code, (criterion, _name) in AIQIF_INDICATORS.items() if criterion in pillar_weights]

    release, items = _release_items()
    profile = _profile(sprint.institution) if release is not None else None
    applicability, applicability_note = _applicability(codes, release, items, profile)
    weights, weights_source, weights_note = _weights(codes, items, pillar_weights)

    from apps.facts.aiqif_tagging import counting_q, queue_counts, queued_tags_q

    verified = (FactAIQIFMapping.objects.filter(counting_q(), fact__sprint=sprint)
                .values_list('indicator_code', 'fact_id'))
    facts_by_code = {}
    for code, fact_id in verified:
        facts_by_code.setdefault(code, set()).add(str(fact_id))
    awaiting_review = (FactAIQIFMapping.objects
                       .filter(queued_tags_q(), fact__sprint=sprint,
                               fact__status__in=[ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED])
                       .count())
    queue = queue_counts(sprint)

    rows = []
    for code in codes:
        result, reason = applicability[code]
        applicable = result != DOES_NOT_APPLY
        fact_ids = sorted(facts_by_code.get(code, ()))
        rows.append({
            'code': code, 'criterion': AIQIF_INDICATORS[code][0], 'name': AIQIF_INDICATORS[code][1],
            'applicability': result, 'applicability_reason': reason, 'applicable': applicable,
            'weight': round(weights[code], 6), 'covered': applicable and bool(fact_ids), 'fact_ids': fact_ids,
        })

    applicable_rows = [r for r in rows if r['applicable']]
    applicable_weight = sum(r['weight'] for r in applicable_rows)
    covered_weight = sum(r['weight'] for r in applicable_rows if r['covered'])
    ratio = round(covered_weight / applicable_weight, 6) if applicable_weight > 0 else None
    covered = sum(1 for r in applicable_rows if r['covered'])
    unresolved = sum(1 for r in applicable_rows if r['applicability'] == REQUIRES_REVIEW)
    if ratio is None:
        status = 'no_applicable_indicators'
    elif covered == len(applicable_rows) and not unresolved:
        status = 'complete'
    else:
        status = 'incomplete'

    return {
        'formula_version': COVERAGE_FORMULA_VERSION,
        'formula': FORMULA,
        'status': status,
        'ratio': ratio,
        'covered_count': covered,
        'applicable_count': len(applicable_rows),
        'excluded_count': len(rows) - len(applicable_rows),
        'unresolved_applicability_count': unresolved,
        'provisional': queue['total'] > 0,
        'expert_queue': queue,
        'covered_weight': round(covered_weight, 6),
        'applicable_weight': round(applicable_weight, 6),
        'weights_source': weights_source,
        'weights_note': weights_note,
        'release_label': release.release_label if release else None,
        'release_hash': release.content_hash if release else None,
        'applicability_note': applicability_note,
        'mappings_awaiting_review': awaiting_review,
        'indicators': rows,
    }


def adjusted_cri(raw_cri, coverage):
    """Raw CRI x coverage ratio, or None when there is no applicable indicator weight."""
    ratio = coverage.get('ratio')
    return None if ratio is None else round(raw_cri * ratio, 2)
