"""The shared fact-verification pipeline: one entry point for every way a fact value arrives.

    verify_fact(fact, source=...)            # a stored fact (extraction, re-verification, conflict refresh)
    verify_snapshot(snapshot, ...)           # any value + citation (an evidence submission, a correction proposal,
                                             #   the original extraction of a reviewed fact in the shadow report)
    process_document(document, pages=...)    # end of extraction: verify the document's facts, apply the policy

Steps (each recorded with whether it is deterministic or AI-assisted):

1. Keep the value and citation exactly as given (FactVerification.value / citation snapshot).
2. Citation: the cited document version exists in the fact's sprint and the cited page is inside it.
3. Quote: the quoted text is on that page (grounding.match_quote -- OCR-tolerant for letters, exact for numbers).
4. Normalize the value for comparison (normalize.comparable_value) -- the stored value is never rewritten.
5. Type-specific deterministic validation (validators.py) and, for a calculated value, the arithmetic and the
   grounding of every input (derived.py).
6. Cross-source: other facts of the same field in the sprint, compared only when their period, population, unit
   and categories are compatible (scope.py); an open conflict gap counts as disagreement.
7. Outcome + reason: verified | needs_review | invalid | conflicting.

Outcome rules (deterministic, in this order):
- invalid      -- a check proves the value wrong as recorded: missing / out-of-range citation, the value
                  contradicts its own quote, a failed validation, a failed calculation;
- conflicting  -- a comparable source states a different value, or an open conflict names this fact;
- verified     -- citation ok, quote found, value stated by the quote (or a passing calculation), no failed or
                  warning validation, no disagreement;
- needs_review -- anything else (quote not found or not checkable, value not in the quote, a warning, ...).

AI confidence is recorded as `extraction_confidence` and never changes the outcome.
"""
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.facts.models import ExtractedFact, FactReviewHistory, FactVerification

from . import derived, grounding, normalize, policy, precedent as precedent_mod, scope as scope_mod, validators

logger = logging.getLogger(__name__)

#: Bumped whenever the rules here change, so a stored verification says which rules produced it.
POLICY_VERSION = 'fact-verification/1'


@dataclass
class Snapshot:
    """A value and its citation, independent of where it came from."""
    sprint_id: object
    field_key: str
    field_name: str
    value: object
    data_type: str
    source_document: object = None
    source_page: str = ''
    source_snippet: str = ''
    normalized_value: object = None
    confidence_score: float | None = None
    extraction_method: str = ''
    fact_kind: str = ''
    derivation: dict = field(default_factory=dict)
    scope: dict = field(default_factory=dict)
    fact_id: object = None
    document: object = None
    status: str = 'extracted'

    @classmethod
    def of(cls, fact, **overrides):
        values = dict(
            sprint_id=fact.sprint_id, field_key=fact.field_key, field_name=fact.field_name, value=fact.value,
            data_type=fact.data_type, source_document=fact.source_document or fact.document,
            source_page=fact.source_page, source_snippet=fact.source_snippet,
            normalized_value=fact.normalized_value, confidence_score=fact.confidence_score,
            extraction_method=fact.extraction_method, fact_kind=fact.fact_kind, derivation=fact.derivation or {},
            scope=fact.scope or {}, fact_id=fact.pk, document=fact.document, status=fact.status)
        values.update(overrides)
        return cls(**values)


@dataclass
class VerificationResult:
    outcome: str
    reason: str
    reasons: list
    grounding: dict
    validation: dict
    derivation: dict
    cross_source: dict
    scope: dict
    risk_level: str
    risk_reason: str
    extraction_confidence: float | None
    passed_summary: list
    ai_assessments: list = field(default_factory=list)

    def as_dict(self):
        return {'outcome': self.outcome, 'reason': self.reason, 'reasons': self.reasons,
                'extraction_confidence': self.extraction_confidence, 'grounding': self.grounding,
                'validation': self.validation, 'derivation': self.derivation, 'cross_source': self.cross_source,
                'scope': self.scope, 'risk_level': self.risk_level, 'risk_reason': self.risk_reason,
                'ai_assessments': self.ai_assessments}


