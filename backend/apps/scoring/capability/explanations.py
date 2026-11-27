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

VERSION = 'explanations-0.6'   # 0.6 (26 Nov): a verdict for each key indicator, for the detailed report
#: 0.5 (26 Nov 2026): a weak area's card lists "the closest things you have" (presentation.card_view: the starting
#: points its next step was written from), so its writer is given them and writes the verdict from them; written after
#: the next steps (publication.keep_going). In 0.4 a verdict could name an ERP portal and a firewall as the area's
#: assets while the card beside it listed a plagiarism policy.
MAX_QUOTES = 4
QUOTE_CHARS = 400
MAX_FIELD_CHARS = 700
MAX_DOCUMENTS = 8
MAX_LOOKED = 3
FIELDS = ('found', 'text', 'looked', 'next_step')
#: The area card of the leadership report (build brief, part D): a stand-alone verdict in the third person, one short
#: fact for page 1's summary, two or three strengths each resting on a quotation, and two or three gaps.
AREA_FIELDS = ('verdict', 'headline', 'strengths', 'gaps')
MAX_CARD_ITEMS = 3
MAX_VERDICT_CHARS = 320
MAX_HEADLINE_CHARS = 90

SYSTEM_PROMPT = """You write the explanations in an AI-readiness report for a college's leadership. They are our customers. Write to them directly, as "you" and "your", warmly and encouragingly, and give them real, specific credit for what they have done. Every statement must still be true to the assessment you are given.

You receive one area of the assessment: its key indicators and their requirements. For each requirement you get its result, the parts it asks for and how each part was judged, quotations from the college's own documents that the judgment rests on (each with an id), the documents that were read for it, and what is still missing.

For each requirement write four fields:
- found: when something was credited, begin with what the college has done, in its favour, and name the document: "Your Annual Quality Assurance Report shows you run AI workshops for faculty." List the quotations you rely on in quote_ids. You may quote a few words from a quotation in double quotes, exactly as given, as long as they read as a whole phrase: some quotations are cut off by the document's layout ("The firewall is upgraded to"), and those you say in your own words. Empty when nothing was credited.
- text: how that led to the result, in one or two sentences: shown in full, partly shown (what is shown and what is not yet), or not yet shown.
- looked: only when something is not shown: that every document was searched, naming at most three of the documents read for it, and that they did not show it. Empty when shown in full.
- next_step: only when something is not shown: one concrete thing the college could do or record next, in plain words. Empty when shown in full.

For each key indicator, and for the area as a whole, write the same four fields as a short summary of at most three sentences each. Lead with what the college is doing well.

For each key indicator also write a verdict, which the detailed report prints under the indicator's name: one or two sentences in the third person, like the area verdict below (rule 7's "you" does not apply), first what is there, named as its quotations name it (a programme, policy, office, system), then what is not yet there, in everyday words. No numbers. When nothing is credited, say plainly what was not found.

Rules:
1. Use only what is in the input. Never mention evidence, documents, numbers, dates or activities that are not in it.
2. Never say or imply more credit than was given. A partly credited requirement is partly shown; one not credited is not yet shown. Use "fully", "completely" or "entirely" only for a requirement shown in full.
3. If a requirement went down because the college's own document contradicts it, say so plainly and kindly, citing the quotation.
4. Do not give scores, credit or percentages; the report shows them.
5. Do not mention how the assessment works inside (models, passes, packets, rubric or requirement codes).
6. Plain words for a principal or vice-chancellor. The parts and still_missing are written for assessors: never copy their wording; say what they mean in everyday terms. For example, not "reproducible multi-cycle calculation records" but "keep the working behind each year's figures so they can be checked again".
7. Be warm in framing, not in substance: begin with what the college has done, and describe gaps as next steps, never as failures. Write "you" and "your", never "the institution" or "the college".
8. For a requirement that could not be judged because of a processing problem, say only that it will be checked again.
9. Keep to the scope the quotations show. If a quotation names one programme, department or group, say that one; never widen it to "every department", "all students" or "the whole college".
10. In found, name the document a quotation comes from. Use digits only for numbers that appear in the input, and do not write numbers out in words unless the quotation does.
11. Name documents only as they appear in the input (documents_read, documents_searched, quotations).

For the area as a whole, also write the card the leadership report prints:
- verdict: one or two sentences that stand alone, in the third person, beginning "The {institution_word} has" (institution_word is given): first what is there, named (a programme, policy, office, system), then what is not yet there. Rule 7's "you" does not apply here. No numbers.
- headline: one short fact for the report's front page, at most twelve words, no numbers, naming the area's strongest thing or, for a weak area, its plainest gap ("Quality is audited every year.", "No written guidance on AI use was found.").
- strengths: two or three things the {institution_word} has in this area, each one sentence that names the thing (a programme, policy, office, system, partner, project) as the quotation does, citing exactly one quotation (condition_id and quote_id) from a requirement with some credit. Empty when nothing in the area has credit.
- gaps: two or three things not yet there, each one short sentence a principal understands, listing the condition_ids of the requirements it is about (requirements not shown in full). Begin with the most basic.

Some weak areas come with closest_things_on_the_card: the starting points the card lists under "The closest things you have" in place of strengths. For such an area the verdict's first part names those things (as they are named there) and says plainly that they do not yet cover AI where that is so; it never presents anything else as what the area has. The headline then names the plainest gap."""


