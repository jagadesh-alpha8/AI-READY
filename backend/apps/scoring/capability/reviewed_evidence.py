"""Versioned review ledger; dispositions never stand in for rubric judgements.

All database reads occur while storage freezes the evidence boundary. The payload
contains no synthetic PDF quotations. Current and original citations are distinct.
"""
from apps.facts.models import ExtractedFact
from apps.facts.verification.scope import read_scope
from apps.gaps.models import GapItem

VERSION = 'reviewed-evidence-1'


def snapshot(sprint):
    claims, live = [], []
    for f in ExtractedFact.objects.filter(sprint=sprint).select_related(
            'source_document', 'document', 'original_source_document').prefetch_related('review_history').order_by('id'):
        live.append(f)
        doc = f.source_document or f.document
        # A malformed foreign citation never widens the tenant boundary.
        valid_doc = doc is not None and doc.sprint_id == sprint.pk
        history = [{'id': str(h.pk), 'actor_id': str(h.user_id) if h.user_id else None,
                    'timestamp': h.created_at.isoformat(), 'action': h.action,
                    'decision_source': h.decision_source or 'person', 'before': h.original_value,
                    'after': h.new_value, 'rationale': h.reason, 'details': h.details}
                   for h in sorted(f.review_history.all(), key=lambda h: (h.created_at, str(h.pk)))]
        original_doc = f.original_source_document or f.document
        original_valid = original_doc is not None and original_doc.sprint_id == sprint.pk
        first_review = next(iter(history), {})
        claims.append({'id': str(f.pk), 'revision': f.updated_at.isoformat(),
            'institution_id': str(sprint.institution_id), 'sprint_id': str(sprint.pk),
            'attribute': f.field_key, 'label': f.field_name, 'value': f.value,
            'original_value': f.original_value if f.original_value is not None else first_review.get('before'), 'value_origin': f.value_origin,
            'scope': {**read_scope(f), 'stated': f.scope}, 'kind': f.fact_kind,
            'verification': {'outcome': f.verification_status, 'grounding': f.grounding_status,
                             'validation': f.validation_status, 'automation': f.automation_decision},
            'disposition': f.status, 'source': {
                'document_id': str(doc.pk) if valid_doc else None,
                'version': doc.version_number if valid_doc else None,
                'current': bool(valid_doc and doc.superseded_at is None and doc.status != 'rejected'),
                'page': f.source_page, 'quote': f.source_snippet if valid_doc else ''},
            'original_source': {'document_id': str(original_doc.pk) if original_valid else None,
                                'page': f.original_source_page or f.source_page,
                                'quote': (f.original_source_snippet or f.source_snippet) if original_valid else ''},
            'decisions': history})
    issues = []
    for g in GapItem.objects.filter(sprint=sprint).prefetch_related('events').order_by('id'):
        ids = [str(x) for x in (g.source_fact_id, g.conflict_fact_b_id) if x]
        own = {c['id'] for c in claims}
        issues.append({'id': str(g.pk), 'revision': g.updated_at.isoformat(), 'kind': g.gap_type,
            'status': g.status, 'claim_ids': [x for x in ids if x in own],
            'rationale': g.resolution, 'title': g.title,
            'alternatives_at_detection': [g.conflict_value_a, g.conflict_value_b],
            'actor_id': str(g.resolved_by_id) if g.resolved_by_id else None,
            'timestamp': g.resolved_at.isoformat() if g.resolved_at else None,
            'events': [{'id': str(e.pk), 'action': e.action, 'rationale': e.note,
                        'actor_id': str(e.user_id) if e.user_id else None,
                        'timestamp': e.created_at.isoformat(), 'details': e.data} for e in g.events.all()]})
    # Reconcile the current corpus too: new evidence can challenge an older
    # resolution even before the extraction pipeline has emitted a new gap.
    from apps.facts.verification.conflicts import disagreements
    by_field = {}
    for fact in live:
        by_field.setdefault(fact.field_key.casefold(), []).append(fact)
    recorded_sets = {frozenset(i['claim_ids']) for i in issues if i['status'] != 'resolved'}
    for rows in by_field.values():
        for group in disagreements(rows):
            ids = sorted(str(f.pk) for f in group)
            if frozenset(ids) not in recorded_sets:
                issues.append({'id': 'corpus-conflict:' + ':'.join(ids), 'kind': 'conflict', 'status': 'open',
                    'claim_ids': ids, 'rationale': 'Current comparable source alternatives disagree. New or changed contradictory evidence requires a fresh scoped resolution.',
                    'prior_resolutions': [i['id'] for i in issues if i['status'] == 'resolved' and set(ids).intersection(i['claim_ids'])]})
    from apps.facts.models import ReviewBatch
    batch = ReviewBatch.objects.filter(sprint=sprint).first()
    return {'version': VERSION, 'claims': claims, 'issues': issues,
            'review_batch': {'id': str(batch.pk), 'cases': batch.cases, 'decisions': batch.decisions}
                            if batch else None}


