"""Score explanations: why each requirement, key indicator and area scored what it did, written for the institution.

Harsha (12 Nov 2026): every score needs an explanation that supports it and credits the institution for what it did
("you did this, it is good; because only this much is done, this is how you scored"), low scores included; for what
was not found, say where we looked. Siddharth (19 Nov): model-written, not templates, and warm, since the readers are
our customers.

One model call per area (9 per run). Each area's input is built from the run's own record and nothing else: each
requirement's result, the parts it asks for and how each was judged, the quotations its judgment rests on (with the
document and page), the documents its key indicator's judge actually read, what is still missing and whether it is in
the priority plan, and for a final result what the second layer changed. The output has the front end's shape
(frontend-new ScoreExplanation): found, text (how it was reached), looked, next_step.

The warmth is in the framing only. validate() rejects an explanation that:
- cites a quotation id it was not given, or credits a requirement with no quotation, or says something was found
  where nothing was credited;
- puts words in quotation marks that are not in that requirement's quotations;
- says "fully", "completely" or "entirely" about anything not credited in full;
- writes a number (in digits or words) or a percentage that is not in that requirement's own input;
- widens scope ("every department", "the whole college") beyond what its quotations say;
- credits a requirement without naming the document or quoting it;
- names the assessment's machinery (rubric codes, requirement ids, packets);
- leaves out "where we looked" or the next step for something not shown, or adds them where all is shown.
A rejected area is asked once more with the problems listed; whatever still fails gets a plain factual explanation
built from the same input (marked fallback), so a report never shows an unchecked claim or an empty space.
Explanations never change a score: they are stored beside the run (CapabilityExplanation), not in it.
"""
import json
import re

VERSION = 'explanations-0.2'
MAX_QUOTES = 4
QUOTE_CHARS = 400
MAX_FIELD_CHARS = 700
MAX_DOCUMENTS = 8
FIELDS = ('found', 'text', 'looked', 'next_step')

SYSTEM_PROMPT = """You write the explanations in an AI-readiness report for a college's leadership. They are our customers. Write warmly and encouragingly, and give them real, specific credit for what they have done. But every statement must be true to the assessment you are given.

You receive one area of the assessment: its key indicators and their requirements. For each requirement you get its result, the parts it asks for and how each part was judged, quotations from the college's own documents that the judgment rests on (each with an id), the documents that were read for it, and what is still missing.

For each requirement write four fields:
- found: what was found and credited, in one or two sentences, naming the document. List the quotations you rely on in quote_ids. You may quote a few words from a quotation in double quotes, exactly as given. Empty when nothing was credited.
- text: how that led to the result: shown in full, partly shown (say which parts are shown and which are not yet), or not yet shown.
- looked: only when something is not shown: which of the listed documents were read and that they did not show it. Empty when shown in full.
- next_step: only when something is not shown: the missing part, phrased as a concrete next step the college can take. Empty when shown in full.

For each key indicator, and for the area as a whole, write the same four fields as a short summary of at most three sentences each, leading with strengths.

Rules:
1. Use only what is in the input. Never mention evidence, documents, numbers, dates or activities that are not in it.
2. Never say or imply more credit than was given. A partly credited requirement is partly shown; one not credited is not yet shown. Use "fully", "completely" or "entirely" only for a requirement shown in full.
3. If a requirement went down because the college's own document contradicts it, say so plainly and kindly, citing the quotation.
4. Do not give scores, credit or percentages; the report shows them.
5. Do not mention how the assessment works inside (models, passes, packets, rubric or requirement codes). Write plain English for a principal or vice-chancellor.
6. Be warm in framing, not in substance: begin with what the college has done, and describe gaps as next steps, never as failures.
7. For a requirement that could not be judged because of a processing problem, say only that it will be checked again.
8. Keep to the scope the quotations show. If a quotation names one programme, department or group, say that one; never widen it to "every department", "all students" or "the whole college".
9. In found, name the document a quotation comes from. Use digits only for numbers that appear in the input, and do not write numbers out in words unless the quotation does.
10. "Where we looked": every document the college uploaded was searched (documents_searched); documents_read are the ones that held the passages read for this key indicator. Name only documents listed there."""


def _entry(extra=None):
    properties = {f: {'type': 'string'} for f in FIELDS}
    properties.update(extra or {})
    return {'type': 'object', 'additionalProperties': False, 'required': sorted(properties), 'properties': properties}