# -- the pipeline ---------------------------------------------------------------------------------------

def _documents_for(derivation, sprint_id):
    from apps.documents.models import Document
    ids = {str(i.get('document_id')) for i in (derivation or {}).get('inputs') or [] if i.get('document_id')}
    if not ids:
        return {}
    return {str(d.id): d for d in Document.objects.filter(pk__in=ids, sprint_id=sprint_id)}


def cross_source(snapshot, fact_scope, *, exclude_ids=()):
    """Compare with the sprint's other facts of the same field. {'status': agrees|disagrees|not_comparable|
    no_other_source|in_open_conflict, 'compared': [...], 'not_comparable': [...], 'kind': 'deterministic'}"""
    from apps.gaps.models import GapItem
    out = {'status': 'no_other_source', 'compared': [], 'not_comparable': [], 'kind': 'deterministic'}
    if not snapshot.sprint_id or not snapshot.field_key:
        return out
    others = (ExtractedFact.objects.filter(sprint_id=snapshot.sprint_id, field_key__iexact=snapshot.field_key)
              .exclude(status=ExtractedFact.Status.REJECTED).exclude(pk__in=[i for i in exclude_ids if i])
              .select_related('source_document', 'document'))
    if snapshot.fact_id:
        others = others.exclude(pk=snapshot.fact_id)
    lineage = set(precedent_mod._lineage(snapshot.document)) if snapshot.document is not None else set()
    disagree = False
    for other in others[:50]:
        doc = other.source_document or other.document
        # An earlier version of the same file is history, not a second source.
        if doc is not None and (doc.pk in lineage and doc.pk != getattr(snapshot.document, 'pk', None)):
            continue
        if doc is not None and doc.superseded_at is not None:
            continue
        other_scope = scope_mod.read_scope(other)
        ok, why = scope_mod.comparable(fact_scope, other_scope)
        row = {'fact_id': str(other.id), 'value': other.value, 'status': other.status,
               'document': doc.original_filename if doc else None,
               'document_version': doc.version_number if doc else None, 'page': other.source_page,
               'period': other_scope.get('period') or None}
        if not ok:
            out['not_comparable'].append({**row, 'why': why})
            continue
        row['agrees'] = normalize.same_value(snapshot.value, other.value, snapshot.data_type)
        row['unknown_scope'] = scope_mod.unknown_parts(fact_scope, other_scope)
        out['compared'].append(row)
        disagree = disagree or not row['agrees']
    if snapshot.fact_id and GapItem.objects.filter(
            gap_type=GapItem.GapType.CONFLICT, status__in=GapItem.ACTIVE_STATUSES).filter(
            _conflict_q(snapshot.fact_id)).exists():
        out['status'] = 'in_open_conflict'
    elif disagree:
        out['status'] = 'disagrees'
    elif out['compared']:
        out['status'] = 'agrees'
    elif out['not_comparable']:
        out['status'] = 'not_comparable'
    return out


def _conflict_q(fact_id):
    from django.db.models import Q
    return Q(source_fact_id=fact_id) | Q(conflict_fact_b_id=fact_id)