def _entry(extra=None):
    properties = {f: {'type': 'string'} for f in FIELDS}
    properties.update(extra or {})
    return {'type': 'object', 'additionalProperties': False, 'required': sorted(properties), 'properties': properties}


def _card():
    strength = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'condition_id', 'quote_id'],
                'properties': {'text': {'type': 'string'}, 'condition_id': {'type': 'string'},
                               'quote_id': {'type': 'string'}}}
    gap = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'condition_ids'],
           'properties': {'text': {'type': 'string'}, 'condition_ids': {'type': 'array', 'items': {'type': 'string'}}}}
    return {'verdict': {'type': 'string'}, 'headline': {'type': 'string'},
            'strengths': {'type': 'array', 'items': strength}, 'gaps': {'type': 'array', 'items': gap}}


def schema(condition_ids, indicator_codes):
    return {'type': 'object', 'additionalProperties': False, 'required': ['area', 'indicators', 'requirements'],
            'properties': {
                'area': _entry(_card()),
                'indicators': {'type': 'array', 'items': _entry(
                    {'code': {'type': 'string', 'enum': list(indicator_codes)}, 'verdict': {'type': 'string'}})},
                'requirements': {'type': 'array', 'items': _entry(
                    {'condition_id': {'type': 'string', 'enum': list(condition_ids)},
                     'quote_ids': {'type': 'array', 'items': {'type': 'string'}}})}}}


# ------------------------------------------------------------------ input


def _names():
    from .report_projection import AREA_TITLES, PILLARS
    return PILLARS, AREA_TITLES


def _readable(filename):
    """(name, group) for an uploaded file. Colleges upload files under a group ("criteria 3 - 3.2.1.pdf", "AICTE
    Approval - AICTE-Engineering-Approvals.pdf"): the name keeps both ("Criteria 3 (3.2.1)"), the group lets several
    files be named together ("the Criteria 3 files")."""
    stem = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', filename or '').replace('_', ' ')
    stem = re.sub(r'\s*\(\d+\)$', '', re.sub(r'\s+', ' ', stem)).strip()
    if not stem:
        return 'an uploaded document', None
    group, _, item = stem.partition(' - ')
    group = group[:1].upper() + group[1:]
    if item:
        return f'{group} ({item.strip()})', group
    return group, None


def document_names(manifest):
    """{document id: readable name} from the run's manifest (_readable)."""
    return {str(entry['document_id']): _readable(entry.get('filename'))[0] for entry in manifest or []}


def document_groups(manifest):
    """{document id: group} for files uploaded under a group (_readable)."""
    return {str(entry['document_id']): _readable(entry.get('filename'))[1] for entry in manifest or []}


def _where(source_id, sources, names):
    source = sources.get(source_id) or {}
    name = names.get(str(source.get('document_id')), 'an uploaded document')
    return f"{name}, page {source['page_number']}" if source.get('page_number') is not None else name


def _part_result(part):
    found = [part.get('credited_as')] + [part[k] for k in ('second_credited_as', 'third_credited_as') if k in part]
    if 'contradicted' in found and len(set(found)) == 1:
        return 'contradicted by the college\'s own document'
    if all(x == 'full' for x in found):
        return 'shown'
    if 'full' in found or 'related' in found:
        return 'partly shown'
    if 'digital_only' in found:
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


