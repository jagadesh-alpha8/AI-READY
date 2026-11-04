"""Offline measurement of capability request construction; never a provider request.

Rebuilds each evaluation and recommendation request from frozen run inputs or a JSON
export, checks it against the saved input/request hashes and attributes its size to
named parts. Figures are labelled by provenance: `actual_*` comes from provider usage
telemetry, `estimated_*` from a stated calibration, `bound_*` from the application's
conservative reservation policy. Nothing here writes run history or changes a decision.

Saved runs are replayed with the construction that produced them (selected by the trace's
prompt version); `current_construction` measures what today's code sends for the same windows.
"""
import hashlib
import json
import math
import re
import statistics
from collections import Counter

from apps.extraction.services.openai_client import _JSON_INSTRUCTIONS
from .evaluation import SYSTEM_PROMPT, _normal, indicator_schema, select_context
from .reviewed_evidence import for_context
from .scope import context_scope
from .storage import digest

VERSION = 'capability-context-diagnostics-0.2'
# Mirrors evaluation.evaluate and provider.MeteredService.envelope. Measured, never changed here.
REVIEWED_EVIDENCE_ALLOWANCE = 32000
ENVELOPE_FRAMING_TOKENS = 4096
BLOCKED_PREFIXES = {
    'Reviewed-evidence context exceeds': 'not_evaluated:reviewed_evidence_allowance',
    'No readable source context': 'not_evaluated:no_readable_context',
    'Evaluation call budget reached': 'not_evaluated:call_budget',
    'Model evaluation failed': 'provider_failure',
}
# Heuristic only: an unknown whose stated reason turns on applicability rather than content.
SCOPE_OR_PERIOD = re.compile(r'(?i)\b(period|year|dated?|current(?:ly)?|currency|cohort|denominator|population|'
                             r'scope|identified (?:group|cohort|programme|faculty))\b')


# Lines AIQIF-EVAL-0.10 added to the system prompt. Removing them recovers 0.9; used only when the hash matches.
PROMPT_0_10_ADDITION = ('Review records reference the separately supplied source passages; do not treat values or\n'
                        'review rationales as quotations. Off-window conflict alternatives remain context only.\n')


def serialized(value):
    """Characters of a value as the evaluation payload serializes it (ASCII escapes, sorted keys)."""
    return len(value) if isinstance(value, str) else len(json.dumps(value, sort_keys=True))


def page_projection(ledger, sources):
    """Frozen copy of reviewed_evidence.for_context before AIQIF-EVAL-0.10, for replaying runs it produced.

    Every claim on a selected page, with its full record, quotations and last three decisions.
    """
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


PROJECTIONS = {'AIQIF-EVAL-0.9': page_projection}


def projection_for(prompt_version):
    return PROJECTIONS.get(prompt_version, for_context)


