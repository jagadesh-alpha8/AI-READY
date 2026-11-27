"""Compact re-judge for follow-up answers (compact-1). Design: claude.ai project doc
claude/ai-ready-compact-rejudge-design-27-nov.md.

The whole-packet re-judge (layer2.fixed_contexts) sends a key indicator's Stage 1 packet again with up to 12,000
characters of the college's material at the end: 8% of a request near its 100,000-token line. Compact mode judges
one requirement per request on a packet built around what the college sent:

| group                     | what                                                                   | cap     |
|---------------------------|------------------------------------------------------------------------|---------|
| sent with this answer     | the whole document if it fits; else pages the answer names, then pages | 40,000  |
|                           | the map tags for the requirement, then pages matching the answer and   |         |
|                           | the parts' wording. Whole pages.                                       |         |
| pointed to by the college | held pages (#111) and corpus pages the answer's words found            | 12,000  |
| cited so far              | every passage any pass cited for the requirement at Stage 1            | none    |
| tagged, not cited         | the requirement's map-tagged passages, direct before supporting        | 12,000  |
| targeted search           | all the college's documents, searched with the answer's words, only    | 8,000   |
|                           | when a gate part is short or the answer names a page                   |         |

At most 80,000 characters in all. Two rules hold (design, "Two rules"): only text this requirement's judge has not
seen, or text the college pointed at, can move a score (the merge's rule: layer2.merge_new_evidence against the
Stage 1 packet); and a page is judged to the same standard wherever it comes from (same judge, credit rule and
quotation check).

Pages are matched to the run's own by text (whitespace cleaned, nothing else), and each page the college sent or
pointed at is in one of three states for each part of the requirement: never reached its judge (new evidence),
reached it and not cited for the part (held: a rise needs every pass to cite it), or already cited for the part (no
re-judge, unless it was cited only as partly shown and the college's answer, shown to the judge, says what the
document is: then one second look under the every-pass rule).

A pass raises a part only where it cites new or pointed text for it (per_pass); every other pass keeps the current
finding. The same pages for the same requirement reuse the stored judgment (RejudgeLook), with one fresh look when
the stored result was not a clean reading. Settings are frozen per run (FollowUpSettings): packet (whole or
compact), other requirements (on or off), typed answer (shown or hidden).
"""
import hashlib
import json
import re

from django.conf import settings as django_settings

PACKET_VERSION = 'compact-1'
SETTINGS_VERSION = 'follow-up-settings-1'
LOOK_VERSION = 'look-1'
CAPS = {'sent': 40000, 'pointed': 12000, 'tagged': 12000, 'search': 8000, 'total': 80000}
ROLES = {'sent': 'sent_with_answer', 'pointed': 'pointed_by_college', 'cited': 'cited_so_far',
         'tagged': 'tagged_not_cited', 'search': 'targeted_search'}
STATES = ('never_reached', 'held', 'cited')
PACKETS = ('whole', 'compact')
TYPED = ('shown', 'hidden')
STATEMENT_NOTE = ('The college wrote this about what it sent. It may say what a document is and where to look. It is '
                  'not evidence: every finding must stand on quoted passage text, and a fact no passage shows stays '
                  'not found. Never quote this statement.')
NAMED_PAGE = re.compile(r'\b(?:pages?|pp?\.|pg\.?)\s*(\d{1,4})(?:\s*(?:-|–|to|and|&)\s*(\d{1,4}))?', re.I)


# ------------------------------------------------------------------ settings


def current_settings():
    packet = getattr(django_settings, 'REJUDGE_PACKET', 'whole')
    typed = getattr(django_settings, 'REJUDGE_TYPED_ANSWER', 'hidden')
    if packet not in PACKETS or typed not in TYPED:
        raise ValueError('REJUDGE_PACKET must be whole or compact, REJUDGE_TYPED_ANSWER shown or hidden.')
    return {'version': SETTINGS_VERSION, 'packet': packet,
            'other_requirements': bool(getattr(django_settings, 'REJUDGE_OTHER_REQUIREMENTS', False)),
            'typed_answer': typed}


def frozen_settings(run_ref):
    """The run's follow-up settings, frozen the first time they are read (question planning, the follow-up page, or
    a re-judge). A run not in this database gets the current ones, unfrozen."""
    from ..models import FollowUpSettings
    from .layer2_service import _run
    if _run(run_ref) is None:
        return current_settings()
    row, _ = FollowUpSettings.objects.get_or_create(run_ref=str(run_ref), defaults=current_settings())
    return {'version': row.version, 'packet': row.packet, 'other_requirements': row.other_requirements,
            'typed_answer': row.typed_answer}


# ------------------------------------------------------------------ pages


def page_key(text):
    """Identical page text after whitespace clean-up is the same page; anything else is new (design, step 2)."""
    return hashlib.sha256(' '.join(str(text or '').split()).encode()).hexdigest()


def twins(pages, frozen):
    """{page id: the run's own page id with the same text} for pages the college sent."""
    by_key = {}
    for source in frozen:
        by_key.setdefault(page_key(source.get('text')), source['id'])
    return {p['id']: by_key.get(page_key(p.get('text')), p['id']) for p in pages}


def _part_cites(part):
    from .layer2 import _pass_citations
    return {c.get('source_id') for cites in _pass_citations(part) for c in cites or []}


def _related(part):
    from .layer2 import _pass_values
    found = _pass_values(part, 'credited_as')
    return 'related' in found and 'full' not in found


def states(record, packet, page_ids):
    """{page id: {part id: state}} for the run's own page ids (after twins), per part of the requirement."""
    reached = {w.get('id') for w in packet or ()}
    out = {}
    for pid in page_ids:
        row = {}
        for part in (record or {}).get('parts') or []:
            if pid in _part_cites(part):
                row[part['id']] = 'cited'
            elif pid in reached:
                row[part['id']] = 'held'
            else:
                row[part['id']] = 'never_reached'
        out[pid] = row or {'-': 'held' if pid in reached else 'never_reached'}
    return out


def needs_rejudge(page_states, record, *, typed_shown, identifies):
    """True when some page can still move a part: it never reached the judge or is held for some part; or it is cited
    only as partly shown for a part and the college's answer, shown to the judge, says what the document is
    (decision 2, 15:44)."""
    parts = {p['id']: p for p in (record or {}).get('parts') or []}
    for row in page_states.values():
        for part_id, state in row.items():
            if state in ('never_reached', 'held'):
                return True
            if state == 'cited' and typed_shown and identifies and part_id in parts and _related(parts[part_id]):
                return True
    return False