def _looked(trace, sources, names, groups=None):
    """The (at most MAX_LOOKED) documents that held the most passages the key indicator's judge read, from its trace's
    source ids. Several files from one upload group count as one source, named "the <group> files"."""
    groups = groups or {}
    passages, members = {}, {}
    for source_id in (trace or {}).get('source_ids') or []:
        source = sources.get(source_id)
        if not source:
            continue
        document = str(source.get('document_id'))
        key = groups.get(document) or names.get(document, 'an uploaded document')
        passages[key] = passages.get(key, 0) + 1
        members.setdefault(key, set()).add(document)
    ranked = sorted(passages, key=lambda key: -passages[key])[:MAX_LOOKED]
    out = []
    for key in ranked:
        if key in set(groups.values()) and len(members[key]) > 1:
            out.append({'document': f'the {key} files'})
        else:
            out.append({'document': names.get(next(iter(members[key])), key)})
    return out


def area_input(area, target):
    """The model's input for one area (AIQIF-C1 ... C9) of a target (see build_target)."""
    from .action_plan import credit_of, missing_parts
    from .part_judgment import _load
    pillars, titles = _names()
    spec = _load()[0]['conditions']
    rubric, sources, names = target['rubric'], target['sources'], target['names']
    groups = target.get('groups') or {}
    by_id = {r['condition_id']: r for r in target['records']}
    traces = {t.get('indicator'): t for t in target['traces']}
    merge = {row['condition_id']: row for row in target.get('merge') or []}
    planned = set((target.get('plan') or {}).get('condition_ids') or [])
    indicators = []
    for indicator in rubric['indicators']:
        if indicator.get('pillar') != area:
            continue
        looked = _looked(traces.get(indicator['code']), sources, names, groups)
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
    labels = sorted({f'the {g} files' for g in groups.values() if g} |
                    {n for d, n in names.items() if not groups.get(d)})
    out = {'area': area, 'name': pillars.get(area, area), 'indicators': indicators,
           'institution_word': target.get('institution_word') or 'institution',
           'documents_searched': {'count': len(names), 'names': labels[:20]}}
    closest = closest_on_card(area, target)
    if closest:
        out['closest_things_on_the_card'] = [c['text'] for c in closest]
    return out


def closest_on_card(area, target):
    """What a weak area's card lists under "The closest things you have" (presentation.card_view), from its written
    next step: [] for an area at or above CLOSEST_BELOW, or with no written step that builds on something."""
    from .presentation import CLOSEST_BELOW
    score = (target.get('area_scores') or {}).get(area)
    if score is None or score >= CLOSEST_BELOW:
        return []
    for key, step in ((target.get('next_steps') or {}).get('actions') or {}).items():
        if key.split(':', 1)[0].rsplit('.', 1)[0] == area and step.get('kind') != 'start':
            return [{'text': x['text'], 'sources': x.get('sources') or []}
                    for x in (step.get('have') or []) + (step.get('related') or [])][:MAX_CARD_ITEMS]
    return []


def institution_word(profile):
    """How the card's verdict names the institution: "university" or "college" from its profile, else "institution"."""
    kind = ' '.join(str((profile or {}).get(k) or '') for k in ('institution_type', 'type', 'name')).lower()
    if 'universit' in kind:
        return 'university'
    if 'college' in kind:
        return 'college'
    return 'institution'


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
THIRD_PERSON = re.compile(r'\bthe (?:institution|college|university)(?:\'s)?\b', re.I)
SECOND_PERSON = re.compile(r'\b(?:you|your|yours)\b', re.I)
MACHINERY = re.compile(r'AIQIF|\bC\d\.\d|\bpacket|\brubric|\bcondition[_ ]id|\b[FAO]\d\b')


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').replace('\u2019', "'").replace('\u2018', "'")).strip().lower()


def _clean(entry):
    return {f: re.sub(r'\s+', ' ', str((entry or {}).get(f) or '')).strip() for f in FIELDS}


def _cut_off(span):
    """A quoted span a reader can't make sense of (26 Nov): it stops on a word that needs more after it ("The firewall is
    upgraded to") or starts mid-sentence. The quotation check in presentation.unreadable, for a few quoted words."""
    from .presentation import _STOP_END
    t = re.sub(r'\s+', ' ', span).strip().rstrip(',;:')
    return bool(_STOP_END.search(t)) or (len(t.split()) > 3 and bool(re.match(r'[a-z]', t)) and
                                         not re.match(r'(?:e-|i[A-Z])', t))


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


