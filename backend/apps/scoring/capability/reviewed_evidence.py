"""Versioned review ledger; dispositions never stand in for rubric judgements.

All database reads occur while storage freezes the evidence boundary. The payload
contains no synthetic PDF quotations. Current and original citations are distinct.
"""
import re

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


def for_context(ledger, sources, diagnostics=None, aliases=None):
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
        key = (source['document_id'], source['page_number'])
        pages.setdefault(key, []).append(source)
        # A deduplicated page also stands for its identical dropped copies (structure.page_aliases).
        for alias in (aliases or {}).get(key, ()):
            pages.setdefault(alias, []).append(source)

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
                guarded_value = claim.get('original_value') if corrected else claim.get('value')
                if not blocked and not (corrected and unresolved_conflict) and _independent_count(text, quote, guarded_value):
                    continue
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


def _independent_count(citation, claim_quote, guarded_value):
    """Allow a neighbouring count only when the guarded number is identifiable."""
    preceding, found, _ = claim_quote.partition(citation)
    if not found or not preceding or not preceding[-1].isspace():
        return False
    conjunction = r'(?:and|while|whereas)'
    if not (re.match(conjunction + r'\s', citation, re.IGNORECASE)
            or re.search(r'\b' + conjunction + r'\s+$', preceding, re.IGNORECASE)):
        return False
    value = re.fullmatch(r'(?:more than |at least |over )?(\d+(?:,\d{3})*)',
                         str(guarded_value).strip(), re.IGNORECASE)
    if not value:
        return False
    number = value.group(1).replace(',', '')
    counts = lambda text: {n.replace(',', '') for n in re.findall(r'\d+(?:,\d{3})*', text)}
    cited_counts = counts(citation)
    return number in counts(preceding) and bool(cited_counts) and number not in cited_counts


# ---- Extracted-evidence lane -----------------------------------------------------------------------------------
# Extraction finds AI evidence (an AI programme's approved intake, faculty funded for an ML conference, an AI patent)
# that keyword and semantic retrieval often miss, because the page shares few words with the rubric condition. On the
# VISTAS full corpus 66 of 101 extracted AI items never reached the judge. This lane adds the source page of each
# relevant extracted AI item to the indicator's packet, within a fixed budget, so the judge can cite it.
LANE_VERSION = 'extracted-evidence-lane-1'
LANE_CHARS = 18000
LANE_WINDOW = 2400
LANE_MAX_ITEMS = 14
_LANE_STOP = frozenset('''institution institutional college university students student faculty there their with that
from have been this number total during year years department identified relevant assessed scope records record
evidence least defined documented demonstrates demonstrate supports supported available within least each
artificial intelligence machine learning based using used about which where'''.split())


def _lane_tokens(text):
    import re
    return {t[:7] for t in re.findall(r'[a-z]{4,}', str(text or '').lower()) if t not in _LANE_STOP}


#: Kinds of extracted AI evidence and the indicators that judge them. Accreditation records describe evidence in
#: their own words ("placements", "approved intake", "patent filed"), which rarely share words with the rubric.
LANE_FAMILIES = (
    (r'patent|publication|journal|research|funded project|grant', ('C7.1', 'C7.3', 'C4.3')),
    (r'intake|programme|program\b|b\.?\s?tech|b\.?\s?sc|m\.?\s?tech|bca|mca|degree|speciali[sz]ation|syllabus|'
     r'curriculum|course|unit\b|elective|textbook', ('C3.1', 'C5.2', 'C3.2', 'C5.1')),
    (r'examination|pass percentage|result|graduat', ('C3.1', 'C5.2')),
    (r'fdp|faculty development|faculty.{0,40}(?:conference|workshop|training|seminar|course)|'
     r'(?:conference|workshop|training|seminar).{0,40}faculty', ('C4.1', 'C4.2')),
    (r'placement|internship|recruit|career|employ|hiring', ('C5.4', 'C8.3')),
    (r'incubat|start-?up|venture|seed fund|entrepreneur|innovation', ('C7.2', 'C7.3')),
    (r'\blab\b|laborator|centre|center|gpu|comput(?:ing|er)', ('C6.1', 'C6.4')),
    (r'mou|partner|collaborat|industry|company', ('C8.2', 'C7.4')),
    (r'student.{0,40}project|project.{0,40}student|hackathon|competition', ('C3.4', 'C5.3')),
    (r'policy|guideline|ethic|responsible', ('C2.1',)),
)


def lane_relevance(claim, indicator):
    """How strongly an extracted item belongs to an indicator: 10 when its kind of evidence is judged there
    (LANE_FAMILIES), plus the shared-word count with the indicator's name and condition texts (seven-letter stems).
    Two or more qualifies. A deliberately simple, inspectable rule."""
    import re
    text = ' '.join(str(claim.get(k) or '') for k in ('label', 'attribute', 'value')).replace('_', ' ')
    quote = str((claim.get('source') or {}).get('quote') or '')
    area = indicator.get('code', '').replace('AIQIF-', '')
    family = any(area in areas and re.search(pattern, text, re.I) for pattern, areas in LANE_FAMILIES)
    target = _lane_tokens(indicator.get('name', '') + ' ' + ' '.join(c['text'] for c in indicator.get('conditions', [])))
    return (10 if family else 0) + len(_lane_tokens(text + ' ' + quote) & target)


def evidence_lane(indicator, context, sources, ledger, *, budget=LANE_CHARS):
    """(context with added windows, audit). Never removes or reorders retrieved windows."""
    from apps.facts.verification.grounding import parse_pages
    from .evaluation import _normal
    audit = {'version': LANE_VERSION, 'budget_chars': budget, 'added': [], 'already_in_packet': 0, 'considered': 0}
    if not ledger:
        return context, audit
    by_page = {}
    for source in sources:
        by_page.setdefault((source['document_id'], source['page_number']), source)
    present = {(w['document_id'], w['page_number']) for w in context}
    scored = []
    for claim in ledger.get('claims', []):
        src = claim.get('source') or {}
        if claim.get('kind') != 'ai_evidence' or claim.get('disposition') == 'rejected' or not src.get('document_id') \
                or src.get('current') is False:
            continue
        score = lane_relevance(claim, indicator)
        if score >= 2:
            scored.append((-score, claim['id'], claim))
    scored.sort(key=lambda row: row[:2])
    audit['considered'] = len(scored)
    used, added = 0, []
    for _, _, claim in scored[:LANE_MAX_ITEMS]:
        src = claim['source']
        for page in parse_pages(src.get('page', ''))[:2]:
            key = (src['document_id'], page)
            source = by_page.get(key)
            if source is None:
                continue
            if key in present:
                audit['already_in_packet'] += 1
                continue
            text = source['text']
            start = 0
            if len(text) > LANE_WINDOW:
                probe = _normal(src.get('quote') or '')[:40]
                hit = text.find(probe) if probe else -1
                start = max(0, min(hit - LANE_WINDOW // 3, len(text) - LANE_WINDOW)) if hit >= 0 else 0
            window = text[start:start + LANE_WINDOW]
            if used + len(window) > budget:
                break
            context.append({**{k: v for k, v in source.items() if k not in ('text', 'report_timestamp')},
                            'text': window, 'text_offset': start, 'evidence_role': 'extracted_evidence'})
            present.add(key)
            used += len(window)
            added.append({'claim_id': claim['id'], 'document_id': src['document_id'], 'page': page,
                          'chars': len(window)})
    audit['added'], audit['used_chars'] = added, used
    return context, audit