def named_pages(text):
    """Page numbers an answer names ("page 12", "pp. 3-5")."""
    out = set()
    for a, b in NAMED_PAGE.findall(text or ''):
        first = int(a)
        last = int(b) if b else first
        if 0 < first <= last <= first + 50:
            out.update(range(first, last + 1))
    return out


# ------------------------------------------------------------------ the packet


def _whole(source, role, **extra):
    return {'id': source['id'], 'document_id': source.get('document_id'), 'page_number': source.get('page_number'),
            **({'filename': source['filename']} if source.get('filename') else {}),
            'text': source['text'], 'text_offset': 0, 'evidence_role': role, **extra}


def _score(query, sources):
    from .layer2 import _lexical
    if not query.strip() or not sources:
        return [0.0] * len(sources)
    return _lexical(query, [s['text'] for s in sources])


def _tags_for(cid, tags_by_key, source):
    entry = (tags_by_key or {}).get(_map_hash(source.get('text'))) or {}
    return [t for t in entry.get('tags') or [] if cid in (t.get('requirements') or [])
            and t.get('strength') in ('direct', 'supporting')]


def _map_hash(text):
    from apps.evidence_map import spec
    return spec.text_hash(text or '')


class _Packet:
    def __init__(self, total):
        self.windows, self.total, self.used, self.seen = [], total, 0, set()

    def room(self, cap_left):
        return max(0, min(cap_left, self.total - self.used))

    def add(self, window, cap_left):
        """Add a window if it fits (a page bigger than the room is cut to it). Returns the characters added."""
        key = (window['id'], window.get('text_offset', 0))
        if key in self.seen or (window['id'], 0) in self.seen and window.get('text_offset', 0) == 0:
            return 0
        room = self.room(cap_left)
        if room < 200:
            return 0
        text = window['text'][:room]
        self.seen.add(key)
        self.windows.append({**window, 'text': text})
        self.used += len(text)
        return len(text)

    def has_page(self, pid):
        return any(k[0] == pid for k in self.seen)


def build(cid, spec_parts, record, stage1_packet, *, sent, pointed, answers, tags_by_key, corpus, caps=None,
          short_gate=False):
    """(packet windows, pages) for one requirement. sent: the pages of documents the college sent for it (source
    dicts, the run's own page ids where the text matched); pointed: windows it pointed at (held pages, corpus search
    hits); answers: its typed answers; tags_by_key: the map's tags by page text hash (the run's frozen map plus the
    upload's own); corpus: the college's documents (the run's frozen pages). pages: per group the page ids taken, per
    sent document the pages read and how many it has, and `partial` documents (not every page read)."""
    caps = {**CAPS, **(caps or {})}
    packet = _Packet(caps['total'])
    query = ' '.join(list(answers) + [p.get('full') or '' for p in spec_parts or []])
    named = set().union(*[named_pages(a) for a in answers]) if answers else set()
    taken = {group: [] for group in ROLES}

    # 1. Sent with this answer: whole documents if they all fit, else named pages, tagged pages, then by words.
    documents = {}
    for source in sent:
        documents.setdefault(str(source.get('document_id')), []).append(source)
    size = sum(len(s['text']) for s in sent)
    if size <= caps['sent']:
        order = list(sent)
    else:
        scores = _score(query, sent)
        rank = {s['id']: n for n, s in enumerate(sent)}

        def priority(n):
            source = sent[n]
            tags = _tags_for(cid, tags_by_key, source)
            strength = 0 if any(t['strength'] == 'direct' for t in tags) else 1 if tags else 2
            return (0 if source.get('page_number') in named else 1, strength, -scores[n], rank[source['id']])
        order = [sent[n] for n in sorted(range(len(sent)), key=priority)]
    used = 0
    for source in order:
        added = packet.add(_whole(source, ROLES['sent']), caps['sent'] - used)
        if added:
            used += added
            taken['sent'].append(source['id'])
    read = {doc: sorted(s.get('page_number') or 0 for s in pages if s['id'] in taken['sent'])
            for doc, pages in documents.items()}
    totals = {doc: len(pages) for doc, pages in documents.items()}
    partial = sorted(doc for doc in documents if len(read[doc]) < totals[doc])
    missed_named = sorted({n for doc in partial for n in named if n not in read[doc]
                           and any(s.get('page_number') == n for s in documents[doc])})

    # 2. Pointed to by the college.
    used = 0
    for window in pointed:
        added = packet.add({**window, 'evidence_role': ROLES['pointed'], 'pointed_as': window.get('evidence_role')},
                           caps['pointed'] - used)
        if added:
            used += added
            taken['pointed'].append(window['id'])

    # 3. Cited so far: every passage any pass cited for this requirement (Stage 1, or the current finding).
    quotes = {}
    for part in (record or {}).get('parts') or []:
        from .layer2 import _pass_citations
        for cites in _pass_citations(part):
            for c in cites or []:
                quotes.setdefault(c.get('source_id'), set()).add(' '.join(str(c.get('quote') or '').split()))
    for window in stage1_packet or ():
        wanted = quotes.get(window.get('id'))
        if not wanted:
            continue
        text = ' '.join((window.get('text') or '').split())
        if any(q and q in text for q in wanted) and packet.add({**window, 'evidence_role': ROLES['cited']},
                                                                caps['total']):
            taken['cited'].append(window['id'])

    # 4. Tagged, not cited: the run's map tags for this requirement, direct before supporting.
    from apps.evidence_map.packet import _tokens, window as map_window
    words = _tokens(query)
    tagged = []
    for source in corpus:
        for tag in _tags_for(cid, tags_by_key, source):
            tagged.append((0 if tag['strength'] == 'direct' else 1, source, tag))
    tagged.sort(key=lambda row: row[0])
    used = 0
    for _, source, tag in tagged:
        if packet.has_page(source['id']):
            continue
        start, end = map_window(source['text'], tag.get('quote') or '', words)
        window = {**_whole(source, ROLES['tagged']), 'text': source['text'][start:end], 'text_offset': start}
        added = packet.add(window, caps['tagged'] - used)
        if added:
            used += added
            taken['tagged'].append(source['id'])

    # 5. Targeted search of all the college's documents, when a gate part is short or the answer names a page.
    if (short_gate or named) and answers:
        from .layer2 import search_with_answer
        hits = search_with_answer(' '.join(answers), [], corpus, packet=packet.windows,
                                  corpus_limit=caps['search'])
        used = 0
        for window in hits:
            added = packet.add({**window, 'evidence_role': ROLES['search']}, caps['search'] - used)
            if added:
                used += added
                taken['search'].append(window['id'])
    return packet.windows, {'groups': taken, 'read': read, 'totals': totals, 'partial': partial,
                            'named': sorted(named), 'named_not_read': missed_named, 'chars': packet.used}