def _loose(text):
    """Lower case, punctuation as spaces: "criteria 6 - h" and "Criteria 6 (h)" match."""
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', _norm(text)).split())


def _numbers_outside_names(value, scope):
    text = _loose(value)
    for name in sorted({_loose(n) for n in scope.get('names', []) if _loose(n)}, key=len, reverse=True):
        text = re.sub(rf'(?<![0-9a-z]){re.escape(name)}(?![0-9a-z])', ' ', text)
    text = re.sub(r'\bpages? (\d+)', lambda m: ' ' if m.group(1) in scope.get('pages', ()) else m.group(0), text)
    # _loose turned "2.5" into "2 5": read numbers back from the original where they survive outside names
    kept = set(text.split())
    return [n for n in NUMBER.findall(value) if all(part in kept for part in re.split(r'[.,]', n))]


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
            elif _cut_off(span):
                errors.append(f'{where}: {field} quotes "{span}", which stops mid-phrase; quote a whole phrase or '
                              'say it in your own words.')
        if not scope['full'] and OVERCLAIM.search(value):
            errors.append(f'{where}: {field} says fully, completely or entirely, but not everything is shown in full.')
        if THIRD_PERSON.search(value):
            errors.append(f'{where}: {field} says "the institution" or "the college"; write "you" and "your".')
    if not entry['text']:
        errors.append(f'{where}: text is empty.')


def _summary_scope(requirements, counts, extra=''):
    scope = _scope(requirements, extra=extra)
    scope['numbers'] |= {str(v) for v in counts.values()}
    return scope


def _documents_named(value, area):
    """The documents of the area's input that a field names (longest names first, each counted once)."""
    text = ' ' + _loose(value) + ' '
    names = {d['document'] for i in area['indicators'] for d in i['documents_read']}
    names |= set(area['documents_searched']['names'])
    found = []
    for name in sorted(names, key=lambda n: len(_loose(n)), reverse=True):
        bare = _loose(re.sub(r'^the ', '', name, flags=re.I))
        bare = re.sub(r' files$', '', bare)   # "the Criteria 3 files" is named by "Criteria 3"
        if bare and f' {bare} ' in text:
            found.append(name)
            text = text.replace(f' {bare} ', ' ')
    return found


def _with_documents(scope, area, title=''):
    """Let a field name any document searched or read for the area (by name, with its pages), and use its title."""
    names = list(area['documents_searched']['names'])
    pages = set()
    for indicator in area['indicators']:
        for document in indicator['documents_read']:
            names.append(document['document'])
            pages |= {str(p) for p in document.get('pages') or []}
    scope['names'] = sorted({_norm(n) for n in names if n} | set(scope['names']), key=len, reverse=True)
    scope['pages'] = set(scope['pages']) | pages
    scope['numbers'] = set(scope['numbers']) | {str(area['documents_searched']['count'])}
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
        if credited and entry['found'] and not SECOND_PERSON.search(entry['found']):
            problems.append(f'{cid}: found must speak to the college as "you" or "your".')
        if entry['looked'] and len(_documents_named(entry['looked'], area)) > MAX_LOOKED:
            problems.append(f'{cid}: looked names more than {MAX_LOOKED} documents; name the most relevant.')
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
        if not any(SECOND_PERSON.search(entry[f]) for f in FIELDS):
            problems.append(f'{code}: speak to the college as "you" or "your".')
        verdict = _topic_verdict(code, summaries[code].get('verdict'), scope, problems)
        errors += problems
        if not problems:
            passed['indicators'][code] = {**entry, **({'verdict': verdict} if verdict else {})}
    everything = [r for i in area['indicators'] for r in i['requirements']]
    totals = {k: sum(i['counts'][k] for i in area['indicators']) for k in area['indicators'][0]['counts']} \
        if area['indicators'] else {}
    scope = _summary_scope(everything, totals)
    _with_documents(scope, area, area['name'])
    raw = (output or {}).get('area') or {}
    entry, problems = _clean(raw), []
    _check('area', entry, scope, problems)
    if not any(SECOND_PERSON.search(entry[f]) for f in FIELDS):
        problems.append('area: speak to the college as "you" or "your".')
    card, card_problems = _check_card(raw, area, given, scope)
    problems += card_problems
    errors += problems
    if not problems:
        passed['area'] = {**entry, **card}
    return passed, errors