def schema(condition_ids, indicator_codes):
    return {'type': 'object', 'additionalProperties': False, 'required': ['area', 'indicators', 'requirements'],
            'properties': {
                'area': _entry(),
                'indicators': {'type': 'array', 'items': _entry(
                    {'code': {'type': 'string', 'enum': list(indicator_codes)}})},
                'requirements': {'type': 'array', 'items': _entry(
                    {'condition_id': {'type': 'string', 'enum': list(condition_ids)},
                     'quote_ids': {'type': 'array', 'items': {'type': 'string'}}})}}}


# ------------------------------------------------------------------ input


def _names():
    from .report_projection import AREA_TITLES, PILLARS
    return PILLARS, AREA_TITLES


def document_names(manifest):
    """{document id: readable name} from the run's manifest (the file name without its extension)."""
    names = {}
    for entry in manifest or []:
        name = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', entry.get('filename') or '').replace('_', ' ').strip()
        names[str(entry['document_id'])] = name or 'an uploaded document'
    return names


def _where(source_id, sources, names):
    source = sources.get(source_id) or {}
    name = names.get(str(source.get('document_id')), 'an uploaded document')
    return f"{name}, page {source['page_number']}" if source.get('page_number') is not None else name


def _part_result(part):
    first, second = part.get('credited_as'), part.get('second_credited_as', part.get('credited_as'))
    if 'contradicted' in (first, second) and first == second:
        return 'contradicted by the college\'s own document'
    if first == second == 'full':
        return 'shown'
    if 'full' in (first, second) or 'related' in (first, second):
        return 'partly shown'
    if 'digital_only' in (first, second):
        return 'shown only in a digital form that is not AI, which this part does not count'
    return 'not shown'


NOT_JUDGED = 'not judged yet (a processing problem; it will be checked again)'


def _result(record):
    """The result follows the credit the report shows, always: anything else (sources disagreeing, a change after
    follow-up) is a separate note, so an explanation can never contradict the number beside it."""
    from .action_plan import credit_of
    from .decision_causes import is_processing
    if is_processing(record):
        return NOT_JUDGED
    credit = credit_of(record)
    return 'shown in full' if credit >= 1 else 'partly shown' if credit > 0 else 'not yet shown'


def _looked(trace, sources, names):
    """The documents (and pages) the key indicator's judge read: from its trace's source ids."""
    pages = {}
    for source_id in (trace or {}).get('source_ids') or []:
        source = sources.get(source_id)
        if not source:
            continue
        name = names.get(str(source.get('document_id')), 'an uploaded document')
        pages.setdefault(name, set()).add(source.get('page_number'))
    ranked = sorted(pages.items(), key=lambda item: -len(item[1]))[:MAX_DOCUMENTS]
    return [{'document': name, 'pages': sorted(p for p in found if p is not None)} for name, found in ranked]


def area_input(area, target):
    """The model's input for one area (AIQIF-C1 ... C9) of a target (see build_target)."""
    from .action_plan import credit_of, missing_parts
    from .part_judgment import _load
    pillars, titles = _names()
    spec = _load()[0]['conditions']
    rubric, sources, names = target['rubric'], target['sources'], target['names']
    by_id = {r['condition_id']: r for r in target['records']}
    traces = {t.get('indicator'): t for t in target['traces']}
    merge = {row['condition_id']: row for row in target.get('merge') or []}
    planned = set((target.get('plan') or {}).get('condition_ids') or [])
    indicators = []
    for indicator in rubric['indicators']:
        if indicator.get('pillar') != area:
            continue
        looked = _looked(traces.get(indicator['code']), sources, names)
        requirements = []
        for condition in indicator['conditions']:
            cid = condition['id']
            record = by_id.get(cid) or {'condition_id': cid, 'state': 'unknown'}
            row = merge.get(cid)
            parts_spec = {p['id']: p for p in (spec.get(cid) or {}).get('parts') or []}
            parts = [{'asks': (parts_spec.get(p['id']) or {}).get('full') or p['id'], 'result': _part_result(p)}
                     for p in record.get('parts') or []]
            quotes = []
            for n, citation in enumerate((record.get('citations') or [])[:MAX_QUOTES], start=1):
                quotes.append({'id': f'Q{n}', 'document': _where(citation.get('source_id'), sources, names),
                               'text': (citation.get('quote') or '')[:QUOTE_CHARS]})
            credit = credit_of(record)
            if credit >= 1:
                missing = []
            elif credit > 0:
                missing = missing_parts(record)
            else:
                missing = [p['full'] for p in parts_spec.values() if p.get('full')] or [condition['text']]
            entry = {'condition_id': cid, 'requirement': condition['text'],
                     'stage': {'F': 'starting capability', 'A': 'repeated use', 'O': 'results and review'}.get(
                         condition.get('level'), condition.get('level')),
                     'result': _result(record), 'parts': parts, 'quotations': quotes,
                     'still_missing': missing, 'in_priority_plan': cid in planned}
            if record.get('state') == 'conflicting':
                entry['note'] = 'some of the college\'s documents disagree with each other on this'
            if row and row.get('decision') == 'replaced':
                entry['changed_after_follow_up'] = 'raised by evidence the college sent after the first assessment'
            if row and row.get('decision') == 'lowered':
                entry['changed_after_follow_up'] = ('lowered: a document the college sent after the first assessment '
                                                    'contradicts it')
            requirements.append(entry)
        results = [r['result'] for r in requirements]
        indicators.append({'code': indicator['code'], 'name': titles.get(indicator['code'], indicator.get('name')),
                           'documents_read': looked, 'requirements': requirements,
                           'counts': {'requirements': len(results), 'shown_in_full': results.count('shown in full'),
                                      'partly_shown': results.count('partly shown'),
                                      'not_yet_shown': results.count('not yet shown')}})
    searched = sorted(set(names.values()))
    return {'area': area, 'name': pillars.get(area, area), 'indicators': indicators,
            'documents_searched': {'count': len(searched), 'names': searched[:20]}}