def statement_block(answers):
    """The typed-answer block (typed answer shown): [(text, for this question?)] -> the request's college_statement."""
    rows, seen = [], set()
    for text, own in answers:
        clean = ' '.join((text or '').split())[:2000]
        if clean and (clean, own) not in seen:
            seen.add((clean, own))
            rows.append({'text': clean, 'written_for': 'this requirement' if own else 'a different question'})
    return {'note': STATEMENT_NOTE, 'statements': rows} if rows else None


# ------------------------------------------------------------------ merge


def per_pass(twin, record, stage1_packet, pointers):
    """The re-judge's record with each pass's part findings kept only where that pass cites new text for the part
    (not in the Stage 1 packet) or the part rests on pointed text in every pass; otherwise the pass keeps the current
    finding (design, step 6). A lowered finding is left as judged: lowering is decided on every pass by the merge
    (layer2._contradicting). A part unlocked by a gate part newly shown on new text in the same pass keeps that pass's
    finding. When the current record has fewer passes than the re-judge, its passes are reused in turn."""
    from .layer2 import _gates, _in, is_new
    rank = {'not_found': 0, 'contradicted': 0, 'related': 1, 'digital_only': 1, 'full': 2}
    current = {p['id']: p for p in (record or {}).get('parts') or []}
    prefixes = ('', 'second_', 'third_')

    def passes_of(part):
        out = []
        for n, prefix in enumerate(prefixes):
            if n and prefix + 'credited_as' not in part:
                break
            cites = part.get('first_citations', part.get('citations')) if n == 0 else part.get(prefix + 'citations')
            out.append({'finding': part.get(prefix + 'finding'), 'credited_as': part.get(prefix + 'credited_as'),
                        'citations': list(cites or [])})
        return out

    twin_parts = twin.get('parts') or []
    gates = _gates(twin.get('condition_id'), twin_parts)
    judged = {p['id']: passes_of(p) for p in twin_parts}
    now = {pid: passes_of(current[pid]) if pid in current else [] for pid in judged}
    count = max([len(v) for v in judged.values()] or [0])

    def new_in(cites):
        return any(is_new(c, stage1_packet) for c in cites)

    def pointed_in(cites):
        return any(_in(c, pointers) for c in cites)

    pointed_all = {pid: bool(pointers) and all(pointed_in(p['citations']) for p in v) and len(v) == count
                   for pid, v in judged.items()}
    kept = {pid: [] for pid in judged}
    for n in range(count):
        unlocked = False
        for pid in judged:
            mine = judged[pid][n] if n < len(judged[pid]) else judged[pid][-1]
            old = now[pid][n % len(now[pid])] if now[pid] else {'finding': 'not_found', 'credited_as': 'not_found',
                                                                 'citations': []}
            rises = rank.get(mine['credited_as'], 0) > rank.get(old['credited_as'], 0)
            if pid in gates and rises and new_in(mine['citations']):
                unlocked = True
        for pid in judged:
            mine = judged[pid][n] if n < len(judged[pid]) else judged[pid][-1]
            old = now[pid][n % len(now[pid])] if now[pid] else {'finding': 'not_found', 'credited_as': 'not_found',
                                                                 'citations': []}
            rises = rank.get(mine['credited_as'], 0) > rank.get(old['credited_as'], 0)
            lowers = mine['finding'] == 'contradicted'
            qualifies = new_in(mine['citations']) or pointed_all[pid] or (unlocked and pid not in gates)
            kept[pid].append(mine if lowers or (rises and qualifies) else old)
    parts = []
    for part in twin_parts:
        rows = kept[part['id']]
        out = {k: v for k, v in part.items() if not any(k == p + f for p in prefixes
                                                       for f in ('finding', 'credited_as', 'citations'))
               and k != 'first_citations'}
        for n, row in enumerate(rows):
            prefix = prefixes[n]
            out[prefix + 'finding'] = row['finding']
            out[prefix + 'credited_as'] = row['credited_as']
            out[prefix + 'citations'] = row['citations']
        if len(rows) == 3:
            out['first_citations'] = rows[0]['citations']
        parts.append(out)
    return {**twin, 'parts': parts}


def split(twin, pages):
    """Part ids where some passes cite the given pages and not all: a rise that failed by one pass (fresh-look
    trigger)."""
    from .layer2 import _pass_citations
    out = []
    for part in twin.get('parts') or []:
        cites = [{c.get('source_id') for c in p or []} & set(pages) for p in _pass_citations(part)]
        if any(cites) and not all(cites):
            out.append(part['id'])
    return out


# ------------------------------------------------------------------ the store


def look_key(cid, page_keys, versions):
    return hashlib.sha256(json.dumps({'v': LOOK_VERSION, 'cid': cid, 'pages': sorted(page_keys),
                                      'versions': versions}, sort_keys=True).encode()).hexdigest()


def answer_hash(answers):
    texts = sorted({' '.join((a or '').split()) for a, _ in answers} - {''})
    return hashlib.sha256(json.dumps(texts).encode()).hexdigest() if texts else ''


def reuse(run_ref, cid, key, *, routes, answers_hash, typed_shown):
    """(stored twin or None, look, why): reuse a stored judgment of the same pages unless a fresh look is due: the
    stored result was a split, a partial read or a tagger failure and the college has sent or pointed at the pages
    again (a new answer or submission), or staff ordered one; at most one per look. A changed answer on the same
    pages, shown to the judge, re-judges once."""
    from ..models import RejudgeLook
    look = RejudgeLook.objects.filter(run_ref=str(run_ref), condition_id=cid, look_key=key).first()
    if look is None:
        return None, None, 'first look'
    again = sorted(set(routes) - set(look.routes or []))
    unclean = [k for k, v in (look.flags or {}).items() if v]
    if look.fresh_looks == 0 and unclean and (again or look.fresh_look_ordered):
        return None, look, 'fresh look (' + ', '.join(unclean) + ')'
    if look.fresh_looks == 0 and look.fresh_look_ordered:
        return None, look, 'fresh look ordered by staff'
    if typed_shown and answers_hash and answers_hash != look.answer_hash and look.answer_rejudges == 0:
        return None, look, 'changed answer'
    return look.twin, look, 'reused'