def _topic_verdict(code, value, scope, problems):
    """A key indicator's verdict (explanations-0.6): one or two sentences in the third person, no numbers, codes or
    widening beyond its quotations. Appends to problems; returns the cleaned text."""
    verdict = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not verdict:   # left out: the detailed report prints the topic's plain line, and readiness warns
        return verdict
    if len(verdict) > MAX_VERDICT_CHARS or len(re.findall(r'[.!?](?:\s|$)', verdict)) > 2:
        problems.append(f'{code}: verdict is at most two sentences.')
    if NUMBER.search(verdict) or PERCENT.search(verdict) or MACHINERY.search(verdict):
        problems.append(f'{code}: verdict carries no numbers, codes or internal terms.')
    if SECOND_PERSON.search(verdict):
        problems.append(f'{code}: the verdict is in the third person, not "you".')
    sub = []   # widening, quotations and the rest: the summaries' own check
    _check(f'{code} verdict', {'found': '', 'text': verdict, 'looked': '', 'next_step': ''}, scope, sub)
    problems += [p for p in sub if 'the institution' not in p]
    return verdict


_CARD_STOP = {'which', 'their', 'there', 'these', 'those', 'about', 'other', 'under', 'within', 'shows', 'where',
              'while', 'every', 'being', 'would', 'should', 'could', 'after', 'before'}


def _check_card(raw, area, given, scope):
    """The area card (AREA_FIELDS): the verdict stands alone in the third person, the headline is short and has no
    numbers, every strength names something its one quotation names, every gap is about practices not shown in
    full. Returns (card, problems)."""
    problems = []
    word = area.get('institution_word') or 'institution'
    clean = lambda v: re.sub(r'\s+', ' ', str(v or '')).strip()
    verdict, headline = clean(raw.get('verdict')), clean(raw.get('headline'))
    if not verdict.lower().startswith(f'the {word} '):
        problems.append(f'area: verdict must begin "The {word}".')
    if len(verdict) > MAX_VERDICT_CHARS or len(re.findall(r'[.!?](?:\s|$)', verdict)) > 2:
        problems.append('area: verdict is at most two sentences.')
    if not headline or len(headline) > MAX_HEADLINE_CHARS:
        problems.append(f'area: headline is one short sentence (at most {MAX_HEADLINE_CHARS} characters).')
    if NUMBER.search(headline) or NUMBER.search(verdict):
        problems.append('area: verdict and headline carry no numbers.')
    for where, value in (('verdict', verdict), ('headline', headline)):
        if MACHINERY.search(value) or PERCENT.search(value):
            problems.append(f'area: {where} uses codes, internal terms or a percentage.')
        if SECOND_PERSON.search(value) and where == 'verdict':
            problems.append('area: the verdict is in the third person ("The ... has"), not "you".')
        for phrase in WIDENING.findall(value):
            if _norm(phrase) not in scope['text']:
                problems.append(f'area: {where} says "{phrase}", wider than its quotations show.')
    strengths = []
    for n, item in enumerate((raw.get('strengths') or [])[:MAX_CARD_ITEMS + 1], 1):
        text, cid, qid = clean((item or {}).get('text')), (item or {}).get('condition_id'), (item or {}).get('quote_id')
        requirement = given.get(cid)
        quote = next((q for q in (requirement or {}).get('quotations') or [] if q['id'] == qid), None)
        if n > MAX_CARD_ITEMS:
            problems.append(f'area: at most {MAX_CARD_ITEMS} strengths.')
            break
        if requirement is None or quote is None:
            problems.append(f'area: strength {n} must cite a quotation given (condition_id and quote_id).')
            continue
        if requirement['result'] not in ('shown in full', 'partly shown'):
            problems.append(f'area: strength {n} cites a requirement with no credit.')
        shared = {w for w in re.findall(r'[a-z]{5,}', _norm(text)) if w not in _CARD_STOP} & \
            set(re.findall(r'[a-z]{5,}', _norm(quote['text'])))
        if len(shared) < 2 and not any(_norm(sp) in _norm(quote['text']) for sp in _spans(text)):
            problems.append(f'area: strength {n} must name what its quotation names, in its words.')
        one = _scope([requirement])
        _with_documents(one, area)
        sub = []
        _check(f'area strength {n}', {'found': '', 'text': text, 'looked': '', 'next_step': ''}, one, sub)
        problems += [p for p in sub if 'the institution' not in p]
        strengths.append({'text': text, 'condition_id': cid, 'quote_id': qid, 'source': quote['document']})
    credited = any(r['result'] in ('shown in full', 'partly shown') and r['quotations'] for r in given.values())
    if credited and not strengths:
        problems.append('area: give two or three strengths; something in this area has credit.')
    gaps = []
    for n, item in enumerate((raw.get('gaps') or [])[:MAX_CARD_ITEMS + 1], 1):
        text = clean((item or {}).get('text'))
        ids = [c for c in (item or {}).get('condition_ids') or [] if isinstance(c, str)]
        if n > MAX_CARD_ITEMS:
            problems.append(f'area: at most {MAX_CARD_ITEMS} gaps.')
            break
        if not text or not ids or any(c not in given or given[c]['result'] == 'shown in full' for c in ids):
            problems.append(f'area: gap {n} must name the requirements not shown in full that it is about.')
            continue
        sub = []
        _check(f'area gap {n}', {'found': '', 'text': text, 'looked': '', 'next_step': ''}, scope, sub)
        problems += [p for p in sub if 'the institution' not in p]
        gaps.append({'text': text, 'condition_ids': ids})
    if not gaps and any(r['result'] != 'shown in full' for r in given.values()):
        problems.append('area: give two or three gaps; not everything in this area is shown in full.')
    return {'verdict': verdict, 'headline': headline, 'strengths': strengths, 'gaps': gaps}, problems


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
    documents = [d['document'] for d in indicator['documents_read'][:MAX_LOOKED]]
    looked = '' if full else (f'We searched every document you uploaded; the closest passages were in '
                              f'{_list(documents)}.' if documents else 'We searched every document you uploaded.')
    missing = requirement['still_missing']
    # The reports and screens put "Next step:" in front of it themselves.
    next_step = '' if full else (f'Show {_lower_first(missing[0]).rstrip(".")}.' if missing else '')
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
    return {'found': '', 'text': f"Of the {len(results)} requirements under {name} in your assessment, {_list(pieces)}.",
            'looked': '',
            'next_step': 'The next steps under each requirement show what would add most.' if rest or part else '',
            'fallback': True}