# ------------------------------------------------------------------ checks

QUOTED = re.compile(r'[\u201c"]([^\u201d"]{3,})[\u201d"]|\u2018([^\u2019]{3,})\u2019')
NUMBER = re.compile(r'\d+(?:[.,]\d+)*')
NUMBER_WORDS = re.compile(r'\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|'
                          r'forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen|lakh|crore)s?\b', re.I)
PERCENT = re.compile(r'%|\bper ?cent\b', re.I)
OVERCLAIM = re.compile(r'\b(fully|completely|entirely)\b', re.I)
WIDENING = re.compile(r'\b(?:every|all|each)\s+(?:of\s+(?:the|its|your)\s+)?(?:department|student|faculty|teacher|staff|'
                      r'programme|program|course|classroom|school|campus|discipline)s?\b|\b(?:institution|college|'
                      r'university|campus)-wide\b|\b(?:whole|entire)\s+(?:college|institution|university|campus)\b|'
                      r'\bacross\s+the\s+(?:college|institution|university|campus)\b', re.I)
MACHINERY = re.compile(r'AIQIF|\bC\d\.\d|\bpacket|\brubric|\bcondition[_ ]id|\b[FAO]\d\b')


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').replace('\u2019', "'").replace('\u2018', "'")).strip().lower()


def _clean(entry):
    return {f: re.sub(r'\s+', ' ', str((entry or {}).get(f) or '')).strip() for f in FIELDS}


def _spans(value):
    return [a or b for a, b in QUOTED.findall(value)]


def _scope(requirements, *, extra=''):
    """What a field may draw on: the numbers, words and quotations of these requirements only (their text, parts,
    quotations and document labels), never ids or codes."""
    texts, labels, quotes = [], [extra], []
    for r in requirements:
        texts += [r['requirement']] + [p['asks'] for p in r['parts']] + list(r['still_missing'])
        for q in r['quotations']:
            texts.append(q['text'])
            labels.append(q['document'])
            quotes.append(_norm(q['text']))
    text = ' '.join(texts)
    # A number in a document's name or page counts only where it is written as that name or page ("SSR 2024",
    # "page 3"), so a page number cannot license an invented "3 workshops".
    names = {_norm(re.sub(r', page \d+$', '', label)) for label in labels if label}
    pages = {m for label in labels for m in re.findall(r', page (\d+)$', label or '')}
    return {'numbers': {n.replace(',', '') for n in NUMBER.findall(text)}, 'text': _norm(' '.join([text] + labels)),
            'quotes': quotes, 'names': sorted((n for n in names if n), key=len, reverse=True), 'pages': pages,
            'full': bool(requirements) and all(r['result'] == 'shown in full' for r in requirements)}


def _numbers_outside_names(value, scope):
    text = _norm(value)
    for name in scope.get('names', []):
        text = text.replace(name, ' ')
    text = re.sub(r'\bpages? (\d+)', lambda m: ' ' if m.group(1) in scope.get('pages', ()) else m.group(0), text)
    return NUMBER.findall(text)