def verify_snapshot(snapshot, *, provided_pages=None, exclude_ids=()):
    """Run the pipeline on one value + citation. Pure: reads the database, writes nothing."""
    reasons, passed = [], []
    documents = _documents_for(snapshot.derivation, snapshot.sprint_id)
    page_map = {}
    if provided_pages and snapshot.source_document is not None:
        page_map = provided_pages.get(str(snapshot.source_document.pk)) or {}
    fact_scope = scope_mod.read_scope(snapshot, stated=snapshot.scope)

    calc = derived.check_derivation(snapshot.derivation, value=snapshot.value, data_type=snapshot.data_type,
                                    sprint_id=snapshot.sprint_id, fact_scope=fact_scope, documents=documents,
                                    provided_pages=provided_pages, default_document=snapshot.source_document)
    derivation_ok = calc['status'] == 'pass'
    g = grounding.ground(sprint_id=snapshot.sprint_id, document=snapshot.source_document,
                         source_page=snapshot.source_page, snippet=snapshot.source_snippet, value=snapshot.value,
                         data_type=snapshot.data_type, provided_pages=page_map, derivation_ok=derivation_ok,
                         input_numbers=[i.get('value') for i in (snapshot.derivation or {}).get('inputs') or []])
    checks = validators.validate(snapshot.value, snapshot, {'derivation_ok': derivation_ok})
    if snapshot.derivation:
        checks.append(validators.check(
            'arithmetic', 'Calculation', 'pass' if derivation_ok else 'fail',
            f'{calc.get("formula") or "?"} = {normalize.format_number(calc.get("computed"))}'
            + ('' if derivation_ok else ' -- ' + '; '.join(calc.get('detail') or ['see the inputs'])))
                      | {'formula': calc.get('formula'), 'inputs': calc.get('inputs')})
    validation = {'status': validators.summarize(checks), 'checks': checks, 'kind': 'deterministic'}
    xs = cross_source(snapshot, fact_scope, exclude_ids=exclude_ids)
    risk, risk_reason = policy.risk_level(snapshot, snapshot.derivation)

    # -- outcome --------------------------------------------------------------------------------------
    invalid = []
    if g.citation in ('page_missing', 'wrong_sprint'):
        invalid += g.detail[:1]
    if g.value_support == 'conflicts_quote':
        invalid.append(next((d for d in g.detail if 'contradicts' in d), 'The value contradicts its own quote.'))
    invalid += [f'{c["label"]}: {c["detail"]}' for c in checks if c['status'] == 'fail']
    if invalid:
        outcome, reasons = 'invalid', invalid
    elif xs['status'] in ('disagrees', 'in_open_conflict'):
        outcome = 'conflicting'
        if xs['status'] == 'in_open_conflict':
            reasons = ['An open conflict names this fact; a person decides which value is right.']
        else:
            other = next(r for r in xs['compared'] if not r['agrees'])
            reasons = [f'{other["document"] or "Another document"}'
                       + (f' v{other["document_version"]}' if other.get('document_version') else '')
                       + (f', page {other["page"]}' if other.get('page') else '')
                       + f' states {other["value"]!r} for the same metric.']
    else:
        review = []
        if g.citation == 'document_missing':
            review.append('No source document is cited, so the value cannot be checked against one.')
        if g.citation == 'no_page':
            review.append('No page number is cited.')
        if g.quote not in ('exact', 'ocr_variant'):
            review += [d for d in g.detail if 'quote' in d.lower()][:1] or [f'Quote check: {g.quote}.']
        if g.value_support == 'not_in_quote':
            review.append('The quote does not state this value.')
        elif g.value_support == 'not_checkable':
            review.append('The value cannot be matched word for word against its quote (a judgement).')
        review += [f'{c["label"]}: {c["detail"]}' for c in checks if c['status'] == 'warn']
        if snapshot.derivation and not derivation_ok:
            review += calc.get('detail') or []
        outcome = 'needs_review' if review else 'verified'
        reasons = review
    if outcome == 'verified':
        doc = snapshot.source_document
        passed = [f'quote found on page {snapshot.source_page} of {doc.original_filename or "the document"} '
                  f'v{doc.version_number}' + (' (OCR differences)' if g.quote == 'ocr_variant' else ''),
                  'value stated by the quote' if not snapshot.derivation else f'calculation {calc["formula"]} checks out',
                  f'{sum(1 for c in checks if c["status"] == "pass")} validation check(s) passed',
                  {'agrees': 'agrees with other sources', 'no_other_source': 'no other source for this field',
                   'not_comparable': 'other sources measure something else'}.get(xs['status'], xs['status'])]
    reason = reasons[0] if reasons else 'All required checks passed.'
    return VerificationResult(
        outcome=outcome, reason=reason, reasons=reasons, grounding=g.as_dict(), validation=validation,
        derivation=calc if snapshot.derivation else {}, cross_source=xs, scope=fact_scope, risk_level=risk,
        risk_reason=risk_reason, extraction_confidence=snapshot.confidence_score, passed_summary=passed)