# ------------------------------------------------------------------ a run


def next_steps_stored(run_id, event_id):
    from .next_steps import stored
    return stored(run_id, event_id)


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
            'names': document_names(inputs.get('manifest')), 'groups': document_groups(inputs.get('manifest')),
            'merge': (inputs.get('second_layer') or {}).get('merge') or [],
            'institution_word': institution_word(inputs.get('profile')),
            'plan': build_plan(inputs['rubric'], records),
            # A weak area's card lists its step's starting points (closest_on_card): the writer sees them.
            'area_scores': {p['code']: p['score'] for p in
                            ((event.payload.get('result') or {}).get('documented') or {}).get('pillars') or []},
            'next_steps': next_steps_stored(str(run.pk), event.pk)[1]}


def _explain_area(area, target, model, take_call, skip_error=None):
    """One area: up to two calls, the checks, and fallbacks for whatever still fails. take_call() reserves one call
    under the explanation's own cap (False when the cap is spent). skip_error: a test for request failures (a timeout,
    a malformed reply) that leave this area on the plain fallback text instead of failing the whole job; anything
    else (a spent budget, a cancelled job) still stops it."""
    payload = area_input(area, target)
    ids = [r['condition_id'] for i in payload['indicators'] for r in i['requirements']]
    codes = [i['code'] for i in payload['indicators']]
    passed, errors, calls, fallbacks = {'area': None, 'indicators': {}, 'requirements': {}}, [], 0, []
    content = json.dumps(payload, ensure_ascii=False)
    for attempt in range(2):
        if not take_call():
            break
        if attempt and errors:
            content = json.dumps({**payload, 'your_previous_answer_had_these_problems': errors[:40],
                                  'instruction': 'Write the whole answer again, fixing every problem.'},
                                 ensure_ascii=False)
        calls += 1
        try:
            response = model(SYSTEM_PROMPT, content, schema(ids, codes), 'score_explanations')
        except Exception as exc:
            if skip_error is None or not skip_error(exc):
                raise
            errors = [f'request failed: {type(exc).__name__}']
            break
        checked, errors = validate(payload, response)
        # Keep the best of each entry across attempts: an entry that passed once stays.
        passed['requirements'].update({k: v for k, v in checked['requirements'].items()
                                       if k not in passed['requirements']})
        passed['indicators'].update({k: v for k, v in checked['indicators'].items() if k not in passed['indicators']})
        passed['area'] = passed['area'] or checked['area']
        if len(passed['requirements']) == len(ids) and len(passed['indicators']) == len(codes) and passed['area']:
            errors = []
            break
    for indicator in payload['indicators']:
        for requirement in indicator['requirements']:
            cid = requirement['condition_id']
            if cid not in passed['requirements']:
                passed['requirements'][cid] = fallback_requirement(requirement, indicator)
                fallbacks.append(cid)
        if indicator['code'] not in passed['indicators']:
            passed['indicators'][indicator['code']] = fallback_summary(indicator['requirements'], indicator['name'])
            fallbacks.append(indicator['code'])
    if not passed['area']:
        passed['area'] = fallback_summary([r for i in payload['indicators'] for r in i['requirements']],
                                          payload['name'])
        fallbacks.append(area)
    return {'passed': passed, 'errors': errors[:40], 'calls': calls, 'fallbacks': fallbacks}