def _check(where, entry, scope, errors):
    for field in FIELDS:
        value = entry[field]
        if len(value) > MAX_FIELD_CHARS:
            errors.append(f'{where}: {field} is too long.')
        if MACHINERY.search(value):
            errors.append(f'{where}: {field} mentions codes or internal terms; write plain English.')
        if PERCENT.search(value):
            errors.append(f'{where}: {field} gives a percentage; the report shows the score.')
        for number in _numbers_outside_names(value, scope):
            if number.replace(',', '') not in scope['numbers']:
                errors.append(f'{where}: {field} has the number {number}, which is not in its input.')
        for word in NUMBER_WORDS.findall(value):
            if not re.search(rf'\b{word}s?\b', scope['text']):
                errors.append(f'{where}: {field} writes the number "{word}", which is not in its input.')
        for phrase in WIDENING.findall(value):
            if _norm(phrase) not in scope['text']:
                errors.append(f'{where}: {field} says "{phrase}", wider than its quotations show.')
        for span in _spans(value):
            if not any(_norm(span) in q for q in scope['quotes']):
                errors.append(f'{where}: {field} quotes words that are not in its quotations.')
        if not scope['full'] and OVERCLAIM.search(value):
            errors.append(f'{where}: {field} says fully, completely or entirely, but not everything is shown in full.')
    if not entry['text']:
        errors.append(f'{where}: text is empty.')


def _summary_scope(requirements, counts, extra=''):
    scope = _scope(requirements, extra=extra)
    scope['numbers'] |= {str(v) for v in counts.values()}
    return scope


def _with_documents(scope, area, title=''):
    """Let a field name any document searched or read for the area (by name, with its pages), and use its title."""
    names = list(area['documents_searched']['names'])
    pages = set()
    for indicator in area['indicators']:
        for document in indicator['documents_read']:
            names.append(document['document'])
            pages |= {str(p) for p in document['pages']}
    scope['names'] = sorted({_norm(n) for n in names if n} | set(scope['names']), key=len, reverse=True)
    scope['pages'] = set(scope['pages']) | pages
    scope['text'] += ' ' + _norm(' '.join(names + [title]))


def validate(area, output):
    """(explanations, errors). explanations: {'area', 'indicators': {code: ...}, 'requirements': {cid: ...}} with
    only the entries that passed; errors: one line per problem, phrased for the retry."""
    errors, passed = [], {'area': None, 'indicators': {}, 'requirements': {}}
    given = {r['condition_id']: r for i in area['indicators'] for r in i['requirements']}
    seen = {}
    for item in (output or {}).get('requirements') or []:
        cid = item.get('condition_id')
        if cid in given and cid not in seen:
            seen[cid] = item
    for cid, requirement in given.items():
        if cid not in seen:
            errors.append(f'{cid}: missing.')
            continue
        item, entry, problems = seen[cid], _clean(seen[cid]), []
        ids = {q['id'] for q in requirement['quotations']}
        cited = [q for q in item.get('quote_ids') or [] if isinstance(q, str)]
        if set(cited) - ids:
            problems.append(f'{cid}: quote_ids {sorted(set(cited) - ids)} were not given for it.')
        full = requirement['result'] == 'shown in full'
        credited = requirement['result'] in ('shown in full', 'partly shown')
        lowered = 'contradicts' in requirement.get('changed_after_follow_up', '')
        if credited and requirement['quotations'] and not (set(cited) & ids):
            problems.append(f'{cid}: it is credited, so found must rest on at least one of its quotations.')
        if credited and not entry['found']:
            problems.append(f'{cid}: found is empty, but something was credited.')
        if credited and entry['found'] and requirement['quotations']:
            named = [_norm(re.sub(r', page \d+$', '', q['document'])) for q in requirement['quotations']
                     if q['id'] in cited]
            if not _spans(entry['found']) and not any(n and n in _norm(entry['found']) for n in named):
                problems.append(f'{cid}: found must name the document it rests on, or quote it.')
        if not credited and entry['found'] and not lowered:
            problems.append(f'{cid}: nothing was credited, so found must be empty.')
        processing = requirement['result'] == NOT_JUDGED
        if full and (entry['looked'] or entry['next_step']):
            problems.append(f'{cid}: it is shown in full, so looked and next_step must be empty.')
        if not full and not processing and not entry['next_step']:
            problems.append(f'{cid}: next_step is empty, but something is not shown.')
        if not full and not processing and not entry['looked'] and not lowered:
            problems.append(f'{cid}: looked is empty, but something is not shown.')
        scope = _scope([requirement])
        _with_documents(scope, area)
        _check(cid, entry, scope, problems)
        errors += problems
        if not problems:
            passed['requirements'][cid] = {**entry, 'quote_ids': cited}
    codes = {i['code']: i for i in area['indicators']}
    summaries = {}
    for item in (output or {}).get('indicators') or []:
        if item.get('code') in codes:
            summaries.setdefault(item['code'], item)
    for code, indicator in codes.items():
        if code not in summaries:
            errors.append(f'{code}: missing.')
            continue
        entry, problems = _clean(summaries[code]), []
        scope = _summary_scope(indicator['requirements'], indicator['counts'])
        _with_documents(scope, area, indicator['name'])
        _check(code, entry, scope, problems)
        errors += problems
        if not problems:
            passed['indicators'][code] = entry
    everything = [r for i in area['indicators'] for r in i['requirements']]
    totals = {k: sum(i['counts'][k] for i in area['indicators']) for k in area['indicators'][0]['counts']} \
        if area['indicators'] else {}
    scope = _summary_scope(everything, totals)
    _with_documents(scope, area, area['name'])
    entry, problems = _clean((output or {}).get('area')), []
    _check('area', entry, scope, problems)
    errors += problems
    if not problems:
        passed['area'] = entry
    return passed, errors