def store(run_ref, cid, key, look, why, *, twin, versions, answers_hash, statement, pages, flags, routes):
    from ..models import RejudgeLook
    if look is None:
        return RejudgeLook.objects.create(run_ref=str(run_ref), condition_id=cid, look_key=key, versions=versions,
                                          answer_hash=answers_hash, statement=statement or {}, twin=twin, pages=pages,
                                          flags=flags, routes=sorted(routes))
    look.twin, look.pages, look.flags, look.statement = twin, pages, flags, statement or {}
    look.routes = sorted(set(look.routes or []) | set(routes))
    if why.startswith('fresh look'):
        look.fresh_looks += 1
    elif why == 'changed answer':
        look.answer_rejudges += 1
        look.answer_hash = answers_hash
    look.save()
    return look


def order_fresh_look(run_ref, cid, reason):
    """Staff order the one fresh look for a requirement's stored looks, with a reason (nothing waits for this)."""
    from ..models import RejudgeLook
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('Give a reason for the fresh look.')
    return RejudgeLook.objects.filter(run_ref=str(run_ref), condition_id=cid, fresh_looks=0).update(
        fresh_look_ordered=reason)


# ------------------------------------------------------------------ what each document did


def _wording(cid, part_ids):
    from .part_judgment import _load
    spec = {p['id']: p for p in (_load()[0]['conditions'].get(cid) or {}).get('parts') or []}
    return [spec[p]['full'] for p in part_ids if p in spec]


def _shown(record):
    from .layer2 import _pass_values
    shown, missing = [], []
    for part in (record or {}).get('parts') or []:
        found = _pass_values(part, 'credited_as')
        (shown if found.count('full') * 2 > len(found) else missing).append(part['id'])
    return shown, missing


def lines(route, cid, *, asked, audit_row, final_record, documents, names, plan, unreadable, typed_shown):
    """Plain lines for the college about what each document did for one requirement (design, "Front-end text"),
    built from the final finding: about this college's documents, "not found in your documents", never "you do not
    have". Each line carries `staff` detail (page states, each pass's finding, the packet, reuse) for staff only."""
    out = []
    shown, missing = _shown(final_record)
    still = '; '.join(_wording(cid, missing)) or 'nothing more'
    showing = '; '.join(_wording(cid, shown))
    tail = 'the question still needs' if asked else 'that part of your assessment still needs'
    decision = (audit_row or {}).get('decision', '')
    req = f'"{(plan.get("requirement_text") or cid).rstrip(".")}"'
    plan.setdefault('lowered', {})[cid] = (audit_row or {}).get('lowered_parts') or []
    for doc in documents:
        name = names.get(doc) or 'this document'
        staff = {'requirement': cid, 'page_states': {p: s for p, s in (plan.get('states') or {}).items()
                                                     if plan.get('page_documents', {}).get(p) == doc},
                 'packet': plan.get('pages'), 'look': plan.get('why'), 'decision': decision,
                 'failed_by_one_pass': plan.get('split') or []}
        if doc in unreadable:
            out.append({'document_id': doc, 'requirement': cid, 'kind': 'could_not_read',
                        'text': f'We could not read {name}. Please send a copy with selectable text, or a clearer scan.',
                        'staff': staff})
            continue
        if plan.get('already'):
            counted = '; '.join(_wording(cid, plan.get('cited_parts') or [])) or 'this requirement'
            out.append({'document_id': doc, 'requirement': cid, 'kind': 'already_counted',
                        'text': f'Already counted for {req}: {name} was credited for: {counted}. Still needed: {still}.',
                        'staff': staff})
            continue
        line = {'document_id': doc, 'requirement': cid, 'staff': staff}
        rose = [p for p in (audit_row or {}).get('new_evidence_parts') or []] + list(
            (audit_row or {}).get('unlocked_parts') or [])
        numbers = plan.get('page_numbers') or {}
        if decision.startswith('not re-judged'):
            line.update(kind='not_checked', text=(
                f'We could not finish checking {name} for {req} this time. InGage will check it again before your '
                'final result.'))
        elif (audit_row or {}).get('lowered_parts'):
            before = (audit_row or {}).get('previous_credit')
            lowered = audit_row['lowered_parts']
            here = sorted({numbers.get(q.get('source_id')) for q in audit_row.get('contradicting_quotes') or []
                           if q.get('part') in lowered and numbers.get(q.get('source_id'))})
            files = plan.get('files') or {}
            earlier = sorted({f'page {numbers[c.get("source_id")]} of {files.get(c.get("source_id"), "your documents")}'
                              for p in plan.get('previous_parts') or [] if p.get('id') in lowered
                              for c in p.get('citations') or [] if numbers.get(c.get('source_id'))})
            line.update(kind='lowered', text=(
                f'{name}' + (f' (page {", ".join(str(n) for n in here)})' if here else '')
                + f' shows something different from what we counted before for {req}: '
                f'{"; ".join(_wording(cid, lowered))}. We had counted it at {round(100 * (before or 0))}%'
                + (f' from {", ".join(earlier)}' if earlier else ' from your earlier documents')
                + '. We now use what the documents show. If this is not right, send the document that settles it.'))
        elif decision == 'replaced' and rose:
            line.update(kind='counted' if asked else 'also_counted', text=(
                f'{"Counted" if asked else "Also counted"} for {req}: {name} shows '
                f'{"; ".join(_wording(cid, rose))}.' + (f' Still needed: {still}.' if missing else '')))
        elif missing:
            line.update(kind='read_again', text=(
                f'Read again for {req}: {name} ' + (f'shows {showing}, and ' if showing else 'did not show more, and ')
                + f'{tail}: {still}. That was not found in the documents you sent.'))
        else:
            line.update(kind='read_again', text=f'Read again for {req}: {name} shows everything this asks for.')
        if doc in (plan.get('pages') or {}).get('partial', []):
            pages = ', '.join(str(n) for n in (plan['pages']['read'] or {}).get(doc, []))
            out.append({'document_id': doc, 'requirement': cid, 'kind': 'partly_read', 'staff': staff,
                        'text': f'We read pages {pages} of {name}. If the page you mean is not among them, tell us the '
                                'page.'})
        out.append(line)
    if not documents and route.get('kind') == 'missing':
        if (plan.get('pages') or {}).get('named') and not plan.get('found_named'):
            out.append({'document_id': None, 'requirement': cid, 'kind': 'could_not_find', 'staff': {},
                        'text': 'We could not find the page or document you named. Please check the page number, or '
                                'attach the document.'})
        else:
            out.append({'document_id': None, 'requirement': cid, 'kind': 'no_document', 'staff': {},
                        'text': 'We have noted this. We can count it once a document shows it.'})
    for line in out:
        line['brief'] = brief(line, cid, plan=plan, final_record=final_record, names=names, asked=asked,
                              shown=shown, missing=missing)
    if plan.get('why') == 'reused':
        for line in out:
            line['text'] = 'We have already taken a second look at this document for this question. ' + line['text']
    return out


