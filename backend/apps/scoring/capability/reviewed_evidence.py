"""Versioned review ledger; dispositions never stand in for rubric judgements.

All database reads occur while storage freezes the evidence boundary. The payload
contains no synthetic PDF quotations. Current and original citations are distinct.
"""
from apps.facts.models import ExtractedFact
from apps.facts.verification.scope import read_scope
from apps.gaps.models import GapItem

VERSION = 'reviewed-evidence-2'


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
                             'validation': f.validation_status, 'automation': f.automation_decision,
                             'source_review_required': f.source_review_required},
            'disposition': f.status, 'source': {
                'document_id': str(doc.pk) if valid_doc else None,
                'version': doc.version_number if valid_doc else None,
                'current': bool(valid_doc and doc.superseded_at is None and doc.status != 'rejected'),
                'page': f.source_page, 'quote': f.source_snippet if valid_doc else ''},
            'original_source': {'document_id': str(original_doc.pk) if original_valid else None,
                                'page': f.original_source_page or f.source_page,
                                'quote': (f.original_source_snippet or f.source_snippet) if original_valid else ''},
            'decisions': history})
    from apps.facts.verification.conflicts import disagreements
    live_by_id = {str(f.pk): f for f in live}
    issues = []
    for g in GapItem.objects.filter(sprint=sprint).prefetch_related('events').order_by('id'):
        ids = [str(x) for x in (g.source_fact_id, g.conflict_fact_b_id) if x]
        own = {c['id'] for c in claims}
        comparison = {}
        if g.gap_type == 'conflict':
            # Field-wide gaps often record only one representative. Reconstruct
            # every current alternative, as the conflict-review UI does.
            linked = ([live_by_id[cid] for cid in ids if cid in live_by_id] if g.conflict_fact_b_id
                      else [f for f in live if str(g.source_fact_id) in live_by_id and
                            f.field_key.casefold() == live_by_id[str(g.source_fact_id)].field_key.casefold()])
            ids = sorted(str(f.pk) for f in linked)
            active = sorted({str(f.pk) for group in disagreements(linked) for f in group})
            comparison = {'comparison_status': 'current_disagreement' if active else 'no_current_disagreement',
                          'active_conflict_claim_ids': active}
        issues.append({'id': str(g.pk), 'revision': g.updated_at.isoformat(), 'kind': g.gap_type,
            'status': g.status, 'claim_ids': [x for x in ids if x in own],
            'rationale': g.resolution, 'title': g.title, **comparison,
            'alternatives_at_detection': [g.conflict_value_a, g.conflict_value_b],
            'actor_id': str(g.resolved_by_id) if g.resolved_by_id else None,
            'timestamp': g.resolved_at.isoformat() if g.resolved_at else None,
            'events': [{'id': str(e.pk), 'action': e.action, 'rationale': e.note,
                        'actor_id': str(e.user_id) if e.user_id else None,
                        'timestamp': e.created_at.isoformat(), 'details': e.data} for e in g.events.all()]})
    # Reconcile the current corpus too: new evidence can challenge an older
    # resolution even before the extraction pipeline has emitted a new gap.
    by_field = {}
    for fact in live:
        by_field.setdefault(fact.field_key.casefold(), []).append(fact)
    recorded_sets = {frozenset(i['claim_ids']) for i in issues if i['status'] != 'resolved'}
    for rows in by_field.values():
        for group in disagreements(rows):
            ids = sorted(str(f.pk) for f in group)
            if frozenset(ids) not in recorded_sets:
                issues.append({'id': 'corpus-conflict:' + ':'.join(ids), 'kind': 'conflict', 'status': 'open',
                    'claim_ids': ids, 'comparison_status': 'current_disagreement',
                    'active_conflict_claim_ids': ids, 'rationale': 'Current comparable source alternatives disagree. New or changed contradictory evidence requires a fresh scoped resolution.',
                    'prior_resolutions': [i['id'] for i in issues if i['status'] == 'resolved' and set(ids).intersection(i['claim_ids'])]})
    from apps.facts.models import ReviewBatch
    batch = ReviewBatch.objects.filter(sprint=sprint).first()
    return {'version': VERSION, 'claims': claims, 'issues': issues,
            'review_batch': {'id': str(batch.pk), 'cases': batch.cases, 'decisions': batch.decisions}
                            if batch else None}


