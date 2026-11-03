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
        original_doc = f.original_source_document or f.document or f.source_document
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
    """Project review controls onto the exact excerpts, without copying quotations.

    Source passages are supplied separately. The frozen ledger remains the local
    validation authority; this packet contains current dispositions and references.
    """
    if not ledger:
        return None
    from apps.facts.verification.grounding import parse_pages
    from .evaluation import _normal
    pages = {}
    for source in sources:
        pages.setdefault((source['document_id'], source['page_number']), []).append(source)

    def references(source):
        quote = _normal(source.get('quote') or '')
        refs = []
        for page in parse_pages(source.get('page', '')):
            for window in pages.get((source.get('document_id'), page), []):
                text = _normal(window['text'])
                # Include boundary-straddling quotes if an exact substantial
                # fragment is present. This is selection, never quote validation.
                touches = quote and (quote in text or text in quote or any(
                    quote[i:i + 64] in text for i in range(0, max(0, len(quote) - 63), 32)))
                if touches:
                    refs.append({'source_id': window['id'], 'text_offset': window.get('text_offset', 0)})
        return refs

    selected = {}
    for claim in ledger['claims']:
        current_refs, original_refs = references(claim['source']), references(claim['original_source'])
        if current_refs or original_refs:
            selected[claim['id']] = (claim, current_refs, original_refs)
    # Keep every alternative of an applicable conflict, including rejected or
    # off-window alternatives; do not present them as citable source passages.
    issues = [i for i in ledger['issues'] if i['kind'] == 'conflict'
              and set(selected).intersection(i['claim_ids'])]
    alternatives = {cid for issue in issues for cid in issue['claim_ids']}
    for claim in ledger['claims']:
        if claim['id'] in alternatives and claim['id'] not in selected:
            selected[claim['id']] = (claim, [], [])

    def citation(source, refs):
        return {k: source[k] for k in ('document_id', 'version', 'page', 'current') if k in source} | {
            'passages': refs, 'source_support_in_selected_passages': bool(refs)}

    claims = []
    for claim, current_refs, original_refs in selected.values():
        decisions = [d for d in claim['decisions'] if d['action'] in ('confirmed', 'corrected', 'rejected')]
        decision = decisions[-1:]  # the effective disposition, not tagging/assignment history
        row = {k: claim[k] for k in ('id', 'attribute', 'label', 'value', 'kind', 'disposition', 'verification')}
        row['scope'] = {k: v for k, v in claim['scope'].items() if k not in ('stated', 'sources')}
        row['source'] = citation(claim['source'], current_refs)
        row['decisions'] = [{k: d[k] for k in ('id', 'actor_id', 'timestamp', 'action', 'rationale')}
                            for d in decision]
        if claim['disposition'] == 'corrected':
            row['original_value'] = claim['original_value']
            row['original_source'] = citation(claim['original_source'], original_refs)
        claims.append(row)
    batch = ledger.get('review_batch')
    answers = []
    if batch:
        for case in batch['cases']:
            decision = batch['decisions'].get(case['id'])
            ids = sorted(set(case['fact_ids']).intersection(selected))
            if decision and (ids or case.get('kind') == 'identity'):
                answers.append({'id': decision['id'], 'claim_ids': ids, 'action': decision['action'],
                                'rationale': decision.get('rationale', '')})
    return {'version': 'review-context-2', 'claims': claims,
            'issues': [{k: i[k] for k in ('id', 'kind', 'status', 'claim_ids', 'rationale')} for i in issues],
            'review_answers': answers,
            'instruction': 'Passage references point to the separately supplied sources. Records with no selected passage support are review context, not quotations or automatic capability credit.'}


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