def brief(line, cid, *, plan, final_record, names, asked, shown, missing):
    """What the writer may use for one line: the requirement's text and its parts' wording (shown and still needed),
    what happened to the document, and the passages of that document the final finding cites, with page numbers.
    Never another college's text, and never the whole document."""
    from .layer2 import _pass_citations
    doc = line.get('document_id')
    numbers = plan.get('page_numbers') or {}
    owner = plan.get('page_documents') or {}
    quotes = []
    for part in (final_record or {}).get('parts') or []:
        for cites in _pass_citations(part):
            for c in cites or []:
                if doc and owner.get(c.get('source_id')) == doc and c.get('quote'):
                    row = {'page': numbers.get(c.get('source_id')), 'quote': ' '.join(str(c['quote']).split())[:400]}
                    if row not in quotes:
                        quotes.append(row)
    pages = plan.get('pages') or {}
    return {'kind': line.get('kind'), 'asked': asked, 'requirement': plan.get('requirement_text') or '',
            'shown': _wording(cid, shown), 'still_needed': _wording(cid, missing),
            'document': names.get(doc) if doc else None, 'quotations': quotes[:6],
            'pages_read': (pages.get('read') or {}).get(doc) if doc in (pages.get('partial') or []) else None,
            'lowered': _wording(cid, (plan.get('lowered') or {}).get(cid) or []) or None}


WRITER_VERSION = 'document-lines-1'
WRITER_PROMPT = """You write the short lines a college reads on its follow-up page after its final AI-readiness result:
for each document it sent, what that document did for one practice. The college is our customer. Write to it as
"you" and "your", plainly and warmly, and be specific about its own document.

Each line you receive has: kind (what happened: counted, also_counted for a practice it was not asked about,
already_counted, read_again, lowered, partly_read, could_not_read, could_not_find, no_document, not_checked), the
practice, the parts of it the documents show and the parts still needed (written for assessors: say what they mean in
everyday words, never copy them), the document's name, quotations from that document with their page numbers, and for
partly_read the pages that were read.

Rules:
1. Use only what is in the line. Never mention a document, page, number, activity or name that is not in it.
2. Name the document and, where given, the page. You may quote a few words from a quotation in double quotes, exactly
   as given; otherwise say it in your own words.
3. Never say or imply more than the kind says. read_again: say what the document shows, then what is still needed,
   "not found in the documents you sent", never "you do not have". lowered: say plainly and kindly what the document
   shows, that we now use it, and what would settle it.
4. No scores, percentages or credit; no requirement codes; nothing about how the assessment works inside.
5. One or two sentences, at most 60 words."""


def writer_schema(ids):
    return {'type': 'object', 'additionalProperties': False, 'required': ['lines'],
            'properties': {'lines': {'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False, 'required': ['id', 'text'],
                'properties': {'id': {'type': 'string', 'enum': sorted(ids)}, 'text': {'type': 'string'}}}}}}


_CODE = re.compile(r'\bAIQIF|\b[A-Z]\d\.\d\.[A-Z]\d\b')
_QUOTED = re.compile(r'"([^"]{3,})"|“([^”]{3,})”')
_NUMBER = re.compile(r'\d+')
_BANNED = ('you do not have', "you don't have", '%', 'percent', 'credit', 'score', 'model', 'packet', 'rubric')


def check_line(text, line):
    """Problems with a written line ([] when it may be shown): codes, quotations not in its passages, numbers not in
    its input, banned phrases, length."""
    problems = []
    b = line.get('brief') or {}
    source = json.dumps(b, ensure_ascii=False)
    plain = ' '.join((text or '').split())
    if not plain:
        return ['empty']
    if len(plain.split()) > 70:
        problems.append('longer than 70 words')
    if _CODE.search(plain):
        problems.append('a requirement code')
    lowered = plain.lower()
    problems += [f'says "{w}"' for w in _BANNED if w in lowered]
    quotes = ' '.join(' '.join(q['quote'].split()) for q in b.get('quotations') or [])
    for a, c in _QUOTED.findall(plain):
        if ' '.join((a or c).split()) not in quotes:
            problems.append(f'quotes "{a or c}", which is not in the document\'s passages')
    for n in _NUMBER.findall(plain):
        if n not in source:
            problems.append(f'the number {n} is not in the input')
    if b.get('document') and b['document'].rsplit('.', 1)[0].lower()[:12] not in lowered and b.get('kind') not in (
            'no_document', 'could_not_find'):
        problems.append('does not name the document')
    return problems


def write_lines(by_route, model):
    """Rewrite each line with the writer (one call per answer or submission, all its lines), keeping each written
    line only when check_line passes; the template stays otherwise (and says so on the line: written: False). A
    failed call keeps every template. by_route: {route: [line]}, changed in place; returns counts."""
    from collections import Counter
    counts = Counter()
    for route, rows in by_route.items():
        wanted = [(str(n), row) for n, row in enumerate(rows) if row.get('brief')]
        if not wanted:
            continue
        content = json.dumps({'lines': [{'id': i, **row['brief']} for i, row in wanted]}, ensure_ascii=False)
        try:
            answer = model(WRITER_PROMPT, content, writer_schema([i for i, _ in wanted]), 'document_lines') or {}
        except Exception as exc:   # never blocks publishing: the templates stand
            counts['call_failed'] += 1
            for _, row in wanted:
                row['written'] = False
                row.setdefault('staff', {})['writer'] = f'call failed ({type(exc).__name__})'
            continue
        written = {str(r.get('id')): r.get('text') for r in answer.get('lines') or []}
        for i, row in wanted:
            text = written.get(i)
            problems = check_line(text, row) if text else ['missing']
            if problems:
                row['written'] = False
                row.setdefault('staff', {})['writer'] = problems
                counts['template'] += 1
            else:
                row['text'], row['written'] = ' '.join(text.split()), True
                row.setdefault('staff', {})['writer'] = WRITER_VERSION
                counts['written'] += 1
    return counts


