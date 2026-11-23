"""The readiness picture for people: what the leadership and detailed reports show (Vijay and Siddharth, 23 Nov).

One function, build(), turns a report payload (report_views.CapabilityReportView) into a plain view: the readiness
level with its stars, the nine areas each with its own stars, strengths quoted from the college's own documents, the
areas to focus on, what the next level takes, and a short list of actions. No model calls, no internal terms: the
templates print what this returns. The front end's workspace/useResult.ts shapes the screens the same way.

Design: claude/ai-ready-leadership-report-design.md (AI Readiness project).
"""
import re

from .action_plan import LEVEL_MEANINGS, tier_for, tiers
from .report_projection import AREA_TITLES, PILLARS

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


# A suggested lead for an area's actions when no foundation goal names one (shown as a suggestion, never assigned).
DEFAULT_LEADS = {
    'AIQIF-C1': 'Leadership team and IQAC', 'AIQIF-C2': 'Data protection and IT leads',
    'AIQIF-C3': 'Programme and curriculum leads', 'AIQIF-C4': 'Academic development lead',
    'AIQIF-C5': 'Student learning and placement leads', 'AIQIF-C6': 'IT and data leads',
    'AIQIF-C7': 'Research and innovation lead', 'AIQIF-C8': 'Service owners and partnerships lead',
    'AIQIF-C9': 'IQAC coordinator',
}
STAGE_STEP = {0: 'Set up', 1: 'Put in use', 2: 'Measure the results'}
_SENTENCE_VERB = re.compile(r'\b(is|are|was|were|has|have|had|provides?|conducts?|offers?|organi[sz]ed|established|'
                            r'approved|completed|trained|includes?|uses?|maintains?|supports?|introduced|adopted|'
                            r'enables?|covers?|focus(es|ing)?|participated|delivered|implemented|created|set up)\b', re.I)


_AI_WORDS = re.compile(r'\b(AI|artificial intelligence|machine learning|deep learning|generative|neural)\b', re.I)


def doc_label(filename):
    """A document's name as a reader sees it: no extension, single spaces."""
    return re.sub(r'\s+', ' ', re.sub(r'\.[A-Za-z0-9]{2,4}$', '', str(filename or ''))).strip()


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


def _doc_names(payload):
    names = set()
    for d in payload.get('source_manifest') or []:
        name = re.sub(r'\s+', ' ', re.sub(r'\.[A-Za-z0-9]{2,4}$', '', str(d.get('filename') or ''))).strip()
        if len(name) >= 8:
            names.add(name)
    return sorted(names, key=len, reverse=True)