def for_context(ledger, sources):
    """Bound by selected pages; keep complete decision provenance for those claims."""
    if not ledger:
        return None
    from apps.facts.verification.grounding import parse_pages
    pages = {(s['document_id'], s['page_number']) for s in sources}
    def selected(source):
        return any((source['document_id'], p) in pages for p in parse_pages(source['page']))
    claims = [{**c, 'decisions': c['decisions'][-3:]} for c in ledger['claims']
              if selected(c['source']) or selected(c['original_source'])]
    ids = {c['id'] for c in claims}
    batch = ledger.get('review_batch')
    if batch:
        cases = [{k: c[k] for k in ('id', 'question', 'scope', 'fact_ids', 'affected_requirements', 'initial')}
                 for c in batch['cases'] if c.get('kind') == 'identity' or ids.intersection(c['fact_ids'])]
        case_ids = {c['id'] for c in cases}
        batch = {'id': batch['id'], 'cases': cases,
                 'decisions': {k: d for k, d in batch['decisions'].items() if k in case_ids},
                 'overflow_total': sum(not c['initial'] for c in ledger['review_batch']['cases'])}
    return {**ledger, 'claims': claims, 'review_batch': batch,
            'issues': [{k: v for k, v in i.items() if k != 'events'} for i in ledger['issues']
                       if ids.intersection(i['claim_ids'])]}


def citation_issue(citations, ledger, sources, state=None):
    """Fail closed on a citation reusing an explicitly rejected/changed alternative.

    Whole-page citations overlapping rejected text are also withheld. Independent
    quotations on that page remain usable. This guard is deliberately conservative;
    semantics and applicability still belong to the evaluator.
    """
    if not ledger:
        return ''
    from .evaluation import _normal
    from apps.facts.verification.grounding import parse_pages
    by_id = {s['id']: s for s in sources}
    unresolved = {cid for i in ledger.get('issues', []) if i['kind'] == 'conflict' and i['status'] != 'resolved' for cid in i['claim_ids']}
    for claim in ledger['claims']:
        unresolved_conflict = state in ('met', 'not_met') and claim['id'] in unresolved
        blocked = claim['disposition'] in ('rejected', 'evidence_requested')
        corrected = claim['disposition'] == 'corrected'
        if not (blocked or corrected or unresolved_conflict):
            continue
        source = claim['original_source'] if corrected else claim['source']
        quote = _normal(source.get('quote') or '')
        if not quote:
            continue
        for cite in citations:
            page = by_id.get(cite.get('source_id'), {})
            text = _normal(cite.get('quote') or '')
            if (page.get('document_id') == source['document_id']
                    and page.get('page_number') in parse_pages(source['page'])
                    and text and (quote in text or text in quote)):
                current = claim['source']
                if (corrected and not unresolved_conflict and current['document_id'] == page.get('document_id')
                        and page.get('page_number') in parse_pages(current['page'])
                        and _normal(current.get('quote') or '') and _normal(current['quote']) in text
                        and claim['verification']['grounding'] in ('exact', 'ocr_variant')
                        and claim['verification']['validation'] != 'fail'):
                    continue
                # A correction preserving the citation and value can still use it.
                if corrected and not unresolved_conflict and claim['value'] == claim['original_value']:
                    continue
                return 'Citation reuses a rejected or superseded claim; independent supporting evidence is required.'
    return ''