def college_view(lines_):
    """The lines without staff detail or the writer's input."""
    return [{k: v for k, v in line.items() if k not in ('staff', 'brief')} for line in lines_ or []]


def description(settings_):
    """'How we use your answers', above the first question, following the run's frozen settings; None while the run
    re-judges on the whole packet, which does not do what the description says (per-document lines, second looks)."""
    if settings_.get('packet') != 'compact':
        return None
    first = ('Attach a document to every answer that says something is in place. We can only count what a document '
             'shows. ' + ('What you write helps us find the right page and understand what the document is.'
                          if settings_.get('typed_answer') == 'shown' else 'What you write helps us find the right page.'))
    fourth = ('A document can count in more than one place. If it helps with another part of your assessment, we count '
              'it there too and tell you.' if settings_.get('other_requirements')
              else 'We consider each document for the question it is attached to.')
    return {'title': 'How we use your answers', 'version': settings_.get('version'), 'lines': [
        first,
        'We tell you what each document did. It counted, it was already counted, or we say what it shows and what is '
        'still missing.',
        'Think we missed something? Upload the document again or tell us the page. We will take a second look at it '
        'for that question and tell you what we found.',
        fourth,
        'Results can go down as well as up. If a document shows something different from what we counted before, we '
        'use what the documents show.']}


# ------------------------------------------------------------------ the re-judge


def _upload_tags(run, new_pages, documents, *, sprint_id):
    """(the map's tags by text hash for the new pages, document ids whose tagging failed, audit). Tags the uploads
    first when REJUDGE_TAG_UPLOADS is on and they have none (one tagging pass, metered as the evidence map's)."""
    from apps.evidence_map import packet as map_packet
    policy = ((run.inputs or {}).get('retrieval_policy') or {}) if run is not None else {}
    version, model = policy.get('map_version'), policy.get('map_model')
    if not new_pages or not version or not model:
        return {}, [], {'tagged': False, 'reason': 'no map on this run' if new_pages else 'no new pages'}
    frozen = map_packet.freeze(new_pages, map_version=version, model=model)
    audit = {'tagged': False, 'coverage_before': frozen['coverage']}
    untagged = frozen['coverage'].get('untagged') or 0
    failed = []
    if untagged and getattr(django_settings, 'REJUDGE_TAG_UPLOADS', True) and sprint_id is not None:
        from apps.documents.models import Document
        from apps.evidence_map import tagging
        from apps.sprints.models import Sprint
        from .layer2_service import _uuid
        names = {str(d.pk): d.original_filename or d.title
                 for d in Document.objects.filter(pk__in=[i for i in map(_uuid, documents) if i])}
        try:
            job = tagging.run(Sprint.objects.get(pk=sprint_id), documents=[n for n in names.values() if n],
                              max_cost_usd=getattr(django_settings, 'REJUDGE_TAG_MAX_COST_USD', '0.50'))
            audit.update(tagged=True, job=str(job.pk), status=job.status, spend_usd=str(job.spend_usd))
            if job.status == 'failed':
                failed = sorted(names)
        except Exception as exc:   # never fails the re-judge: pages are then chosen by words alone
            audit.update(error=f'{type(exc).__name__}: {exc}'[:300])
            failed = sorted(names)
        frozen = map_packet.freeze(new_pages, map_version=version, model=model)
        audit['coverage_after'] = frozen['coverage']
        if frozen['coverage'].get('failed') or frozen['coverage'].get('untagged'):
            hashes = {map_packet.spec.text_hash(p['text']) for p in new_pages}
            missing = hashes - set(frozen['pages'])
            failed = sorted(set(failed) | {str(p.get('document_id')) for p in new_pages
                                           if map_packet.spec.text_hash(p['text']) in missing})
    elif untagged:
        failed = sorted({str(p.get('document_id')) for p in new_pages})
    return frozen['pages'], failed, audit


def _other_routes(routes, records, rubric, pages_by_document, tags_by_key):
    """The other-requirements switch: for each document sent, the requirements below full credit the map tags its
    pages for (direct or supporting), beyond the ones its answer was routed to. [route]."""
    credit = {r['condition_id']: r.get('credit') or 0 for r in records}
    code_of = {c['id']: i['code'] for i in rubric['indicators'] for c in i['conditions']}
    out = []
    for route in routes:
        covered = set(route.get('conditions') or [])
        if route.get('conditions') is None:
            covered = {c for c, k in code_of.items() if k == route.get('indicator')}
        found = {}
        for doc in route.get('documents') or []:
            for page in pages_by_document.get(str(doc), []):
                entry = tags_by_key.get(_map_hash(page.get('text'))) or {}
                for tag in entry.get('tags') or []:
                    if tag.get('strength') not in ('direct', 'supporting'):
                        continue
                    for cid in tag.get('requirements') or []:
                        if cid in code_of and cid not in covered and credit.get(cid, 0) < 1:
                            found.setdefault(cid, set()).add(str(doc))
        for cid, docs in sorted(found.items()):
            out.append({'indicator': code_of[cid], 'conditions': [cid], 'windows': [], 'documents': sorted(docs),
                        'kind': 'other', 'from': route.get('from'), 'answer': route.get('answer') or '',
                        'other_of': route.get('indicator')})
    return out


def _combined_traces(traces):
    """One trace per key indicator from the per-requirement requests: the first request's trace, with every request's
    packet in source_excerpts and the others kept under compact_requests."""
    out = {}
    for trace in traces:
        code = trace.get('indicator')
        if code not in out:
            out[code] = {**trace, 'source_excerpts': list(trace.get('source_excerpts') or []), 'compact_requests': []}
            continue
        seen = {(w.get('id'), w.get('text_offset', 0)) for w in out[code]['source_excerpts']}
        out[code]['source_excerpts'] += [w for w in trace.get('source_excerpts') or []
                                         if (w.get('id'), w.get('text_offset', 0)) not in seen]
        out[code]['compact_requests'].append({k: v for k, v in trace.items() if k != 'source_excerpts'})
    return list(out.values())