def for_context(ledger, sources, diagnostics=None):
    """Project review controls onto the exact excerpts, without copying quotations.

    Source passages are supplied separately. The frozen ledger remains the local
    validation authority; this packet contains current dispositions and references.
    """
    if not ledger:
        if diagnostics is not None:
            diagnostics.update(version='review-attachment-audit-1', claims=[], issues=[])
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
    # Full alternatives stay in the frozen ledger and citation validator. The
    # model receives bounded representatives plus explicit omission summaries.
    issues = [i for i in ledger['issues'] if i['kind'] == 'conflict'
              and set(selected).intersection(i['claim_ids'])]
    alternatives = {cid for issue in issues for cid in issue['claim_ids']}
    candidates = sorted((c for c in ledger['claims'] if c['id'] in alternatives and c['id'] not in selected),
                        key=lambda c: (c['disposition'] not in ('rejected', 'corrected', 'evidence_requested'), c['id']))
    for claim in candidates[:4]:
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
    packet = bounded_packet(claims, issues, answers)
    if diagnostics is not None:
        sent = {c['id'] for c in packet['claims']}
        rows = []
        for claim in ledger['claims']:
            refs = selected.get(claim['id'])
            current_refs, original_refs = (refs[1], refs[2]) if refs else ([], [])
            attached = claim['id'] in sent
            if attached:
                reason = ('current_quote_overlap' if current_refs else 'original_quote_overlap'
                          if original_refs else 'conflict_alternative_context_only')
            elif refs:
                reason = 'bounded_packet_omission'
            elif claim['id'] in alternatives:
                reason = 'conflict_alternative_limit'
            else:
                reason = 'no_selected_quote_overlap'
            rows.append({'claim_id': claim['id'], 'attached': attached, 'reason': reason,
                'disposition': claim['disposition'], 'verification': claim['verification'],
                'source': claim['source'], 'original_source': claim['original_source'],
                'current_references': current_refs, 'original_references': original_refs,
                'scope': claim['scope']})
        diagnostics.update(version='review-attachment-audit-1', claims=rows,
            issues=[{'id': i['id'], 'kind': i['kind'], 'status': i['status'],
                     'claim_ids': i['claim_ids'], 'rationale': i.get('rationale', ''),
                     'selected_claim_ids': sorted(set(i['claim_ids']).intersection(selected)),
                     'sent_claim_ids': sorted(set(i['claim_ids']).intersection(sent))}
                    for i in ledger['issues'] if set(i['claim_ids']).intersection(selected)],
            note='Overlap attaches review controls; it does not establish assertion relevance, scope or satisfaction.')
    return packet


def bounded_packet(claims, issues, answers):
    """A fixed prompt budget, never a truncation of the validation authority.

    Omitted alternatives stay in run.inputs.reviewed_evidence; citation_issue
    always checks that complete ledger, including rejected and corrected claims.
    """
    import hashlib
    import json
    def clip(value, depth=0):
        if depth > 5:
            return '[context omitted]'
        if isinstance(value, str):
            return value if len(value) <= 512 else value[:480] + ' [context clipped]'
        if isinstance(value, dict):
            return {k: clip(v, depth + 1) for k, v in sorted(value.items())[:32]}
        if isinstance(value, list):
            return [clip(v, depth + 1) for v in value[:8]]
        return value
    ordered = sorted(claims, key=lambda c: (
        c['disposition'] not in ('rejected', 'corrected', 'evidence_requested'),
        not c['source']['source_support_in_selected_passages'], c['id']))
    rows = [clip(c) for c in ordered[:20]]
    # IDs and ref arrays are structural, not narrative. Preserve them verbatim.
    for row, original in zip(rows, ordered):
        row['id'] = original['id']
        row['source'] = original['source']
    def packet():
        sent = {c['id'] for c in rows}
        selected_issues = []
        for issue in issues:
            retained = [cid for cid in issue['claim_ids'] if cid in sent]
            if not retained:
                continue
            selected_issues.append({'id': issue['id'] if len(issue['id']) <= 200 else
                'conflict-digest:' + hashlib.sha256(issue['id'].encode()).hexdigest(),
                'kind': issue['kind'], 'status': issue['status'], 'claim_ids': retained,
                'rationale': clip(issue.get('rationale', '')),
                'alternative_count': len(issue['claim_ids']),
                'omitted_alternatives': len(issue['claim_ids']) - len(retained),
                **({'comparison_status': issue['comparison_status'],
                    'active_conflict_claim_ids': [cid for cid in retained if cid in issue.get('active_conflict_claim_ids', [])],
                    'active_alternative_count': len(issue.get('active_conflict_claim_ids', [])),
                    'omitted_active_alternatives': len(set(issue.get('active_conflict_claim_ids', [])) - set(retained))}
                   if 'comparison_status' in issue else {})})
            if len(selected_issues) == 8:
                break
        return {'version': 'review-context-4', 'claims': rows, 'issues': selected_issues,
            'review_answers': [clip(a) for a in answers[:8]],
            'omissions': {'matching_claims': max(0, len(claims) - len(rows)),
                          'applicable_issues': max(0, len(issues) - len(selected_issues)),
                          'full_ledger_retained_for_validation': True},
            'instruction': 'A stored conflict with no_current_disagreement is historical review context, not a current contradiction or proof of agreement. Only supplied passages are citable. This bounded packet may omit conflict alternatives and review details; omitted records do not establish agreement. Complete rejected, corrected and unresolved alternatives are enforced by local validation. Never award credit from review dispositions alone.'}
    result = packet()
    while len(json.dumps(result)) > 24000 and rows:
        rows.pop()
        result = packet()
    return result


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
    unresolved = {cid for i in ledger.get('issues', []) if i['kind'] == 'conflict' and i['status'] != 'resolved' for cid in i.get('active_conflict_claim_ids', i['claim_ids'])}
    for claim in ledger['claims']:
        unresolved_conflict = state in ('met', 'not_met') and claim['id'] in unresolved
        blocked = claim['disposition'] in ('rejected', 'evidence_requested') or claim.get('verification', {}).get('source_review_required', False)
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