# -- stored facts -----------------------------------------------------------------------------------

def _citation(snapshot):
    doc = snapshot.source_document
    return {'document_id': str(doc.pk) if doc else None, 'document_name': doc.original_filename if doc else None,
            'document_version': doc.version_number if doc else None, 'source_page': snapshot.source_page,
            'source_snippet': snapshot.source_snippet}


def verify_fact(fact, *, source=FactVerification.Source.REVERIFY, provided_pages=None, apply_policy=False,
                current_mode=None):
    """Verify a stored fact, record the run, update its summary fields and -- when `apply_policy` -- let the
    automation policy decide it (policy.mode(): shadow records what it would do; enforce confirms)."""
    from apps.facts.evidence_requests import open_request_for
    snapshot = Snapshot.of(fact)
    result = verify_snapshot(snapshot, provided_pages=provided_pages)
    prec = precedent_mod.find(fact, result.scope) if fact.status == ExtractedFact.Status.EXTRACTED else None
    decision = policy.decide(fact, result, precedent=prec, has_open_request=bool(open_request_for(fact)),
                             current_mode=current_mode) if apply_policy else policy.Decision(
        'not_applicable' if fact.status != ExtractedFact.Status.EXTRACTED else 'review',
        'Recorded only; the policy was not applied on this run.')
    now = timezone.now()
    run = FactVerification.objects.create(
        fact=fact, sprint_id=fact.sprint_id, source=source, mode=current_mode or policy.mode(),
        outcome=result.outcome, reason=result.reason, reasons=result.reasons, value=fact.value,
        citation=_citation(snapshot),
        extraction_confidence=fact.confidence_score, grounding=result.grounding, validation=result.validation,
        derivation=result.derivation, cross_source=result.cross_source, scope=result.scope,
        risk_level=result.risk_level, precedent=prec, automation_decision=decision.action,
        automation_reason=decision.reason, blockers=decision.blockers, policy_version=POLICY_VERSION)
    summary = dict(verification_status=result.outcome, grounding_status=result.grounding['status'],
                   validation_status=result.validation['status'], cross_source_status=result.cross_source['status'],
                   risk_level=result.risk_level, automation_decision=decision.action,
                   automation_reason=decision.reason, verified_at=now)
    ExtractedFact.objects.filter(pk=fact.pk).update(**summary)
    for name, value in summary.items():
        setattr(fact, name, value)
    if decision.action in ('auto_verified', 'precedent'):
        _auto_confirm(fact, run, decision, prec)
    return run


def _auto_confirm(fact, run, decision, prec):
    """Confirm as the system account -- only if still unreviewed at this moment (a person may have acted)."""
    from apps.facts.auto_confirm import system_user
    from apps.gaps.services import resolve_unconfirmed_fact_gap
    user = system_user()
    via_precedent = decision.action == 'precedent'
    with transaction.atomic():
        updated = ExtractedFact.objects.filter(pk=fact.pk, status=ExtractedFact.Status.EXTRACTED).update(
            status=ExtractedFact.Status.CONFIRMED, reviewed_by=user, reviewed_at=timezone.now(),
            updated_at=timezone.now())
        if not updated:
            return False
        FactReviewHistory.objects.create(
            fact=fact, action=FactReviewHistory.Action.CONFIRMED, original_value=fact.value, user=user,
            decision_source=(FactReviewHistory.DecisionSource.PRECEDENT if via_precedent
                             else FactReviewHistory.DecisionSource.RULE),
            reason=('Auto-verified (earlier reviewer decision): ' if via_precedent else 'Auto-verified: ')
            + decision.reason,
            details={'verification_id': str(run.id), 'policy_version': POLICY_VERSION, 'risk_level': run.risk_level,
                     'grounding': run.grounding.get('status'), 'validation': run.validation.get('status'),
                     'cross_source': run.cross_source.get('status'),
                     **({'precedent': prec} if via_precedent else {})})
        fact.refresh_from_db()
        resolve_unconfirmed_fact_gap(fact, user=user)
    return True