def explain(target, model, *, max_calls=None, concurrency=1, skip_error=None):
    """{'version', 'run_id', 'event_id', 'areas': {code: ...}, 'indicators': {code: ...}, 'requirements': {cid: ...},
    'fallbacks': [ids], 'calls': n}. model: the depth code's interface (system, content, schema, name) -> dict.
    concurrency: areas written side by side (the assessment's indicator concurrency in the job); the meter's
    reservations are already serialised, and each worker thread gets its own database connection."""
    import threading
    out = {'version': VERSION, 'run_id': target['run_id'], 'event_id': target['event_id'], 'areas': {},
           'indicators': {}, 'requirements': {}, 'fallbacks': [], 'calls': 0, 'errors': {}}
    areas = []
    for indicator in target['rubric']['indicators']:
        if indicator.get('pillar') not in areas:
            areas.append(indicator.get('pillar'))
    lock, taken = threading.Lock(), [0]

    def take_call():
        with lock:
            if max_calls is not None and taken[0] >= max_calls:
                return False
            taken[0] += 1
            return True

    if concurrency <= 1:
        results = [_explain_area(area, target, model, take_call, skip_error) for area in areas]
    else:
        import contextvars
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connections

        def run_in_thread(area):
            try:
                return _explain_area(area, target, model, take_call, skip_error)
            finally:
                connections.close_all()
        executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='capability-explain')
        try:
            futures = [executor.submit(contextvars.copy_context().run, run_in_thread, area) for area in areas]
            results = [future.result() for future in futures]
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        executor.shutdown(wait=True)
    for area, result in zip(areas, results):   # assembled in area order, whatever finished first
        if result['errors']:
            out['errors'][area] = result['errors']
        out['calls'] += result['calls']
        out['fallbacks'] += result['fallbacks']
        out['areas'][area] = {**result['passed']['area'], 'closest_seen': bool(closest_on_card(area, target))}
        out['indicators'].update(result['passed']['indicators'])
        out['requirements'].update(result['passed']['requirements'])
    return out