# ------------------------------------------------------------------ plain fallback


def _list(items):
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1] if items else ''


def _lower_first(text):
    return text[:1].lower() + text[1:] if text else text


def fallback_requirement(requirement, indicator):
    result, quotes = requirement['result'], requirement['quotations']
    found = ''
    if quotes and result in ('shown in full', 'partly shown'):
        found = f"Your {quotes[0]['document']} records: \"{quotes[0]['text'][:200].strip()}\"."
    shown = [p['asks'] for p in requirement['parts'] if p['result'] == 'shown']
    if result == 'shown in full':
        text = 'This is shown in your documents.'
    elif result == 'partly shown':
        text = ('This is partly shown' + (f': {_lower_first(_list(shown))} is shown' if shown else '') + '.')
    elif result == NOT_JUDGED:
        return {'found': '', 'text': 'This could not be checked this time; it will be checked again.', 'looked': '',
                'next_step': '', 'quote_ids': [], 'fallback': True}
    else:
        text = 'This is not yet shown in the documents we read.'
    if 'contradicts' in requirement.get('changed_after_follow_up', ''):
        text += ' A document you sent after the first assessment shows otherwise for part of it.'
    full = result == 'shown in full'
    documents = [d['document'] for d in indicator['documents_read'][:4]]
    looked = '' if full else (f'We read {_list(documents)} for this.' if documents else
                              'We read every document you uploaded for this.')
    missing = requirement['still_missing']
    next_step = '' if full else (f'Next step: show {_lower_first(missing[0]).rstrip(".")}.' if missing else '')
    return {'found': found, 'text': text, 'looked': looked, 'next_step': next_step,
            'quote_ids': ['Q1'] if found else [], 'fallback': True}


def fallback_summary(requirements, name):
    results = [r['result'] for r in requirements]
    full, part = results.count('shown in full'), results.count('partly shown')
    rest = len(results) - full - part
    pieces = []
    if full:
        pieces.append(f"{full} {'is' if full == 1 else 'are'} shown in full")
    if part:
        pieces.append(f"{part} {'is' if part == 1 else 'are'} partly shown")
    if rest:
        pieces.append(f"{rest} {'is' if rest == 1 else 'are'} not yet shown")
    return {'found': '', 'text': f"Of the {len(results)} requirements under {name}, {_list(pieces)}.", 'looked': '',
            'next_step': 'The next steps under each requirement show what would add most.' if rest or part else '',
            'fallback': True}


# ------------------------------------------------------------------ a run


def build_target(run):
    """What the explanations read for a completed run (provisional or final), from this database."""
    from .action_plan import build as build_plan
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise ValueError(f'Run {run.pk} has no completed assessment.')
    inputs = run.inputs or {}
    records = event.payload.get('records') or []
    return {'run_id': str(run.pk), 'event_id': event.pk, 'rubric': inputs['rubric'], 'records': records,
            'traces': event.payload.get('traces') or [],
            'sources': {s['id']: s for s in inputs.get('sources') or []},
            'names': document_names(inputs.get('manifest')),
            'merge': (inputs.get('second_layer') or {}).get('merge') or [],
            'plan': build_plan(inputs['rubric'], records)}