def balanced_windows_0_3(indicator, sources, max_chars=18000):
    """Frozen copy of evaluation.select_balanced_context at retrieval 'assertion-balanced-windows-0.3'.

    Word-presence ranking over half-overlapping 3,000-character windows, hints ignored. Kept to
    replay runs it produced and as the baseline when measuring retrieval changes.
    """
    from .evaluation import RETRIEVAL_TERMS
    sources = [{k: v for k, v in s.items() if k != 'retrieval_hints'} for s in sources]
    if len({s['id'] for s in sources}) != len(sources):
        raise ValueError('Source IDs must be unique.')
    if max_chars < 100:
        return []
    stop = set('the and for with that this from each institution institutional evidence documented '
               'identified stated explicit completed record records review relevant defined actual '
               'demonstrates demonstrate requirement has have are its an of to in or a'.split())
    def tokens(text):
        return set(t for t in re.findall(r'[a-z0-9]{2,}', text.lower()) if t not in stop)
    docs = [tokens(s['text']) for s in sources]
    frequency = Counter(t for words in docs for t in words)
    size = min(3000, max_chars)
    windows = []
    for source in sources:
        for offset in range(0, len(source['text']), max(1, size // 2)):
            excerpt = source['text'][offset:offset + size]
            if excerpt.strip():
                windows.append((source, offset, excerpt, tokens(excerpt)))
            if offset + size >= len(source['text']):
                break
    terms = tokens(RETRIEVAL_TERMS.get(indicator['code'], indicator['name']))
    queries = [tokens(c['text']) for c in indicator.get('conditions', [])] or [terms]
    def score(row, query):
        words = row[3]
        return sum((3 if t in query else 1) * (1 + math.log((len(sources) + 1) / (frequency[t] + 1)))
                   for t in (query | terms) & words)
    def ranked(query):
        return sorted(windows, key=lambda w: (-score(w, query), hashlib.sha256(w[0]['text'].encode()).hexdigest(), w[1]))
    chosen = {}
    for query in queries:
        ordered = ranked(query)
        if ordered:
            row = ordered[0]
            chosen.setdefault((row[0]['id'], row[1]), row)
    for row in ranked(set().union(*queries)):
        chosen.setdefault((row[0]['id'], row[1]), row)
    result, used = [], 0
    for source, offset, excerpt, _ in chosen.values():
        remaining = max_chars - used
        if remaining < 100:
            break
        text = excerpt[:remaining]
        result.append({**source, 'text': text, 'text_offset': offset})
        used += len(text)
    return result


RETRIEVALS = {'assertion-balanced-windows-0.3': balanced_windows_0_3}


def retrieval_for(retrieval_version):
    """The selector that produced a run's windows; today's select_context for current or unknown versions."""
    legacy = RETRIEVALS.get(retrieval_version)
    if legacy is None:
        return select_context
    return lambda indicator, sources, max_chars=18000: (
        legacy(indicator, sources, max_chars) if indicator.get('scoring_mode') == 'independent_conditions'
        else select_context(indicator, sources, max_chars))


def system_prompt_for(prompt_hash):
    """The system prompt text whose sha256 is `prompt_hash`, if this code can reproduce it."""
    for text in (SYSTEM_PROMPT, SYSTEM_PROMPT.replace(PROMPT_0_10_ADDITION, '')):
        if hashlib.sha256(text.encode()).hexdigest() == prompt_hash:
            return text
    return None


def evaluation_request(indicator, context, *, ledger, scope, population, reference_period, compatible_endpoint=True,
                       projection=for_context, system_prompt=SYSTEM_PROMPT):
    """The user payload, schema and instructions evaluate() builds for one indicator batch."""
    review = projection(ledger, context)
    scope_part = context_scope(scope, context)
    payload = json.dumps({'reviewed_evidence': review, 'indicator': indicator, 'population': population,
                          'reference_period': reference_period, 'scope': scope_part, 'sources': context}, sort_keys=True)
    schema = indicator_schema(indicator, context)
    system = system_prompt
    if compatible_endpoint:
        system += _JSON_INSTRUCTIONS.format(schema=json.dumps(schema, separators=(',', ':')))
    return {'indicator': indicator, 'context': context, 'review': review, 'scope': scope_part,
            'population': population, 'reference_period': reference_period, 'payload': payload,
            'schema': schema, 'schema_name': 'capability_conditions', 'system': system, 'base_prompt': system_prompt,
            'input_hash': hashlib.sha256(payload.encode()).hexdigest()}


def provider_kwargs(system, user, schema, schema_name, *, model, settings):
    """Request keyword arguments as MeteredService reserves and digests them (OpenAI-compatible path)."""
    kwargs = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
              'response_format': {'type': 'json_schema', 'json_schema': {'name': schema_name, 'schema': schema, 'strict': True}}}
    kwargs.update({k: settings[k] for k in ('temperature', 'seed', 'max_tokens', 'timeout') if k in settings})
    return kwargs


def envelope_input_bound(kwargs):
    return len(json.dumps(kwargs, ensure_ascii=False, default=str).encode()) + ENVELOPE_FRAMING_TOKENS


def gate(request, *, calls_before=0, max_calls=36):
    """Which pre-request limit, if any, stops this batch, in evaluate()'s own order."""
    review = request['review']
    measured = len(json.dumps(review)) if review else 0
    if review and measured > REVIEWED_EVIDENCE_ALLOWANCE:
        return 'reviewed_evidence_allowance', measured
    if not request['context']:
        return 'no_readable_context', measured
    if calls_before >= max_calls:
        return 'call_budget', measured
    return None, measured


def _side(claim, side):
    return claim.get(side) or {}


def components(request):
    """Serialized characters per request part. User-message parts sum with `user_framing` to the payload.

    Reads both packet formats: page projection (quotations, review cases) and excerpt-scoped
    `review-context-2` (passage references, review answers, packet instruction).
    """
    review = request['review'] or {}
    claims = review.get('claims', [])
    issues = review.get('issues', [])
    current = sum(serialized(_side(c, 'source').get('quote') or '') for c in claims)
    original = sum(serialized(_side(c, 'original_source').get('quote') or '') for c in claims)
    references = sum(serialized(_side(c, side)['passages']) for c in claims for side in ('source', 'original_source')
                     if 'passages' in _side(c, side))
    history = sum(serialized(c.get('decisions', [])) for c in claims)
    user = {
        'rubric_indicator': serialized(request['indicator']),
        'population_and_period': serialized(request['population']) + serialized(request['reference_period']),
        'scope': serialized(request['scope']),
        'source_passages': serialized(request['context']),
        'current_quotations': current,
        'original_quotations': original,
        'passage_references': references,
        'review_history': history,
        'claim_records': serialized(claims) - current - original - references - history if claims else 0,
        'conflicts': serialized([i for i in issues if i['kind'] == 'conflict']) if issues else 0,
        'other_issues': serialized([i for i in issues if i['kind'] != 'conflict']) if issues else 0,
        'case_details': (serialized(review['review_batch']) if review.get('review_batch') else 0)
                        + (serialized(review['review_answers']) if review.get('review_answers') else 0),
        'packet_instruction': serialized(review['instruction']) if review.get('instruction') else 0,
    }
    user['user_framing'] = len(request['payload']) - sum(user.values())
    response_format = {'type': 'json_schema', 'json_schema': {'name': request['schema_name'], 'schema': request['schema'], 'strict': True}}
    base = len(request['base_prompt'])
    return {'instructions': base, 'schema_in_instructions': len(request['system']) - base,
            'response_schema': serialized(response_format), **user}


def repetition(request):
    """Repeated information inside one request (behaviour 2), in serialized characters."""
    claims = (request['review'] or {}).get('claims', [])
    windows = [_normal(s['text']) for s in request['context']]
    same_original = [c for c in claims if _side(c, 'original_source').get('quote')
                     and _side(c, 'original_source').get('quote') == _side(c, 'source').get('quote')
                     and str(_side(c, 'original_source').get('page')) == str(_side(c, 'source').get('page'))]
    in_window = [c for c in claims if _normal(_side(c, 'source').get('quote') or '')
                 and any(_normal(c['source']['quote']) in w for w in windows)]
    quotes = Counter(_normal(c['source']['quote']) for c in claims if _side(c, 'source').get('quote'))
    records = Counter(json.dumps({k: v for k, v in c.items() if k not in ('id', 'revision', 'decisions')}, sort_keys=True)
                      for c in claims)
    quote_size = {q: serialized(q) for q in quotes}
    return {
        'original_quotation_equals_current': len(same_original),
        'original_quotation_equals_current_chars': sum(serialized(c['original_source']['quote']) for c in same_original),
        'current_quotation_inside_supplied_window': len(in_window),
        'current_quotation_inside_supplied_window_chars': sum(serialized(c['source']['quote']) for c in in_window),
        'repeated_quotations': sum(n - 1 for n in quotes.values() if n > 1),
        'repeated_quotation_chars': sum((n - 1) * quote_size[q] for q, n in quotes.items() if n > 1),
        'duplicate_claim_records': sum(n - 1 for n in records.values() if n > 1),
        'duplicate_claim_record_chars': sum((n - 1) * len(k) for k, n in records.items() if n > 1),
        'unchanged_original_value': sum(c.get('original_value', c['value']) == c['value'] for c in claims),
    }


def anchoring(request):
    """Claims supported by a supplied window versus those included without such support (behaviour 1).

    Excerpt-scoped packets state support as passage references. For page-projected packets support
    is exact normalized quotation containment, so OCR variants count as unsupported there.
    `unsupported_conflict_alternatives` are unsupported claims an included conflict names.
    """
    review = request['review'] or {}
    claims = review.get('claims', [])
    from apps.facts.verification.grounding import parse_pages
    windows = {}
    for s in request['context']:
        windows.setdefault((s['document_id'], s['page_number']), []).append(_normal(s['text']))
    def anchored(claim):
        sides = [_side(claim, 'source'), _side(claim, 'original_source')]
        if any('passages' in s for s in sides):
            return any(s.get('passages') for s in sides)
        for source in sides:
            quote = _normal(source.get('quote') or '')
            if quote and any(quote in w for p in parse_pages(source.get('page'))
                             for w in windows.get((source.get('document_id'), p), [])):
                return True
        return False
    page_only = [c for c in claims if not anchored(c)]
    ids = {c['id'] for c in page_only}
    kept = {c['id'] for c in claims} - ids
    named = {cid for i in review.get('issues', []) if i['kind'] == 'conflict' for cid in i['claim_ids']}
    issues_only = [i for i in review.get('issues', []) if not kept.intersection(i['claim_ids'])]
    cases = (review.get('review_batch') or {}).get('cases', [])
    cases_only = [c for c in cases if c.get('fact_ids') and not kept.intersection(c['fact_ids'])]
    return {'claims': len(claims), 'anchored_claims': len(claims) - len(page_only), 'page_only_claims': len(page_only),
            'unsupported_conflict_alternatives': len(ids & named),
            'unsupported_unconnected_claims': len(ids - named),
            'page_only_claim_chars': serialized(page_only) if page_only else 0,
            'issues_only_via_page_only_claims': len(issues_only),
            'issue_chars_only_via_page_only_claims': serialized(issues_only) if issues_only else 0,
            'cases_only_via_page_only_claims': len(cases_only)}


def counts(request):
    review = request['review'] or {}
    batch = review.get('review_batch') or {}
    return {'windows': len(request['context']),
            'pages': len({(s['document_id'], s['page_number']) for s in request['context']}),
            'claims': len(review.get('claims', [])), 'issues': len(review.get('issues', [])),
            'conflicts': sum(i['kind'] == 'conflict' for i in review.get('issues', [])),
            'review_cases': len(batch.get('cases', [])), 'case_decisions': len(batch.get('decisions', {})),
            'review_answers': len(review.get('review_answers', []))}


def calibration(samples):
    """Bytes per actual prompt token from (exact message bytes, provider prompt_tokens) pairs."""
    ratios = sorted(b / t for b, t in samples if t)
    if not ratios:
        return None
    return {'bytes_per_token': round(statistics.median(ratios), 4), 'min': round(ratios[0], 4), 'max': round(ratios[-1], 4),
            'samples': len(ratios), 'basis': "median of this run's actual prompt_tokens over exact system+user message UTF-8 bytes"}


def condition_cause(record, trace):
    """Why a saved decision is unknown. Unknown is never read as absence of evidence."""
    if record['state'] != 'unknown':
        return 'decided:' + record['state']
    for prefix, cause in BLOCKED_PREFIXES.items():
        if (trace.get('error') or '').startswith(prefix):
            return cause
    if record.get('validation_issue'):
        return 'validation_rejected'
    if SCOPE_OR_PERIOD.search(record.get('reason') or ''):
        return 'model_unknown:scope_or_period_heuristic'
    return 'model_unknown:insufficient_in_supplied_windows'


def _terms(text):
    stop = set('the and for with that this from each institution institutional evidence documented identified stated '
               'explicit completed record records review relevant defined actual demonstrates demonstrate requirement '
               'have are its least one which their into where when such than more other within'.split())
    return {t for t in re.findall(r'[a-z0-9]{4,}', text.lower()) if t not in stop}


def retrieval_coverage(condition, context, sources):
    """Lexical signal for missed retrieval: do unselected pages cover more requirement terms? Not a recall measure."""
    terms = _terms(condition['text'])
    if not terms:
        return None
    cover = lambda text: len(terms & _terms(text)) / len(terms)
    chosen = {s['id'] for s in context}
    best_selected = max((cover(s['text']) for s in context), default=0)
    others = [(cover(s['text']), s['page_number']) for s in sources if s['id'] not in chosen]
    higher = sorted((p for c, p in others if c > best_selected))
    return {'requirement_terms': len(terms), 'best_selected_coverage': round(best_selected, 3),
            'best_unselected_coverage': round(max((c for c, _ in others), default=0), 3),
            'unselected_pages_covering_more_terms': len(higher), 'example_pages': higher[:5],
            'basis': 'share of requirement terms (4+ letters, stop words removed) present; heuristic only'}


def manifest_sources(manifest):
    """Page stubs for ledger page matching when only an export (no page text) is available."""
    return [{'id': p['page_id'], 'document_id': d['document_id'], 'page_number': p['number'], 'text': ''}
            for d in manifest for p in d['pages'] if p['status'] == 'ok']


def recommendation_requests(plan, sources, rubric):
    """Rebuild each advice batch request as generate_recommendations() builds it today.

    `sources` must carry frozen page text: each batch selects its indicator's windows. For
    comparison, `page_projection_ledger_*` is the whole-ledger packet the previous construction
    attached to every batch.
    """
    from .recommendation_execution import bounded_strengths
    from .recommendations import PROMPT, advice_schema, processing_failure
    from .semantic_retrieval import ranker_for
    foundation = plan.get('foundation_plan') or {}
    strengths = bounded_strengths(foundation.get('existing_strengths', []))
    model_actions = [a for a in plan['actions'] if not processing_failure(a) and (a['state'] != 'unknown' or strengths)]
    semantic_ranker = ranker_for(plan.get('retrieval_policy')) if model_actions else None
    ledger = plan.get('reviewed_evidence')
    whole = page_projection(ledger, sources)
    scope = plan.get('scope') or {}
    rows = []
    for indicator in dict.fromkeys(a['indicator'] for a in model_actions):
        actions = [a for a in model_actions if a['indicator'] == indicator]
        selected = select_context(next(i for i in rubric['indicators'] if i['code'] == indicator), sources, semantic_ranker=semantic_ranker)
        payload = {k: plan[k] for k in ('profile', 'population', 'reference_period')}
        payload['sources'] = selected
        payload['reviewed_evidence'] = review = for_context(ledger, selected)
        payload['actions'] = actions
        payload['established_strengths'] = strengths
        payload['foundation_goals'] = [{k: g[k] for k in ('id', 'title', 'depends_on', 'status', 'conditional')}
                                       for g in foundation.get('goals', [])]
        payload['scope'] = {k: scope[k] for k in ('institution', 'mode', 'population_label', 'period_label', 'limitations') if k in scope}
        user = json.dumps(payload, sort_keys=True)
        support = anchoring({'review': review, 'context': selected})
        rows.append({'indicator': indicator, 'actions': len(actions),
                     'unknown_actions': sum(a['state'] == 'unknown' for a in actions),
                     'user_chars': len(user), 'instructions_chars': len(PROMPT), 'schema_chars': len(json.dumps(advice_schema(actions, selected, strengths))),
                     'source_windows': len(selected), 'source_chars': len(json.dumps(selected)),
                     'ledger_chars': len(json.dumps(review)) if review else 0,
                     'ledger_claims': len((review or {}).get('claims', [])),
                     'unsupported_unconnected_claims': support['unsupported_unconnected_claims'],
                     'unsupported_conflict_alternatives': support['unsupported_conflict_alternatives'],
                     'page_projection_ledger_chars': len(json.dumps(whole)) if whole else 0,
                     'page_projection_ledger_claims': len((whole or {}).get('claims', [])),
                     'review_resolutions_carried': sum(1 for i in (review or {}).get('issues', []) if i.get('status') == 'resolved'),
                     'payload_hash': hashlib.sha256(user.encode()).hexdigest()})
    return {'strengths_supplied': len(strengths), 'model_actions': len(model_actions),
            'deterministic_actions': len(plan['actions']) - len(model_actions), 'batches': rows}


def advice_origins(advice):
    """Count advice by declared origin; model-tailored rows currently carry no origin field."""
    return dict(Counter(a.get('origin', 'unlabelled') for a in advice))


def analyse(export, *, sources=None):
    """Per-batch diagnostics for one saved run. `sources` (full frozen pages) enables retrieval replay."""
    assessment = export['assessment']
    rubric, ledger, scope = export['rubric'], export['reviewed_evidence'], export['scope']
    records = {r['condition_id']: r for r in assessment['records']}
    calls = assessment.get('inference', {}).get('calls', [])
    reservations = [c for c in calls if c.get('kind') == 'request_reserved']
    output_tokens = assessment.get('inference', {}).get('settings', {}).get('output_tokens')
    compatible = assessment.get('inference', {}).get('provider') == 'openai_compatible'
    rows, samples, attempted = [], [], 0
    claimed = set()
    for indicator, trace in zip(rubric['indicators'], assessment['traces']):
        if indicator['code'] != trace['indicator']:
            raise ValueError('Trace order does not match the frozen rubric.')
        context = trace['source_excerpts']
        prompt = system_prompt_for(trace.get('prompt_hash'))
        common = dict(ledger=ledger, scope=scope, population=export['population'],
                      reference_period=export['reference_period'], compatible_endpoint=compatible)
        request = evaluation_request(indicator, context, projection=projection_for(trace.get('prompt_version')),
                                     system_prompt=prompt or SYSTEM_PROMPT, **common)
        limit, ledger_chars = gate(request, calls_before=attempted)
        today = evaluation_request(indicator, context, **common)
        today_limit, today_chars = gate(today)
        row = {'indicator': indicator['code'], 'requirements': len(indicator['conditions']),
               'prompt_version': trace.get('prompt_version'), 'prompt_reproduced': prompt is not None,
               'input_hash_matches': request['input_hash'] == trace['input_hash'],
               'retrieval_replayed': None, 'pre_request_limit': limit,
               'current_construction': {'pre_request_limit': today_limit, 'ledger_chars_as_gated': today_chars,
                                        'user_chars': len(today['payload']), 'system_chars': len(today['system']),
                                        **counts(today), 'anchoring': anchoring(today)},
               'ledger_chars_as_gated': ledger_chars, 'model_call_attempted': trace['model_call_attempted'],
               'saved_error': trace.get('error') or '', **counts(request),
               'components': components(request), 'repetition': repetition(request), 'anchoring': anchoring(request),
               'user_chars': len(request['payload']), 'system_chars': len(request['system'])}
        if sources is not None:
            row['retrieval_replayed'] = retrieval_for(trace.get('retrieval_version'))(indicator, sources) == context
        row['decisions'] = dict(Counter(records[c['id']]['state'] for c in indicator['conditions']))
        row['causes'] = dict(Counter(condition_cause(records[c['id']], trace) for c in indicator['conditions']))
        requests = []
        if trace['model_call_attempted']:
            attempted += 1
            requests.append(('initial', request['system'], request['payload'], request['schema'], request['schema_name']))
            if trace.get('initial_response_audit') and trace.get('correction_response_audit'):
                failed = {i['condition_id'] for i in trace['initial_response_audit']['validation_issues']}
                subset = {**indicator, 'conditions': [c for c in indicator['conditions'] if c['id'] in failed]}
                correction = json.loads(request['payload'])
                correction['indicator'] = subset
                correction['correction'] = {
                    'instruction': 'Return every requested decision, including unknown, in the required conditions object. Re-evaluate only these requirements from the supplied exact passages; never invent a quotation or infer missing evidence.',
                    'issues': trace['initial_response_audit']['validation_issues']}
                schema = indicator_schema(subset, context)
                system = request['base_prompt'] + (_JSON_INSTRUCTIONS.format(schema=json.dumps(schema, separators=(',', ':'))) if compatible else '')
                requests.append(('correction', system, json.dumps(correction, sort_keys=True), schema, 'capability_conditions_correction'))
        row['provider_requests'] = []
        for kind, system, user, schema, name in requests:
            entry = {'kind': kind, 'message_bytes': len(system.encode()) + len(user.encode())}
            if reservations:
                kwargs = provider_kwargs(system, user, schema, name, model=reservations[0]['configured_model'],
                                         settings=reservations[0]['settings'])
                wanted = digest(kwargs)
                # Match by exact request hash; client retries (e.g. an invalid-JSON resend) add reservations.
                index = next((i for i, r in enumerate(reservations) if i not in claimed and r['request_hash'] == wanted), None)
                if index is not None:
                    claimed.add(index)
                entry.update(request_hash_matches=index is not None, reservation_index=index,
                             bound_input_tokens=envelope_input_bound(kwargs),
                             saved_bound_input_tokens=reservations[index]['input_token_bound'] if index is not None else None)
            row['provider_requests'].append(entry)
        if not requests and reservations:
            # The request this batch would have sent, bounded by the same reservation policy.
            kwargs = provider_kwargs(request['system'], request['payload'], request['schema'], request['schema_name'],
                                     model=reservations[0]['configured_model'], settings=reservations[0]['settings'])
            row['unsent_bound_input_tokens'] = envelope_input_bound(kwargs)
        rows.append(row)
    # Exports omit reservation event IDs; each reservation's outcome is the outcome at the same position.
    ordered = [c for c in calls if c.get('kind') == 'request_outcome']
    for entry in (e for r in rows for e in r['provider_requests']):
        index = entry.get('reservation_index')
        if index is None or index >= len(ordered):
            continue
        outcome = ordered[index]
        tokens = outcome.get('tokens') or {}
        entry['outcome'] = outcome.get('outcome')
        entry['actual_prompt_tokens'] = tokens.get('prompt_tokens', tokens.get('input_tokens'))
        entry['actual_completion_tokens'] = tokens.get('completion_tokens', tokens.get('output_tokens'))
        samples.append((entry['message_bytes'], entry['actual_prompt_tokens']))
    cal = calibration(samples)
    for row in rows:
        initial_bytes = row['system_chars'] + row['user_chars']
        sent = row['provider_requests']
        row['tokens'] = {
            'actual_prompt_tokens': sum(e.get('actual_prompt_tokens') or 0 for e in sent) if sent else None,
            'actual_completion_tokens': sum(e.get('actual_completion_tokens') or 0 for e in sent) if sent else None,
            'estimated_prompt_tokens': math.ceil(initial_bytes / cal['bytes_per_token']) if cal else None,
            'estimated_prompt_tokens_generic_4_chars': math.ceil(initial_bytes / 4),
            'bound_input_tokens': sum(e.get('bound_input_tokens') or 0 for e in sent) if sent else row.get('unsent_bound_input_tokens'),
            'bound_output_tokens': output_tokens * max(1, len(sent)) if output_tokens else None,
        }
    return {'version': VERSION, 'run_id': export.get('run_id'), 'calibration': cal, 'batches': rows,
            'unattributed_requests': [{'request_number': r.get('request_number'), 'input_token_bound': r.get('input_token_bound')}
                                      for i, r in enumerate(reservations) if i not in claimed]}


def replay_scoring(export, *, sources=None):
    """Saved validated decisions through the frozen engine; optionally publish()'s revalidation too."""
    from .engine import assess
    from .evaluation import validate_decisions
    assessment, rubric = export['assessment'], export['rubric']
    decisions = {r['condition_id']: r['state'] for r in assessment['records']}
    replay = assess(decisions, rubric)
    saved = assessment['result']
    result = {'matches_saved_result': replay == saved, 'lower': replay['lower'], 'upper': replay['upper'],
              'saved_lower': saved['lower'], 'saved_upper': saved['upper'],
              'state_counts': dict(Counter(decisions.values())), 'revalidation_matches_saved_records': None}
    if sources is not None:
        records = {r['condition_id']: r for r in assessment['records']}
        same = True
        for indicator in rubric['indicators']:
            subset = [dict(records[c['id']]) for c in indicator['conditions']]
            for row in validate_decisions(indicator, {'conditions': subset}, sources, reviewed_evidence=export['reviewed_evidence']):
                saved_row = records[row['condition_id']]
                same &= (row['state'], row['citations']) == (saved_row['state'], saved_row['citations'])
        result['revalidation_matches_saved_records'] = same
    return result


def _proposal(audit, condition_id):
    rows = ((audit or {}).get('model_response') or {}).get('conditions', {})
    if isinstance(rows, list):
        rows = {r.get('condition_id'): r for r in rows if isinstance(r, dict)}
    row = rows.get(condition_id)
    if not isinstance(row, dict):
        return None
    return {'state': row.get('state'), 'reason': row.get('reason'), 'citations': len(row.get('citations') or []),
            'scope_supported': row.get('scope_supported'), 'period_supported': row.get('period_supported')}


def trace_requirement(export, analysis, condition_id, *, sources=None):
    """Source evidence -> retrieval -> review disposition -> provider -> validation -> decision for one requirement."""
    rubric = export['rubric']
    indicator = next(i for i in rubric['indicators'] if any(c['id'] == condition_id for c in i['conditions']))
    condition = next(c for c in indicator['conditions'] if c['id'] == condition_id)
    trace = next(t for t in export['assessment']['traces'] if t['indicator'] == indicator['code'])
    batch = next(b for b in analysis['batches'] if b['indicator'] == indicator['code'])
    record = next(r for r in export['assessment']['records'] if r['condition_id'] == condition_id)
    context = trace['source_excerpts']
    review = projection_for(trace.get('prompt_version'))(export['reviewed_evidence'], context) or {}
    initial = trace.get('initial_response_audit') or trace.get('response_audit')
    return {
        'requirement': {'id': condition_id, 'indicator': indicator['code'], 'level': condition.get('level'), 'text': condition['text']},
        'retrieval': {'windows': [{'page': s['page_number'], 'offset': s['text_offset'], 'chars': len(s['text'])} for s in context],
                      'replayed_identically': batch['retrieval_replayed'],
                      'coverage': retrieval_coverage(condition, context, sources) if sources is not None else None},
        'review_disposition': {'claims': dict(Counter(c['disposition'] for c in review.get('claims', []))),
                               'open_issues': dict(Counter(i['kind'] for i in review.get('issues', []) if i.get('status') != 'resolved')),
                               'anchored_claims': batch['anchoring']['anchored_claims'],
                               'page_only_claims': batch['anchoring']['page_only_claims']},
        'provider': {'pre_request_limit': batch['pre_request_limit'], 'ledger_chars_as_gated': batch['ledger_chars_as_gated'],
                     'attempted': trace['model_call_attempted'],
                     'initial_proposal': _proposal(initial, condition_id) if trace['model_call_attempted'] else None,
                     'correction_proposal': _proposal(trace.get('correction_response_audit'), condition_id)},
        'validation': {'initial_issues': [i['issue'] for i in (trace.get('initial_response_audit') or {}).get('validation_issues', [])
                                          if i['condition_id'] == condition_id],
                       'final_issue': record.get('validation_issue') or ''},
        'decision': {'state': record['state'], 'reason': record['reason'], 'citations': len(record['citations']),
                     'cause': condition_cause(record, trace)},
    }


def representative_requirements(export):
    """One requirement each from: a context-blocked batch, a batch with a demonstrated requirement, an evaluated all-unknown batch."""
    records = {r['condition_id']: r for r in export['assessment']['records']}
    picks = {}
    for indicator, trace in zip(export['rubric']['indicators'], export['assessment']['traces']):
        ids = [c['id'] for c in indicator['conditions']]
        states = [records[i]['state'] for i in ids]
        if (trace.get('error') or '').startswith('Reviewed-evidence context exceeds'):
            picks.setdefault('blocked_by_context', ids[0])
        elif 'met' in states and trace.get('correction_response_audit'):
            picks.setdefault('demonstrated', next(i for i in ids if records[i]['state'] == 'met'))
        elif trace['model_call_attempted'] and set(states) == {'unknown'}:
            picks.setdefault('evaluated_unknown', ids[0])
    return picks


def cause_summary(export, *, sources=None):
    """Unknown decisions by first stage that explains them; retrieval signal needs full frozen pages."""
    traces = {t['indicator']: t for t in export['assessment']['traces']}
    records = {r['condition_id']: r for r in export['assessment']['records']}
    causes, signals = Counter(), Counter()
    for indicator in export['rubric']['indicators']:
        trace = traces[indicator['code']]
        for condition in indicator['conditions']:
            record = records[condition['id']]
            cause = condition_cause(record, trace)
            causes[cause] += 1
            if sources is not None and cause.startswith('model_unknown'):
                coverage = retrieval_coverage(condition, trace['source_excerpts'], sources)
                signals['unselected_page_covers_more_terms' if coverage and coverage['unselected_pages_covering_more_terms']
                        else 'no_lexical_miss_signal'] += 1
    repaired = sum(len((t.get('initial_response_audit') or {}).get('validation_issues', [])) for t in traces.values())
    return {'causes': dict(causes), 'retrieval_signal_for_model_unknowns': dict(signals) if sources is not None else None,
            'validation_issues_repaired_by_correction': repaired}
