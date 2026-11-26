"""The readiness picture for people: what the leadership and detailed reports show (Vijay and Siddharth, 23 Nov).

One function, build(), turns a report payload (report_views.CapabilityReportView) into a plain view: the readiness
level with its stars, the nine areas each with its own stars, strengths quoted from the college's own documents, the
areas to focus on, what the next level takes, and a short list of actions. No model calls, no internal terms: the
templates print what this returns. The front end's workspace/useResult.ts shapes the screens the same way.

Design: claude/ai-ready-leadership-report-design.md (AI Readiness project).
"""
import math
import re
from functools import lru_cache

from .action_plan import LEVEL_MEANINGS, tier_for, tiers
from .report_projection import AREA_DEFINITIONS, AREA_TITLES, PILLARS

STAGE_ORDER = {'F': 0, 'A': 1, 'O': 2}
STAGE_WORDS = {'F': 'Foundation', 'A': 'In use', 'O': 'Results'}


def _level_of(condition_id):
    return STAGE_ORDER.get(condition_id.rsplit('.', 1)[-1][:1], 3)


def _credit(record):
    if record is None:
        return 0.0
    if record.get('credit') is not None:
        return float(record['credit'])
    return 1.0 if record.get('state') == 'met' else 0.0


def _counted(record):
    """The share of a requirement's credit the headline counts now (reserve.record_factor), from the record's stamps."""
    from fractions import Fraction
    from .reserve import record_factor
    try:
        return float(record_factor(record))
    except Exception:   # an unstamped or older record: nothing held
        return 1.0


def _sentence(text):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[0].upper() + text[1:] if text else ''


SHORT_QUOTE = 6   # words: a shorter quotation ("The firewall is upgraded to") tells a reader nothing


_STOP_END = re.compile(r'\b(to|of|the|a|an|and|or|for|with|in|on|from|by|at|as|that|which|is|are|was|were|has|have|'
                       r'its|their|our|this|these|between|into|under|than|such|including|other|various|several|both|each|'
                       r'all|any|some|more|e\.g)$')   # lower case: "Dr. Banushri.A" ends a name, not a sentence
_TOKEN_CODE = re.compile(r'^(?:[\d.,:/%()-]+|[A-Z]|[A-Z0-9]*\d[A-Z0-9]*|[-–—:|])$')
_METRIC_HEADING = re.compile(r'\b(?:year-?wise|during the last (?:five|5) years)\b|'
                             r'^(?:(?:Average |Total )?(?:percentage|number) of|Details of)\b', re.I)   # NAAC metric titles