def explain(target, model, *, max_calls=None):
    """{'version', 'run_id', 'event_id', 'areas': {code: ...}, 'indicators': {code: ...}, 'requirements': {cid: ...},
    'fallbacks': [ids], 'calls': n}. model: the depth code's interface (system, content, schema, name) -> dict."""
    out = {'version': VERSION, 'run_id': target['run_id'], 'event_id': target['event_id'], 'areas': {},
           'indicators': {}, 'requirements': {}, 'fallbacks': [], 'calls': 0, 'errors': {}}
    areas = []
    for indicator in target['rubric']['indicators']:
        if indicator.get('pillar') not in areas:
            areas.append(indicator.get('pillar'))
    for area in areas:
        payload = area_input(area, target)
        ids = [r['condition_id'] for i in payload['indicators'] for r in i['requirements']]
        codes = [i['code'] for i in payload['indicators']]
        passed, errors, content = {'area': None, 'indicators': {}, 'requirements': {}}, [], json.dumps(
            payload, ensure_ascii=False)
        for attempt in range(2):
            if max_calls is not None and out['calls'] >= max_calls:
                break
            if attempt and errors:
                content = json.dumps({**payload, 'your_previous_answer_had_these_problems': errors[:40],
                                      'instruction': 'Write the whole answer again, fixing every problem.'},
                                     ensure_ascii=False)
            out['calls'] += 1
            response = model(SYSTEM_PROMPT, content, schema(ids, codes), 'score_explanations')
            checked, errors = validate(payload, response)
            # Keep the best of each entry across attempts: an entry that passed once stays.
            passed['requirements'].update({k: v for k, v in checked['requirements'].items()
                                           if k not in passed['requirements']})
            passed['indicators'].update({k: v for k, v in checked['indicators'].items()
                                         if k not in passed['indicators']})
            passed['area'] = passed['area'] or checked['area']
            if len(passed['requirements']) == len(ids) and len(passed['indicators']) == len(codes) and passed['area']:
                errors = []
                break
        if errors:
            out['errors'][area] = errors[:40]
        for indicator in payload['indicators']:
            for requirement in indicator['requirements']:
                cid = requirement['condition_id']
                if cid not in passed['requirements']:
                    passed['requirements'][cid] = fallback_requirement(requirement, indicator)
                    out['fallbacks'].append(cid)
            if indicator['code'] not in passed['indicators']:
                passed['indicators'][indicator['code']] = fallback_summary(indicator['requirements'], indicator['name'])
                out['fallbacks'].append(indicator['code'])
        if not passed['area']:
            passed['area'] = fallback_summary([r for i in payload['indicators'] for r in i['requirements']],
                                              payload['name'])
            out['fallbacks'].append(area)
        out['areas'][area] = passed['area']
        out['indicators'].update(passed['indicators'])
        out['requirements'].update(passed['requirements'])
    return out


def latest(run):
    """The newest explanations stored for a run's current completed assessment, or None."""
    from apps.scoring.models import CapabilityExplanation
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        return None
    row = CapabilityExplanation.objects.filter(run=run, event_id=event.pk).order_by('-created_at').first()
    return row.payload if row else None


def attach(assessment, explanations):
    """A copy of an assessment payload (records, result) with explanations attached where the front end reads them:
    records[].explanation, result.indicators[].explanation, result.documented.indicators[] and .pillars[]."""
    if not explanations:
        return assessment
    public = lambda e: {k: e.get(k) or None for k in FIELDS} if e else None
    out = dict(assessment)
    out['records'] = [{**r, 'explanation': public(explanations['requirements'].get(r.get('condition_id')))}
                      for r in assessment.get('records') or []]
    result = dict(assessment.get('result') or {})
    if result.get('indicators'):
        result['indicators'] = [{**i, 'explanation': public(explanations['indicators'].get(i.get('code')))}
                                for i in result['indicators']]
    documented = result.get('documented')
    if isinstance(documented, dict):
        documented = dict(documented)
        documented['indicators'] = [{**i, 'explanation': public(explanations['indicators'].get(i.get('code')))}
                                    for i in documented.get('indicators') or []]
        documented['pillars'] = [{**p, 'explanation': public(explanations['areas'].get(p.get('code')))}
                                 for p in documented.get('pillars') or []]
        result['documented'] = documented
    out['result'] = result
    out['explanations_version'] = explanations.get('version')
    return out