def rejudge(*, export, service, result, records, traces, routes, run, run_ref, rubric, lowering, frozen, new_pages,
            evaluate_fn, sources, evaluate_options, rule, settings_, failed_documents=()):
    """The compact re-judge (layer2_service.rejudge_credit with the run's frozen packet setting 'compact'). Returns
    the same result shape as the whole-packet path, plus `compact` (per requirement: the page states, the packet, the
    stored look) and `document_lines` (per answer or submission: what each document did, with staff detail)."""
    from . import layer2
    from .layer2_service import run_sprint_id, with_depth
    from .part_judgment import _load, metadata
    from .layer2 import Layer2Error
    parts_spec = _load()[0]['conditions']
    by_id = {r['condition_id']: r for r in records}
    packets = {t['indicator']: list(t.get('source_excerpts') or []) for t in traces}
    typed_shown = settings_.get('typed_answer') == 'shown'
    sprint_id = run_sprint_id(run_ref)
    all_pages = list(frozen) + list(new_pages)
    pages_by_document = {}
    for page in all_pages:
        pages_by_document.setdefault(str(page.get('document_id')), []).append(page)
    new_documents = sorted({str(p.get('document_id')) for p in new_pages})
    upload_tags, tagger_failed, tag_audit = _upload_tags(run, new_pages, new_documents, sprint_id=sprint_id)
    tags_by_key = {**(((run.inputs or {}).get('evidence_map') or {}).get('pages') or {} if run is not None else {}),
                   **upload_tags}
    routes = list(routes)
    if settings_.get('other_requirements'):
        routes += _other_routes(routes, records, rubric, pages_by_document, tags_by_key)
    targets = layer2.credit_targets(records, rubric, [{**r, 'windows': r.get('windows') or []} for r in routes],
                                    include_full=lowering == 'apply')
    twin_of = twins(new_pages, frozen)
    frozen_by_id = {s['id']: s for s in frozen}
    names = {}
    if sprint_id is not None:
        from apps.documents.models import Document
        from .layer2_service import _uuid
        ids = {i for i in (_uuid(d) for r in routes for d in r.get('documents') or []) if i}
        names = {str(d.pk): d.original_filename or d.title for d in Document.objects.filter(pk__in=ids)}
    requirement_texts = {c['id']: c['text'] for i in rubric['indicators'] for c in i['conditions']}
    manifest_names = {str(m.get('document_id')): m.get('filename')
                      for m in ((run.inputs or {}).get('manifest') or [] if run is not None else [])}
    versions = {'credit_rule': rule, 'parts_prompt_hash': metadata()['parts_prompt_hash'], 'packet': PACKET_VERSION,
                'settings': settings_, 'model': getattr(service, 'model', None) or type(service).__name__}
    plans, jobs = {}, []
    for code, target in targets.items():
        if code not in packets:
            raise Layer2Error(f'No Stage 1 packet for {code} in the run trace: without it every page would read as '
                              'new, so the follow-up cannot be re-judged. Tell InGage staff.')
        for cid in target['conditions']:
            mine = [r for r in routes if r.get('indicator') == code and (r.get('conditions') is None
                                                                         or cid in r.get('conditions'))]
            documents = sorted({str(d) for r in mine for d in r.get('documents') or []})
            sent, page_documents = [], {}
            for doc in documents:
                for page in pages_by_document.get(doc, []):
                    own = frozen_by_id.get(twin_of.get(page['id'], page['id']), page)
                    if own['id'] not in page_documents:
                        sent.append({**own, 'document_id': page.get('document_id')})
                        page_documents[own['id']] = doc
            pointed = [w for r in mine for w in r.get('windows') or []
                       if w.get('evidence_role') in (layer2.HELD_ROLE, 'answer_search')]
            for window in pointed:
                page_documents.setdefault(window['id'], str(window.get('document_id')))
            unreadable = sorted(set(documents) & ({str(d) for d in failed_documents}
                                                  | {d for d in documents if not pages_by_document.get(d)}))
            answers = [(r.get('answer') or '', r.get('kind') != 'other') for r in mine if (r.get('answer') or '').strip()]
            record = by_id.get(cid) or {'condition_id': cid, 'credit': 0, 'parts': []}
            page_states = states(record, packets[code], [s['id'] for s in sent] + [w['id'] for w in pointed])
            plan = {'code': code, 'routes': mine, 'documents': documents, 'unreadable': unreadable,
                    'states': page_states, 'page_documents': page_documents, 'names': names,
                    'page_numbers': {p['id']: p.get('page_number') for p in all_pages},
                    'files': {p['id']: manifest_names.get(str(p.get('document_id'))) or names.get(str(p.get('document_id')))
                              or 'your documents' for p in all_pages},
                    'previous_parts': record.get('parts') or [],
                    'requirement_text': requirement_texts.get(cid, '')}
            plans[cid] = plan
            if not (sent or pointed):
                plan['skipped'] = 'nothing readable to judge'
                continue
            if not needs_rejudge(page_states, record, typed_shown=typed_shown, identifies=bool(answers)):
                plan['already'] = True
                plan['cited_parts'] = sorted({p for row in page_states.values() for p, s in row.items()
                                              if s == 'cited'})
                continue
            gates = layer2._gates(cid, record.get('parts') or [])
            short = any(any(f != 'full' for f in layer2._pass_values(p, 'credited_as'))
                        for p in record.get('parts') or [] if p['id'] in gates) or not record.get('parts')
            packet, pages = build(cid, (parts_spec.get(cid) or {}).get('parts') or [], record, packets[code],
                                  sent=sent, pointed=pointed, answers=[a for a, _ in answers],
                                  tags_by_key=tags_by_key, corpus=frozen, short_gate=short)
            plan['pages'] = pages
            plan['found_named'] = not pages['named'] or any(
                s.get('page_number') in pages['named'] for s in sent)
            statement = statement_block(answers) if typed_shown else None
            # Pointers for the every-pass rule: the held pages sent or pointed at, and (decision 2) pages cited only
            # as partly shown when the answer, shown to the judge, says what the document is.
            pointer_ids = {pid for pid, row in page_states.items()
                           if any(s == 'held' for s in row.values())}
            if typed_shown and answers:
                pointer_ids |= {pid for pid, row in page_states.items()
                                for part in record.get('parts') or []
                                if row.get(part['id']) == 'cited' and _related(part)}
            plan['pointers'] = [w for w in packets[code] if w.get('id') in pointer_ids]
            keys = [page_key(w['text']) for w in packet if w['evidence_role'] in (ROLES['sent'], ROLES['pointed'])]
            key = look_key(cid, keys, versions)
            seen = sorted({str(r.get('from')) for r in mine if r.get('from')})
            stored, look, why = reuse(run_ref, cid, key, routes=seen, answers_hash=answer_hash(answers),
                                      typed_shown=typed_shown)
            plan.update(key=key, why=why, routes_seen=seen, statement=statement)
            if stored is not None:
                plan['twin'] = stored
            else:
                plan['look'] = look
                jobs.append((code, cid, packet, statement))
    # Judge one requirement per request, a round at a time (each round: at most one requirement per key indicator).
    if evaluate_fn is None:
        from .evaluation import evaluate as evaluate_fn
    policy = {k: v for k, v in (export.get('retrieval_policy') or {}).items() if k != 'follow_up'} or None
    repair = run is not None and ((run.inputs or {}).get('execution_policy') or {}).get(
        'part_quote_repair') == 'quote-repair-v1'
    by_code = {i['code']: i for i in rubric['indicators']}
    rounds, new_traces = [], []
    for code, cid, packet, statement in jobs:
        for batch in rounds:
            if code not in batch:
                batch[code] = (cid, packet, statement)
                break
        else:
            rounds.append({code: (cid, packet, statement)})
    for batch in rounds:
        subset = {**rubric, 'indicators': [{**by_code[code], 'conditions': [c for c in by_code[code]['conditions']
                                                                            if c['id'] == cid]}
                                           for code, (cid, _, _) in batch.items()]}
        outcome = evaluate_fn(sources if sources is not None else all_pages, service=service,
                              population=export.get('population') or 'Not recorded',
                              reference_period=export.get('reference_period') or 'Not recorded', rubric=subset,
                              scope=export.get('scope'), reviewed_evidence=export.get('reviewed_evidence'),
                              retrieval_policy=policy, judgment='parts', agreement_passes=2, tie_break=True,
                              max_calls=len(batch), fixed_contexts={code: p for code, (_, p, _) in batch.items()},
                              statements={code: s for code, (_, _, s) in batch.items() if s},
                              **({'quote_repair': True} if repair else {}), **(evaluate_options or {}))
        new_traces += outcome.get('traces') or []
        for twin in outcome.get('records') or []:
            plan = plans.get(twin['condition_id'])
            if plan is None:
                continue
            plan['twin'] = twin
            if layer2._failed(twin):
                continue
            sent_ids = [pid for pid in plan['states']]
            flags = {'split': bool(split(twin, sent_ids)),
                     'partial': bool(plan['pages']['named_not_read']),
                     'tagger_failed': bool(set(plan['documents']) & set(tagger_failed))}
            plan['split'] = split(twin, sent_ids)
            store(run_ref, twin['condition_id'], plan['key'], plan.get('look'), plan['why'], twin=twin,
                  versions=versions, answers_hash=answer_hash([(r.get('answer') or '', True)
                                                               for r in plan['routes'] if r.get('answer')]),
                  statement=plan.get('statement'), pages=plan['pages'], flags=flags, routes=plan['routes_seen'])
    # Merge: each pass raises a part only on new or pointed text; then the existing merge and its lowering rules.
    twins_ = []
    pointers = {}
    for cid, plan in plans.items():
        twin = plan.get('twin')
        if twin is None:
            continue
        code = plan['code']
        twins_.append(twin if layer2._failed(twin) else per_pass(twin, by_id.get(cid), packets[code],
                                                                 plan.get('pointers') or []))
        pointers.setdefault(code, []).extend(w for w in plan.get('pointers') or [] if w not in pointers[code])
    from django.conf import settings as conf
    merged, merge_audit = layer2.merge_new_evidence(
        records, twins_, packets, rubric=rubric, lowering=lowering,
        max_per_document=conf.SECOND_LAYER_LOWERING_MAX_PER_DOCUMENT,
        source_documents={s['id']: s.get('document_id') for s in new_pages if s.get('id')},
        pointers={code: w for code, w in pointers.items() if w})
    merged, changes = with_depth(merged, run_ref)
    audit_by = {row['condition_id']: row for row in merge_audit}
    final_by = {r['condition_id']: r for r in merged}
    document_lines = {}
    for cid, plan in plans.items():
        for route in plan['routes']:
            asked = route.get('kind') != 'other' and (route.get('conditions') is None or cid in route['conditions'])
            rows = lines(route, cid, asked=asked, audit_row=audit_by.get(cid), final_record=final_by.get(cid),
                         documents=[str(d) for d in route.get('documents') or []], names=names, plan=plan,
                         unreadable=plan['unreadable'], typed_shown=typed_shown)
            document_lines.setdefault(str(route.get('from')), []).extend(rows)
    compact_audit = {'version': PACKET_VERSION, 'settings': settings_, 'tagging': tag_audit,
                     'tagger_failed': tagger_failed, 'requests': len(jobs), 'rounds': len(rounds),
                     'requirements': {cid: {'code': p['code'], 'documents': p['documents'], 'states': p['states'],
                                            'pages': p.get('pages'), 'look': p.get('why'), 'already': p.get('already'),
                                            'skipped': p.get('skipped'), 'split': p.get('split'),
                                            'unreadable': p['unreadable'],
                                            'statement_shown': bool(p.get('statement'))}
                                      for cid, p in plans.items()}}
    return {**result, 'targets': {code: t['conditions'] for code, t in targets.items()},
            'context_audit': {'compact': compact_audit}, 'merge': merge_audit, 'records': merged,
            'depth_changes': changes, 'contradictions': layer2.contradictions(merge_audit),
            'lowerings': layer2.lowerings(merge_audit), 'final_score': layer2.final_score(merged, rubric),
            'traces': _combined_traces(new_traces), 'new_sources': new_pages, 'compact': compact_audit,
            'document_lines': document_lines,
            'note': 'Publish with publish_final to make this the result reports use.'}