def unreadable(text):
    """Why a quotation can't be printed for a reader to make sense of, or '' when it can (audit, 26 Nov). The record's
    quotations are exact text from the college's documents, which is the point of them, but extraction leaves some
    that are only shards: a sentence cut off mid-clause ("The firewall is upgraded to"), a heading ("LIST OF DOCUMENTS
    UPLOADED"), a table's header row or a row whose cells came out empty or shifted ("Cycle Info: B | Accreditation:
    2.58 | | Grade: | CGPA:"), course codes and credit columns, or the extractor's own note on a table ("[Table 1 on
    page 37 -- columns: ...]"). A filled table row ("Name of the Collaborative Skill Partners: ImaginXP") is kept."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    words = t.split()
    if len(words) < SHORT_QUOTE:
        return 'too short'
    if t.startswith('[') or '-- columns:' in t:
        return 'extraction note'
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 'no words'
    cells = [c.strip() for c in t.strip('|').split('|')] if '|' in t else []
    if len(cells) >= 2:
        empty = sum(1 for c in cells if not c or re.fullmatch(r'[^:]*:\s*[-–]?', c) or re.fullmatch(r'[-–]+(?::\s*[-–]+)?', c))
        mirrored = sum(1 for c in cells if ':' in c and c.split(':', 1)[0].strip() == c.split(':', 1)[1].strip())
        # A row with a whole sentence in it reads as that sentence ("Dr.M.Ramprabha: | Two Days Workshop on ...").
        if (empty * 3 >= len(cells) or mirrored) and max(len(c.split()) for c in cells) < 12:
            return 'table row with empty or shifted cells'
    tokens = [w for w in re.split(r'[\s|]+', t) if w]
    if tokens and sum(1 for w in tokens if _TOKEN_CODE.match(w)) * 2 > len(tokens):
        return 'mostly codes and numbers'
    caps = sum(c.isupper() for c in letters) / len(letters)
    if caps > 0.7 and len(words) <= 8 and not cells:
        return 'heading'
    if not cells and re.match(r'[a-z]', t):
        return 'starts mid-sentence'
    if not cells and not re.search(r'[.!?)\u201d"]$', t):
        if t.count('(') > t.count(')'):
            return 'cut off mid-sentence'
        if _STOP_END.search(t.rstrip(',;:')) or re.search(r',\s*\w+$', t) or t.endswith(':'):
            return 'cut off mid-sentence'
        if _METRIC_HEADING.search(t) and not re.search(r'\d', t):
            return 'heading'
    return ''


def evidence_in(cites, pages, limit=3):
    """Where a practice's evidence is, for the detailed report's "Evidence found in" line (26 Nov: the report cites the
    document and page instead of printing the quotation): each document once, its pages together, in the order the
    citations come; at most `limit` documents. Unknown pages are left out."""
    by_doc = {}
    for c in cites or []:
        label = pages.get(str(c.get('source_id')))
        if not label:
            continue
        doc, _, page = label.rpartition(', page ')
        doc = doc or label
        got = by_doc.setdefault(doc, [])
        if page and page not in got:
            got.append(page)
    out = []
    for doc, got in list(by_doc.items())[:limit]:
        nums = sorted(got, key=lambda p: (not p.isdigit(), int(p) if p.isdigit() else 0, p))
        out.append(doc if not nums else f"{doc}, page {nums[0]}" if len(nums) == 1 else
                   f"{doc}, pages {', '.join(nums[:-1])} and {nums[-1]}")
    return out


_RESULT_WORDS = re.compile(r'^(?:this (?:requirement|practice) is |it is )?(?:shown in full|partly shown|not yet shown|'
                           r'not shown)\s*[,.;:]?\s*(?:(?:as|because|since|so)\b\s*)?', re.I)


def _why(text):
    """The written explanation of a partly credited practice, without its opening result words ("Partly shown, as
    annual assessments exist, but ..." reads "Annual assessments exist, but ..."): the report's badge already says
    it. Empty when nothing is left."""
    t = _RESULT_WORDS.sub('', re.sub(r'\s+', ' ', str(text or '')).strip()).strip()
    return t[:1].upper() + t[1:] if len(t.split()) >= 4 else ''


def _records_that_show(cid):
    """The kinds of record that would show a practice (the depth spec's "for example" list, also used in the
    follow-up questions), as one phrase: "a continuity or recovery exercise record"."""
    from .depth import spec
    try:
        forms = spec()['indicators'][cid.rsplit('.', 1)[0]]['conditions'][cid]['evidence_forms']
    except (KeyError, ValueError):
        return ''
    forms = [f.strip() for f in forms if f and f.strip()]
    if not forms:
        return ''
    text = forms[0] if len(forms) == 1 else f"{', '.join(forms[:-1])} or {forms[-1]}"
    return text[:1].upper() + text[1:]


STATUS_WORDS = {'shown': 'in place', 'partly': 'partly in place', 'missing': 'not found'}


def topic_line(rows):
    """A topic's plain line when its verdict is not written (explanations-0.6): the practices by status, in the
    rubric's order, named by their short labels. "Computing access is in place; usage records and fixing access
    problems are partly in place; no recovery test was found." """
    groups = {k: [r['label_short'] for r in rows if r['status'] == k] for k in ('shown', 'partly', 'missing')}
    low = lambda xs: [x[:1].lower() + x[1:] if not x[:2].isupper() else x for x in xs]
    join = lambda xs: xs[0] if len(xs) == 1 else f"{', '.join(xs[:-1])} and {xs[-1]}"
    parts = []
    for key in ('shown', 'partly'):
        if groups[key]:
            names = low(groups[key])
            parts.append(f"{join(names)} {'is' if len(names) == 1 else 'are'} {STATUS_WORDS[key]}")
    if groups['missing']:
        if not parts:
            return 'None of these practices was found in the documents.'
        parts.append(f"{join(low(groups['missing']))} {'was' if len(groups['missing']) == 1 else 'were'} not found")
    text = '; '.join(parts)
    return text[:1].upper() + text[1:] + '.'


def _readable_cite(cite, cites):
    """The citation a report prints: the chosen one, or, when its quotation can't be read on its own (unreadable),
    the most readable other quotation of the same requirement; with none, the source alone (its quotation blank)."""
    if cite is None or not unreadable(cite.get('quote')):
        return cite
    readable = [c for c in cites if c.get('quote') and not unreadable(c.get('quote'))]
    better = max(readable, key=lambda c: (quote_quality(c.get('quote'), 1), len(str(c.get('quote')))), default=None)
    return better or {**cite, 'quote': ''}


def _quote(text, limit=190):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[:cut.rfind(' ')] + '…'


def _first_sentences(text, count=2, limit=340):
    """The opening of an explanation, for the leadership report: at most two sentences, cut at a word."""
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\u201c])', text)
    return _quote(' '.join(parts[:count]), limit)


STAGE_STEP = {0: 'Set up', 1: 'Put in use', 2: 'Measure the results'}
_SENTENCE_VERB = re.compile(r'\b(is|are|was|were|has|have|had|provides?|conducts?|offers?|organi[sz]ed|established|'
                            r'approved|completed|trained|includes?|uses?|maintains?|supports?|introduced|adopted|'
                            r'enables?|covers?|focus(es|ing)?|participated|delivered|implemented|created|set up)\b', re.I)