def clean_text(text, names):
    """Model-written explanation text, made easier to read: NAAC criterion file codes ("criteria 1 - 1.4.1") become
    plain words, and a document named again in the same passage becomes "the same document"."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not t:
        return ''
    t = re.sub(r'\b[Cc]riteria\s+\d+\s*-\s*[0-9]+(?:\.[0-9]+)*[a-z]?\b|\b[Cc]riteria\s+\d+\s*-\s*[a-z]\b',
               'the NAAC criterion files', t)
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


def choose_actions(result, records, indicator_scores, goal_roles, areas, focus, total_weight, limit=6, per_area=2):
    """What to do next: for each key indicator, the practices at its first unfinished stage (at most two), with the
    overall points they would add when shown in full. The areas with the most to gain and the focus areas get their
    best action first; then the largest gains, at most two per area and six in all. Matches workspace/plain.ts."""
    candidates = []
    for indicator in result['indicators']:
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
        lead = next((goal_roles[c['id']] for c, _ in chosen if goal_roles.get(c['id'])), '') or DEFAULT_LEADS.get(area, '')
        candidates.append({'title': AREA_TITLES.get(indicator['code'], indicator.get('name', '')), 'code': indicator['code'],
                           'area_code': area, 'area': PILLARS.get(area, area), 'points': points,
                           'step': STAGE_STEP.get(first, 'Show'),
                           'show': [_sentence(c['text']) + (' (partly shown)' if cr > 0 else '') for c, cr in chosen],
                           'more': 0, 'lead': lead})
    candidates.sort(key=lambda a: -a['points'])
    picked, count = [], {}
    priority = [a['code'] for a in sorted(areas, key=lambda a: -a['room'])[:3]] + [a['code'] for a in focus]
    for code in dict.fromkeys(priority):
        best = next((a for a in candidates if a['area_code'] == code and a not in picked), None)
        if best and len(picked) < limit:
            picked.append(best)
            count[code] = count.get(code, 0) + 1
    for a in candidates:
        if len(picked) >= limit:
            break
        if a not in picked and count.get(a['area_code'], 0) < per_area:
            picked.append(a)
            count[a['area_code']] = count.get(a['area_code'], 0) + 1
    return sorted(picked, key=lambda a: -a['points'])


def level(score):
    band = tier_for(score)
    return {'name': band['current'], 'stars': band['stars'], 'meaning': band['meaning'],
            'next': band['next'], 'next_stars': band['stars'] + 1 if band['next'] else None,
            'points_to_next': max(0, int(-(-band['points_to_next'] // 1))) if band['next'] else 0}


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
    goal_roles = {}
    for goal in foundation.get('goals') or []:
        for cid in goal.get('target_condition_ids') or []:
            goal_roles.setdefault(cid, re.sub(r'\s*\(suggested\)$', '', goal.get('suggested_role') or ''))
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
        missing = []
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
                    missing.append((_level_of(condition['id']), 1, _sentence(condition['text']) + ' (partly shown)'))
                else:
                    missing.append((_level_of(condition['id']), 0, _sentence(condition['text'])))
                cites = (record or {}).get('citations') or [c for p in (record or {}).get('parts') or []
                                                            for c in p.get('citations') or []]
                cite = _best_cite(cites, cr)
                if cr >= 0.5:
                    for c in cites:
                        q = quote_quality(c.get('quote'), cr)
                        if q > 0:
                            candidates.append((q, -_level_of(condition['id']), c))
                explanation = (record or {}).get('explanation') or {}
                rows.append({'text': _sentence(condition['text']), 'status': status,
                             'stage': STAGE_WORDS.get(condition['id'].rsplit('.', 1)[-1][:1], ''),
                             'quote': _quote(cite['quote'], 260) if cite and cr > 0 else '',
                             'source': pages.get(str(cite.get('source_id')), '') if cite and cr > 0 else '',
                             'found': clean_text(explanation.get('found'), names),
                             'next_step': clean_text(explanation.get('next_step'), names),
                             'follow_up': explanation.get('follow_up') or ''})
            iscore = indicator_scores.get(indicator['code'], {}).get('score')
            exp = indicator.get('explanation') or indicator_scores.get(indicator['code'], {}).get('explanation') or {}
            subareas.append({'code': indicator['code'], 'name': AREA_TITLES.get(indicator['code'], indicator.get('name', '')),
                             'score': iscore, 'stars': level(iscore or 0)['stars'], 'requirements': rows,
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
        areas.append({'code': code, 'name': PILLARS.get(code, code), 'score': pillar['score'], 'shown': shown,
                      'held': max(0.0, shown - pillar['score']), 'level': level(pillar['score']),
                      'requirements': sum(len(i['conditions']) for i in indicators), 'in_place': in_place,
                      'partly': partly, 'quote': quote,
                      'missing': [m for *_, m in sorted(missing, key=lambda x: (x[0], x[1]))],
                      'summary_short': _first_sentences(clean_text(exp.get('found') or exp.get('text') or '', names)),
                      'summary': clean_text(' '.join(x for x in (exp.get('found'), exp.get('text')) if x), names),
                      'points_available': round(gains.get(code, 0.0), 1), 'room': room, 'subareas': subareas})

    by_score = sorted(areas, key=lambda a: -a['score'])
    strengths = [a for a in by_score if a['score'] > 0][:3]
    focus = [a for a in sorted(areas, key=lambda a: (a['score'], -a['points_available'])) if a not in strengths][:3]
    overall = level(score)
    actions = choose_actions(result, records, indicator_scores, goal_roles, areas, focus, total_weight)
    to_next, gathered = [], 0.0
    for action in actions:
        if len(to_next) >= 5 or (overall['next'] and gathered >= overall['points_to_next']):
            break
        to_next.append(action)
        gathered += action['points']
    reserve = result.get('depth_reserve') or {}
    held_points = float(reserve.get('still_held_points') or 0)
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
            'score': score, 'score_whole': int(round(score)), 'level': overall, 'levels': levels_table(),
            'held_points': held_points, 'held_whole': int(round(held_points)),
            'held_share_text': ('a quarter' if abs(float(reserve.get('share') or 0) - 0.25) < 1e-9
                                else f"{float(reserve.get('share') or 0) * 100:g}%"),
            'shown_score': min(100.0, score + held_points),
            'areas': sorted(areas, key=lambda a: -a['score']), 'strengths': strengths, 'focus': focus,
            'actions': actions, 'actions_points': sum(a['points'] for a in actions), 'to_next': to_next,
            'where_points': sorted(areas, key=lambda a: -a['room'])[:3],
            'started': [a for a in sorted(areas, key=lambda a: -a['score']) if a['score'] > 0 or a['partly']],
            'not_started': [a for a in areas if not (a['score'] > 0 or a['partly'])], 'to_next_points': gathered, 'summary': summary,
            'routes': routes, 'requirements': sum(a['requirements'] for a in areas),
            'in_place': sum(a['in_place'] for a in areas), 'partly': sum(a['partly'] for a in areas),
            'documents': len(payload.get('source_manifest') or []),
            'reference_period': payload.get('reference_period') or ''}