def process_document(document, *, pages=None, job=None):
    """End of extraction: verify every unreviewed fact of the document and apply the automation policy.
    Reviewed facts are verified for display only -- never changed. Returns {'verified': n, 'auto': n, ...}."""
    provided = {}
    if pages:
        provided[str(document.pk)] = {p['page_number']: p.get('text') or '' for p in pages.get('pages') or []
                                      if p.get('page_number') is not None}
    counts = {'checked': 0, 'auto_verified': 0, 'precedent': 0, 'would_auto_verify': 0, 'would_precedent': 0,
              'review': 0, 'outcomes': {}}
    for fact in document.extracted_facts.select_related('source_document', 'document', 'sprint').exclude(
            status=ExtractedFact.Status.REJECTED):
        try:
            run = verify_fact(fact, source=FactVerification.Source.EXTRACTION, provided_pages=provided,
                              apply_policy=fact.status == ExtractedFact.Status.EXTRACTED)
        except Exception:  # never fail an extraction because one fact could not be verified
            logger.exception('verification.fact_failed fact_id=%s', fact.id)
            continue
        counts['checked'] += 1
        counts['outcomes'][run.outcome] = counts['outcomes'].get(run.outcome, 0) + 1
        if run.automation_decision in counts:
            counts[run.automation_decision] += 1
    logger.info('verification.document document_id=%s %s', document.id, counts)
    return counts


def verify_evidence_link(link):
    """Deterministic check of an evidence submission's AI assessment: is its quote on the stated page of the
    submitted document, and does it state the suggested value? Stored on the link; decides nothing."""
    fact = link.request.fact
    pages = {}
    for row in link.source_pages or []:
        if row.get('page_number') is not None:
            pages[int(row['page_number'])] = row.get('text') or ''
    value = link.analysis_suggested_value if link.analysis_suggested_value is not None else fact.value
    if not link.document_id:
        quote = link.analysis_quote or ''
        found = bool(quote) and f' {" ".join(normalize.tokens(quote))} ' in f' {" ".join(normalize.tokens(link.submitted_text))} '
        support, _, _ = grounding.value_support(value, fact.data_type, quote)
        return {'kind': 'deterministic', 'quote': 'exact' if found else ('no_quote' if not quote else 'not_found'),
                'value_support': support, 'status': 'ok' if found and support == 'in_quote' else 'check',
                'detail': [] if found else ['The quoted text is not in the submitted text.']}
    snapshot = Snapshot(sprint_id=link.request.sprint_id, field_key=fact.field_key, field_name=fact.field_name,
                        value=value, data_type=fact.data_type, source_document=link.document,
                        source_page=str(link.analysis_page_number or link.source_page or ''),
                        source_snippet=link.analysis_quote or link.source_snippet, fact_id=fact.pk,
                        document=link.document, status=fact.status)
    result = verify_snapshot(snapshot, provided_pages={str(link.document_id): pages} if pages else None)
    return {**result.grounding, 'outcome': result.outcome, 'reason': result.reason,
            'validation': result.validation['status'],
            'cross_source': result.cross_source['status'], 'note': 'Advisory: the reviewer decides.'}