_AI_WORDS = re.compile(r'\b(AI|artificial intelligence|machine learning|deep learning|generative|neural)\b', re.I)


def doc_label(filename):
    """A document's name as a reader sees it, the same everywhere (explanations._readable): no extension, single
    spaces, and a file uploaded under a group named with it ("criteria 3 - b (13).pdf" is "Criteria 3 (b)")."""
    from .explanations import _readable
    return _readable(str(filename or ''))[0]


def display_quote(text, limit=190):
    """The part of a quotation a card shows: whole sentences up to the limit, else cut at a word."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(t) <= limit:
        return t
    out = ''
    for sentence in re.split(r'(?<=[.!?])\s+', t):
        if len(out) + len(sentence) + 1 > limit:
            break
        out = f'{out} {sentence}'.strip()
    return out if len(out) >= 40 else _quote(t, limit)


def quote_quality(text, credit):
    """How well a quotation shows a strength to a reader: 0 for headings, titles and table rows; higher for a full
    sentence from a practice shown in full. Matches workspace/plain.ts on the screens."""
    t = display_quote(text)
    letters = [c for c in t if c.isalpha()]
    if len(t) < 40 or not letters or t.startswith('[') or t.count('|') >= 1 or re.match(r'^(S\.?\s?No|Sl\.?\s?No)', t, re.I):
        return 0.0
    if sum(c.isupper() for c in letters) / len(letters) > 0.5 or re.match(r'^[A-Z0-9]*\d[A-Z0-9]*\s*:', t):
        return 0.0
    score = 1.0 + (1.0 if credit >= 1 else 0.0)
    if _AI_WORDS.search(t):
        score += 1.0
    if _SENTENCE_VERB.search(t):
        score += 1.5
    if 60 <= len(t) <= 230:
        score += 0.5
    if not t.endswith('…'):
        score += 0.5
    return score


def _best_cite(cites, credit):
    """The citation to print for a requirement: the most readable one, else the first with a quotation."""
    scored = [(quote_quality(c.get('quote'), credit), i, c) for i, c in enumerate(cites) if c.get('quote')]
    if not scored:
        return None
    best = max(scored, key=lambda x: (x[0], -x[1]))
    return best[2]


def whole(value):
    """A score as the reports and the screens print it: rounded half up (62.5 prints 63, as the website's
    Math.round does; Python's round() would print 62)."""
    return int(math.floor(float(value or 0) + 0.5))


def _doc_names(payload):
    names = set()
    for d in payload.get('source_manifest') or []:
        name = re.sub(r'\s+', ' ', re.sub(r'\.[A-Za-z0-9]{2,4}$', '', str(d.get('filename') or ''))).strip()
        if len(name) >= 8:
            names.add(name)
    return sorted(names, key=len, reverse=True)


def _plain(explanation):
    """A requirement's text on the plain fallback: flagged since explanations-0.3, and recognisable in older stored
    text by its form ("Your <document>, page N records: \"...\".")."""
    return bool(explanation.get('fallback')) or bool(
        re.match(r'^Your .+, page \d+ records: "', str(explanation.get('found') or '')))


def _no_prefix(text):
    """The reports print "Next" in front of a practice's next step: an older stored fallback began "Next step:"."""
    t = re.sub(r'^\s*Next step:\s*', '', text or '')
    return t[:1].upper() + t[1:]


def clean_text(text, names):
    """Model-written explanation text, made easier to read: NAAC criterion file codes ("criteria 1 - 1.4.1") become
    plain words, and a document named again in the same passage becomes "the same document"."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not t:
        return ''
    code = r'[Cc]riteria\s+\d+\s*-\s*(?:[0-9]+(?:\.[0-9]+)*[a-z]?|[a-z])\b'
    # "Document criteria 1 - 1.4.2 notes ..." (the model naming one file): one file, so "A NAAC criterion file notes".
    t = re.sub(r'\b([Dd])ocument\s+' + code, lambda m: ('A' if m.group(1) == 'D' else 'a') + ' NAAC criterion file', t)
    t = re.sub(r'\b' + code, 'the NAAC criterion files', t)
    t = re.sub(r'(the NAAC criterion files)(,? (?:and|or) the NAAC criterion files)+', r'\1', t)
    for name in names:
        pattern = re.compile(r'(\b[Tt]he\s+)?' + re.escape(name))
        seen = [0]

        def swap(m):
            seen[0] += 1
            if seen[0] == 1:
                return m.group(0)
            start = m.start() == 0 or t[max(0, m.start() - 2):m.start()].strip() in {'.', ''}
            return ('The' if (m.group(1) or '').startswith('T') or start else 'the') + ' same document'
        t = pattern.sub(swap, t)
    return t


def _join(names):
    names = [n[0].lower() + n[1:] for n in names]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def choose_actions(result, records, areas, focus=None, total_weight=None, start_here=3):
    """What to do next: one step in every area (build brief, part B). In each key indicator the candidate is its
    first unfinished stage (at most two practices), worth the overall points they would add when shown in full. An
    area's step is its candidate at the earliest stage (the basics first), then worth the most points; on a tie, the
    key indicator with more already in place (more to build on), then rubric order. Steps run weakest area first; the first `start_here` are "Where to start". The code's
    choice, never the model's: next_steps.py writes text only for the steps chosen here."""
    if total_weight is None:
        total_weight = sum(float(i.get('weight_units') or 0) for i in result['indicators'])
    scores = {i['code']: float(i.get('score') or 0)
              for i in ((result.get('documented') or {}).get('indicators') or [])}
    best = {}
    for order, indicator in enumerate(result['indicators']):
        conditions = indicator['conditions']
        if not conditions:
            continue
        open_ = [(c, _credit(records.get(c['id']))) for c in conditions]
        open_ = [(c, cr) for c, cr in open_ if cr < 1]
        if not open_:
            continue
        first = min(_level_of(c['id']) for c, _ in open_)
        chosen = sorted([(c, cr) for c, cr in open_ if _level_of(c['id']) == first], key=lambda x: x[1])[:2]
        weight = (float(indicator.get('weight_units') or 0) / total_weight) if total_weight else 1 / max(1, len(result['indicators']))
        points = sum((1 - cr) / len(conditions) * 100 * weight for _, cr in chosen)
        area = indicator.get('pillar') or indicator['code'].rsplit('.', 1)[0]
        candidate = {'title': AREA_TITLES.get(indicator['code'], indicator.get('name', '')), 'code': indicator['code'],
                     'area_code': area, 'area': PILLARS.get(area, area), 'points': points,
                     'step': STAGE_STEP.get(first, 'Show'),
                     'conditions': [{'id': c['id'], 'text': c['text']} for c, _ in chosen]}
        # The basics first (Siddharth, 26 Nov: "finishing the basics in every area"), then the most points, then
        # the key indicator with more already in place, then rubric order.
        rank = (-first, round(points, 6), scores.get(indicator['code'], 0.0), -order)
        if area not in best or rank > best[area][0]:
            best[area] = (rank, candidate)
    area_score = {a['code']: a['score'] for a in areas}
    picked = sorted((c for _, c in best.values()), key=lambda a: (area_score.get(a['area_code'], 0.0), a['area_code']))
    for n, action in enumerate(picked):
        action['start_here'] = n < start_here
    return picked


@lru_cache(maxsize=1)
def _labels():
    from pathlib import Path
    import json
    return json.loads(Path(__file__).with_name('practice_labels_v1.json').read_text())['conditions']


def practice_label(condition_id, text=''):
    """(label, looked_for) for a practice: the short label and the sentence that stands on its own, else the rubric's
    sentence."""
    row = _labels().get(condition_id) or {}
    return row.get('label') or _sentence(text), row.get('looked_for') or _sentence(text)


KIND_LABELS = {'extend': 'Extend', 'name': 'Name', 'start': 'Start'}
#: A card's strengths are titled "The closest things you have" below this area score: what there is barely counts.
CLOSEST_BELOW = 10
#: How many cards share a leadership report page, after page 1 (the v5 mock: two, in larger type).
CARDS_PER_PAGE = 2
NOTHING_YET = 'Nothing in the documents you sent yet'


def basics_score(result, records):
    """The overall score if the basics (the first two practices of every topic, the set-up stage) were shown in full,
    everything else as credited: "Finishing the basics in every area would bring you to about N" (Siddharth, 26 Nov).
    From the credits the documents show, before anything is held for the follow-up answers."""
    total = sum(float(i.get('weight_units') or 0) for i in result['indicators'])
    if not total:
        return 0.0
    score = 0.0
    for indicator in result['indicators']:
        conditions = indicator['conditions']
        if not conditions:
            continue
        credits = [1.0 if _level_of(c['id']) == 0 else _credit(records.get(c['id'])) for c in conditions]
        score += float(indicator.get('weight_units') or 0) / total * 100 * sum(credits) / len(conditions)
    return score


def _and(lines):
    """Two "done when" lines as one, ending in a full stop: "a policy is in force, and it sets a limit on its use."
    """
    parts = [l.strip().rstrip('.') for l in lines if l and l.strip()]
    return (', and '.join(parts) + '.') if parts else ''


#: A "done when" line that points back at the practice before it ("those decisions", "that guidance"): 40 of 216
#: do, and most second practices of a stage read as a sequel; that reads well after the first, not alone.
POINTS_BACK = re.compile(r'\b(?:those|these|such|that|it|its)\b(?! is| was| are| has)', re.I)


def _unless_same(line, other):
    """line, or '' when it says the same as other (four in five of its words of four letters or more are in other)."""
    words = lambda t: set(re.findall(r'[a-z]{4,}', (t or '').lower()))
    mine, theirs = words(line), words(other)
    return '' if mine and len(mine & theirs) >= 0.8 * len(mine) else line


def _standalone(requirements):
    """The step's "done when" lines; a first line that points back at a practice the step doesn't include is
    replaced by that practice's own stand-alone "we looked for" sentence (practice_labels_v1.json)."""
    lines = []
    for n, r in enumerate(requirements):
        line = r['done_when']
        # The second practice of a stage (F2, A2, O2) is written as a sequel to the first ("the pathway includes...").
        if n == 0 and (r['id'].endswith('2') or POINTS_BACK.search(line)):
            looked = practice_label(r['id'])[1]
            if looked:
                line = looked[:1].lower() + looked[1:].rstrip('.') + '.' if not looked[1:2].isupper() else looked
        lines.append(line)
    return lines


def step_view(action):
    """A step as the reports print it: the title, its kind, what it builds on, who leads it and when it is done."""
    owner = action.get('owner') or {}
    lead = owner.get('name') or ''
    if lead:
        lead += ' (suggested)' if owner.get('suggested') else ' (named in your documents)'
    labels = [practice_label(r['id'])[0] for r in action.get('requirements') or []]
    written = bool(action.get('generated'))
    lower = lambda l: l if l[1:2].isupper() else l[:1].lower() + l[1:]   # "AI ..." keeps its capitals
    title = action.get('action') if written else ('Put in place: ' + ' and '.join(lower(l) for l in labels)
                                                   if labels else action.get('title', ''))
    if written and action.get('kind') == 'start':
        builds = NOTHING_YET
    else:
        builds = action.get('builds_on') or ''
    return {'title': title, 'kind': KIND_LABELS.get(action.get('kind') or '', ''), 'builds_on': builds, 'lead': lead,
            'done_when': [r['done_when'] for r in action.get('requirements') or [] if r.get('done_when')],
            # In rubric order (F1 before F2), whatever order the step was chosen in: the second line refers to the first.
            'done_when_text': _and(_standalone(sorted((r for r in action.get('requirements') or [] if r.get('done_when')),
                                                      key=lambda r: r['id']))),
            'start': action.get('kind') == 'start', 'written': written, 'first_step': action.get('first_step') or '',
            'have': action.get('have') or [], 'related': action.get('related') or []}


def card_view(area, step, word):
    """An area's card: the model's verdict, strengths and gaps (explanations-0.4) where written and checked, else a
    plain fallback from the record (the reports are then a draft: publication.readiness). A weak area's strengths
    become "The closest things you have": the starting points its step was checked against."""
    exp = area.get('explanation') or {}
    written = bool(exp.get('verdict')) and not exp.get('fallback')
    strengths = [{'text': x['text'], 'source': x.get('source') or ''} for x in exp.get('strengths') or []] \
        if written else []
    if not written and area.get('quote'):
        strengths = [{'text': f"\u201c{area['quote']['text']}\u201d", 'source': area['quote']['source']}]
    gaps = [g['text'] for g in exp.get('gaps') or []] if written else \
        [practice_label(m['id'])[0] for m in (area.get('missing') or [])[:3]]
    title = 'What you do well'
    if area['score'] < CLOSEST_BELOW:
        title = 'The closest things you have'
        if step and step['written'] and not step['start']:
            near = [{'text': x['text'], 'source': ', '.join(x.get('sources') or [])}
                    for x in (step['have'] or []) + (step['related'] or [])][:3]
            strengths = near or strengths
    return {'written': written, 'verdict': exp.get('verdict') or area.get('summary_short') or '',
            'headline': exp.get('headline') or '', 'strengths_title': title, 'strengths': strengths[:3],
            'gaps': gaps[:3]}


def level(score):
    """The level of a score as printed: from the whole number the reader sees (39.6 prints "40", so Prepared), so a
    number and its level never disagree; the points to the next level are counted from it too."""
    printed = whole(score)
    band = tier_for(printed)
    to_next = max(1, whole(band['points_to_next'])) if band['next'] else 0
    return {'name': band['current'], 'stars': band['stars'], 'meaning': band['meaning'],
            'next': band['next'], 'next_stars': band['stars'] + 1 if band['next'] else None,
            'points_to_next': to_next}


def levels_table():
    rows = tiers()
    out = []
    for i, (name, start) in enumerate(rows):
        end = rows[i + 1][1] - 1 if i + 1 < len(rows) else None
        out.append({'name': name, 'stars': i + 1, 'from': int(start), 'to': int(end) if end is not None else None,
                    'meaning': LEVEL_MEANINGS.get(name, '')})
    return out


def build(payload):
    """The view the new reports print. payload: the report payload with explanations attached."""
    assessment = payload['assessment']
    result = assessment['result']
    stage = payload.get('assessment_stage') or {}
    final = stage.get('stage') == 'final'
    score = next((float(result[k]) for k in ('score', 'exact_score', 'lower') if result.get(k) is not None), 0.0)
    records = {r['condition_id']: r for r in assessment['records']}
    pages = {str(p['page_id']): f"{doc_label(d['filename'])}, page {p.get('number', '?')}"
             for d in payload.get('source_manifest') or [] for p in d.get('pages', [])}
    plan = (payload.get('deterministic_plan') or {}).get('priority_plan') or {}
    foundation = (payload.get('deterministic_plan') or {}).get('foundation_plan') or {}
    from . import next_steps
    not_started = frozenset(payload.get('not_started') or ())
    checklist = next_steps.checklist(result, records, not_started)
    gains = {}
    for action in plan.get('actions') or []:
        area = action.get('pillar') or action['indicator'].rsplit('.', 1)[0]
        gains[area] = gains.get(area, 0) + float(action.get('score_gain') or 0)
    documented = result.get('documented') or {}
    indicator_scores = {i['code']: i for i in documented.get('indicators') or []}

    pillars = documented.get('pillars')
    if not pillars:   # a run from before the single score: each area's share of credited requirements
        pillars = []
        for code in dict.fromkeys(i.get('pillar') or i['code'].rsplit('.', 1)[0] for i in result['indicators']):
            ids = [c['id'] for i in result['indicators'] if (i.get('pillar') or i['code'].rsplit('.', 1)[0]) == code
                   for c in i['conditions']]
            pillars.append({'code': code, 'score': round(100 * sum(_credit(records.get(c)) for c in ids) / len(ids), 2)
                            if ids else 0.0})
    total_weight = sum(float(i.get('weight_units') or 0) for i in result['indicators'])
    names = _doc_names(payload)
    areas, used_quotes = [], set()
    for pillar in pillars:
        code = pillar['code']
        indicators = [i for i in result['indicators'] if i.get('pillar') == code or i['code'].startswith(code + '.')]
        credit = counted = 0.0
        in_place = partly = 0
        candidates = []
        subareas = []
        for indicator in indicators:
            rows = []
            for condition in indicator['conditions']:
                record = records.get(condition['id'])
                cr = _credit(record)
                credit += cr
                counted += cr * (_counted(record) if record else 1.0)
                status = 'shown' if cr >= 1 else 'partly' if cr > 0 else 'missing'
                if status == 'shown':
                    in_place += 1
                elif status == 'partly':
                    partly += 1
                cites = (record or {}).get('citations') or [c for p in (record or {}).get('parts') or []
                                                            for c in p.get('citations') or []]
                cite = _readable_cite(_best_cite(cites, cr), cites)
                if cr >= 0.5:
                    for c in cites:
                        q = quote_quality(c.get('quote'), cr)
                        if q > 0 and not unreadable(c.get('quote')):
                            candidates.append((q, -_level_of(condition['id']), c))
                explanation = (record or {}).get('explanation') or {}
                label, looked_for = practice_label(condition['id'], condition['text'])
                rows.append({'id': condition['id'], 'label_short': label, 'looked_for': looked_for,
                             'text': _sentence(condition['text']), 'status': status,
                             'label': next_steps.label(condition['id'], cr, not_started),
                             # Printed alone ("Next: Done when ..."), so it stands alone (_standalone); left out where
                             # it would only repeat the "We looked for" line above it.
                             'done_when': _unless_same(
                                 _standalone([{'id': condition['id'], 'done_when': next_steps.done_when(condition)}])[0],
                                 looked_for) if cr < 1 else '',
                             'stage': STAGE_WORDS.get(condition['id'].rsplit('.', 1)[-1][:1], ''),
                             'quote': _quote(cite['quote'], 260) if cite and cr > 0 else '',
                             # The detailed report cites the documents instead of quoting them (Harsha, 26 Nov).
                             'evidence_in': evidence_in([cite] + [c for c in cites if c is not cite], pages)
                             if cite and cr > 0 else [],
                             'why': _why(explanation.get('text')) if status == 'partly' and not _plain(explanation)
                             else '',
                             'records': _records_that_show(condition['id']) if status == 'missing' else '',
                             'source': pages.get(str(cite.get('source_id')), '') if cite and cr > 0 else '',
                             # A requirement still on the plain fallback has no written finding (its fallback only
                             # restated the quotation): the quotation below says it, with its document and page.
                             'found': '' if _plain(explanation) else clean_text(explanation.get('found'), names),
                             'next_step': _no_prefix(clean_text(explanation.get('next_step'), names)),
                             'follow_up': explanation.get('follow_up') or ''})
            iscore = indicator_scores.get(indicator['code'], {}).get('score')
            exp = indicator.get('explanation') or indicator_scores.get(indicator['code'], {}).get('explanation') or {}
            subareas.append({'code': indicator['code'], 'name': AREA_TITLES.get(indicator['code'], indicator.get('name', '')),
                             'score': iscore, 'stars': level(iscore or 0)['stars'], 'requirements': rows,
                             'level_index': min(4, whole(iscore) // 20), 'nothing': not iscore,
                             'marks': [r['status'] for r in rows],
                             'verdict': clean_text(exp.get('verdict'), names) if exp.get('verdict') and
                             not exp.get('fallback') else '',
                             'line': topic_line(rows),
                             'summary': clean_text(' '.join(x for x in (exp.get('found'), exp.get('text')) if x), names)})
        quote = None
        for _, _, c in sorted(candidates, key=lambda x: (-x[0], -x[1])):
            if c['quote'] not in used_quotes:
                used_quotes.add(c['quote'])
                quote = {'text': display_quote(c['quote']), 'source': pages.get(str(c.get('source_id')), 'your documents')}
                break
        # Overall points still to gain here if all of it were shown: each key indicator's weight times what it lacks.
        room = sum(float(i.get('weight_units') or 0) / total_weight * (100 - float(indicator_scores.get(i['code'], {}).get('score') or 0))
                   for i in indicators) if total_weight else 0.0
        ratio = credit / counted if counted else 1.0
        shown = min(100.0, pillar['score'] * ratio)
        exp = pillar.get('explanation') or {}
        areas.append({'code': code, 'name': PILLARS.get(code, code), 'definition': AREA_DEFINITIONS.get(code, ''),
                      'explanation': exp, 'score': pillar['score'], 'shown': shown,
                      'held': max(0.0, shown - pillar['score']), 'level': level(pillar['score']),
                      'requirements': sum(len(i['conditions']) for i in indicators), 'in_place': in_place,
                      'partly': partly, 'quote': quote,
                      # Requirements not yet done, foundations first: the code's label and the plain "done when" line.
                      'missing': checklist.get(code, []),
                      'summary_short': _first_sentences(clean_text(exp.get('found') or exp.get('text') or '', names)),
                      'summary': clean_text(' '.join(x for x in (exp.get('found'), exp.get('text')) if x), names),
                      'points_available': round(gains.get(code, 0.0), 1), 'room': room, 'subareas': subareas})

    by_score = sorted(areas, key=lambda a: -a['score'])
    strengths = [a for a in by_score if a['score'] > 0][:3]
    focus = [a for a in sorted(areas, key=lambda a: (a['score'], -a['points_available'])) if a not in strengths][:3]
    overall = level(score)
    chosen = choose_actions(result, records, areas, focus, total_weight)
    actions = next_steps.finish(chosen, records, pages, payload.get('next_steps'), not_started)
    to_next, gathered = [], 0.0
    for action in actions:
        if len(to_next) >= 5 or (overall['next'] and gathered >= overall['points_to_next']):
            break
        to_next.append(action)
        gathered += action['points']
    reserve = result.get('depth_reserve') or {}
    held_points = float(reserve.get('still_held_points') or 0)
    # The redesigned reports (v5 mocks, 26 Nov): cards strongest first, two to a page after page 1; one step per area.
    from .explanations import institution_word
    word = institution_word(payload.get('profile'))
    by_area_step = {a['area_code']: step_view(a) for a in actions}
    ordered = sorted(areas, key=lambda a: -a['score'])
    for n, area in enumerate(ordered):
        area['step'] = by_area_step.get(area['code'])
        area['card'] = card_view(area, area['step'], word)
        area['card_page'] = 2 + n // CARDS_PER_PAGE
        area['level_index'] = min(4, whole(area['score']) // 20)
        area['confirmed'] = area['score']
        area['to_confirm'] = area['held'] if area['held'] >= 0.5 else 0.0
    page_of = {a['code']: a['card_page'] for a in ordered}
    score_of = {a['code']: a['score'] for a in areas}
    for action in actions:
        action['view'] = by_area_step[action['area_code']]
        action['card_page'] = page_of.get(action['area_code'])
        action['area_score'] = score_of.get(action['area_code'], 0.0)
    basics = basics_score(result, records)
    summary_lines = []
    if ordered:
        # Nothing is "strong" at 0: then only the weakest line, which names the plainest gap.
        picks = [('Strongest', ordered[0])] if ordered[0]['score'] > 0 else []
        picks += [('Also strong', ordered[1])] if len(ordered) > 2 and ordered[1]['score'] > 0 else []
        picks += [('Weakest', ordered[-1])]
        summary_lines = [{'label': l, 'area': a['name'], 'fact': a['card']['headline']} for l, a in picks]
    shown_whole = whole(min(100.0, score + held_points))
    if strengths:
        summary = f"Your documents show the most in {strengths[0]['name']}"
        summary += f", followed by {strengths[1]['name']}." if len(strengths) > 1 else '.'
        if focus:
            summary += f" Focus next on {focus[0]['name']}" + (f", then {focus[1]['name']}." if len(focus) > 1 else '.')
    else:
        summary = 'Your documents show little AI-specific practice so far. The areas below show where to start.'
    routes = [{'name': r['name'], 'duration': r.get('indicative_duration', '')} for r in foundation.get('routes') or []]
    return {'institution': (payload.get('scope') or {}).get('institution', {}).get('assessed_name')
            or payload['profile'].get('name', ''),
            'final': final, 'stage_label': 'Final result' if final else 'Stage 1 result: from your documents',
            'score': score, 'score_whole': whole(score), 'level': overall, 'levels': levels_table(),
            'held_points': held_points, 'held_whole': whole(held_points),
            'held_share_text': ('a quarter' if abs(float(reserve.get('share') or 0) - 0.25) < 1e-9
                                else f"{float(reserve.get('share') or 0) * 100:g}%"),
            'shown_score': min(100.0, score + held_points),
            'areas': sorted(areas, key=lambda a: -a['score']), 'strengths': strengths, 'focus': focus,
            'actions': actions, 'raw_actions': chosen, 'actions_points': sum(a['points'] for a in actions),
            'next_steps_written': any(a['generated'] for a in actions), 'to_next': to_next,
            'where_points': sorted(areas, key=lambda a: -a['room'])[:3],
            'started': [a for a in sorted(areas, key=lambda a: -a['score']) if a['score'] > 0 or a['partly']],
            'not_started': [a for a in areas if not (a['score'] > 0 or a['partly'])], 'to_next_points': gathered, 'summary': summary,
            'routes': routes, 'requirements': sum(a['requirements'] for a in areas),
            'cards': ordered, 'card_pages': [ordered[i:i + CARDS_PER_PAGE] for i in range(0, len(ordered), CARDS_PER_PAGE)],
            'summary_lines': summary_lines, 'start_here': [a for a in actions if a.get('start_here')],
            'basics': {'score': basics, 'whole': whole(basics), 'level': level(basics)['name'],
                       'reaches_next': bool(overall['next']) and level(basics)['stars'] > overall['stars']},
            'institution_word': word, 'stage1': not final,
            'confirmed_whole': whole(score), 'shown_whole': shown_whole,
            'to_next_if_confirmed': max(0, levels_table()[min(4, overall['stars'])]['from'] - shown_whole)
            if overall['next'] else 0,
            'pages': sum(len(d.get('pages') or []) for d in payload.get('source_manifest') or []),
            'level_index': min(4, whole(score) // 20),
            # The bracket under the overall bar: from the score to the next level, or across what is to be confirmed.
            'next_note_width': (100 * overall['points_to_next'] / max(1.0, 100 - score)) if overall['next'] else 0,
            'held_note_width': 100 * min(held_points, 100 - score) / max(1.0, 100 - score),
            'in_place': sum(a['in_place'] for a in areas), 'partly': sum(a['partly'] for a in areas),
            'documents': len(payload.get('source_manifest') or []),
            'reference_period': payload.get('reference_period') or ''}


def for_screens(view):
    """What the website's Overview, Readiness areas and practices screens print: the same pieces as the reports
    (build brief: one set of pieces, so the reports and the website can't drift apart), trimmed to what they show."""
    def step(s):
        return None if not s else {k: s[k] for k in ('title', 'kind', 'builds_on', 'lead', 'done_when_text', 'start',
                                                    'written', 'first_step')}
    cards = []
    for a in view['cards']:
        cards.append({
            'code': a['code'], 'name': a['name'], 'definition': a['definition'], 'score': a['score'],
            'level': a['level']['name'], 'level_index': a['level_index'], 'to_confirm': a['to_confirm'],
            'card': a['card'], 'step': step(a.get('step')),
            'topics': [{'code': t['code'], 'name': t['name'], 'score': t['score'], 'marks': t['marks'],
                        'practices': [{k: r.get(k) for k in ('id', 'label_short', 'looked_for', 'status', 'label',
                                                             'found', 'quote', 'source', 'next_step', 'done_when',
                                                             'follow_up')} for r in t['requirements']]}
                       for t in a['subareas']]})
    return {
        'stage1': view['stage1'], 'level': view['level'], 'levels': view['levels'], 'level_index': view['level_index'],
        'score': view['score'], 'confirmed_whole': view['confirmed_whole'], 'shown_whole': view['shown_whole'],
        'held_whole': view['held_whole'], 'held_points': view['held_points'],
        'to_next_if_confirmed': view['to_next_if_confirmed'], 'summary_lines': view['summary_lines'],
        'basics': view['basics'], 'documents': view['documents'], 'requirements': view['requirements'],
        'institution_word': view['institution_word'], 'cards': cards,
        'start_here': [{'area': a['area'], 'area_code': a['area_code'], **step(a['view'])} for a in view['start_here']],
        'steps': [{'area': a['area'], 'area_code': a['area_code'], 'area_score': a['area_score'], **step(a['view'])}
                  for a in view['actions']],
    }