def import_cards(target, base, cards, written_by):
    """Area cards written outside the product (for example while the model keys are unavailable), on top of a
    stored payload's requirement, topic and area text: each card goes through the same checks as the model's
    (_check_card) against this run; a card that fails, or an area with none, keeps the area on the plain fallback, so
    the reports stay a draft for it (publication.readiness). Returns (payload, problems by area)."""
    out = {'version': VERSION, 'run_id': target['run_id'], 'event_id': target['event_id'],
           'areas': {}, 'indicators': dict(base.get('indicators') or {}),
           'requirements': dict(base.get('requirements') or {}), 'fallbacks': list(base.get('fallbacks') or []),
           'calls': 0, 'errors': {}, 'written_by': written_by,
           'base_version': base.get('version')}
    problems = {}
    areas = list(dict.fromkeys(i.get('pillar') for i in target['rubric']['indicators']))
    topics_wrong = {}
    for area in areas:
        topic_problems = []
        area_text = dict((base.get('areas') or {}).get(area) or {})
        for key in AREA_FIELDS:
            area_text.pop(key, None)
        card = cards.get(area)
        if not area_text or area_text.get('fallback'):
            problems[area] = ["the area's own text is on plain wording: write the explanations with the model"]
        elif card is None:
            problems[area] = ['no card was given']
        else:
            given_area = area_input(area, target)
            given = {r['condition_id']: r for i in given_area['indicators'] for r in i['requirements']}
            everything = [r for i in given_area['indicators'] for r in i['requirements']]
            totals = {k: sum(i['counts'][k] for i in given_area['indicators'])
                      for k in given_area['indicators'][0]['counts']}
            scope = _summary_scope(everything, totals)
            _with_documents(scope, given_area, given_area['name'])
            checked, errors = _check_card(card, given_area, given, scope)
            # Topic verdicts (explanations-0.6), checked like the model's; one that fails is left out (the detailed
            # report then prints the topic's plain line) and reported.
            for indicator in given_area['indicators']:
                code, wrong = indicator['code'], []
                text = (card.get('topics') or {}).get(code)
                if text is None:
                    continue
                one = _summary_scope(indicator['requirements'], indicator['counts'])
                _with_documents(one, given_area, indicator['name'])
                verdict = _topic_verdict(code, text, one, wrong)
                if wrong:
                    topic_problems.extend(wrong)
                elif code in out['indicators']:
                    out['indicators'][code] = {**out['indicators'][code], 'verdict': verdict}
            if errors:
                problems[area] = errors
            else:
                area_text.update(checked)
        if area in problems:
            area_text['fallback'] = True
            if area not in out['fallbacks']:
                out['fallbacks'].append(area)
        else:
            area_text.pop('fallback', None)
            out['fallbacks'] = [f for f in out['fallbacks'] if f != area]
        if topic_problems:
            topics_wrong[area] = topic_problems
        area_text['closest_seen'] = bool(closest_on_card(area, target))
        out['areas'][area] = area_text
    out['errors'] = {**problems, **{f'{a} topics': p for a, p in topics_wrong.items()}}
    return out, out['errors']


def latest(run):
    """The newest explanations stored for a run's current completed assessment, or None."""
    from apps.scoring.models import CapabilityExplanation
    # The id only: the completed payload is about 40 MB with its traces.
    event_id = run.events.filter(state='completed', payload__result__isnull=False).values_list('pk', flat=True).last()
    if event_id is None:
        return None
    row = CapabilityExplanation.objects.filter(run=run, event_id=event_id).order_by('-created_at').first()
    return row.payload if row else None


def attach(assessment, explanations, closed=False):
    """A copy of an assessment payload (records, result) with explanations attached where the front end reads them:
    records[].explanation, result.indicators[].explanation, result.documented.indicators[] and .pillars[]."""
    if not explanations:
        return assessment
    from .reserve import follow_up_note
    public = lambda e: {k: e.get(k) or None for k in FIELDS} if e else None

    def for_record(r):
        e = public(explanations['requirements'].get(r.get('condition_id')))
        # The credit held for follow-up answers (reserve.py); written here, not by the model; closed: the follow-up
        # stage is closed.
        note = follow_up_note(r, closed=closed)
        return {**e, 'follow_up': note} if e and note else e
    def for_indicator(code):
        # The topic's verdict (explanations-0.6) travels with it; a summary on plain wording is marked so.
        e = explanations['indicators'].get(code)
        out_e = public(e)
        if out_e is not None:
            out_e.update({'verdict': e.get('verdict') or None, 'fallback': bool(e.get('fallback'))})
        return out_e
    out = dict(assessment)
    out['records'] = [{**r, 'explanation': for_record(r)} for r in assessment.get('records') or []]
    result = dict(assessment.get('result') or {})
    if result.get('indicators'):
        result['indicators'] = [{**i, 'explanation': for_indicator(i.get('code'))} for i in result['indicators']]
    documented = result.get('documented')
    if isinstance(documented, dict):
        documented = dict(documented)
        documented['indicators'] = [{**i, 'explanation': for_indicator(i.get('code'))}
                                    for i in documented.get('indicators') or []]
        def for_area(code):
            e = explanations['areas'].get(code)
            out_e = public(e)
            if out_e is not None:
                out_e.update({k: e.get(k) for k in AREA_FIELDS if e.get(k)})
                out_e['fallback'] = bool(e.get('fallback'))
                out_e['closest_seen'] = bool(e.get('closest_seen'))
            return out_e
        documented['pillars'] = [{**p, 'explanation': for_area(p.get('code'))} for p in documented.get('pillars') or []]
        result['documented'] = documented
    out['result'] = result
    out['explanations_version'] = explanations.get('version')
    return out
