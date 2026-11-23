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


def _join(names):
    names = [n[0].lower() + n[1:] for n in names]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


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
    pages = {str(p['page_id']): f"{d['filename']}, page {p.get('number', '?')}"
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
    areas, used_quotes = [], set()
    for pillar in pillars:
        code = pillar['code']
        indicators = [i for i in result['indicators'] if i.get('pillar') == code or i['code'].startswith(code + '.')]
        credit = counted = 0.0
        in_place = partly = 0
        quote = None
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
                else:
                    missing.append((_level_of(condition['id']), _sentence(condition['text'])))
                cites = (record or {}).get('citations') or [c for p in (record or {}).get('parts') or []
                                                            for c in p.get('citations') or []]
                cite = next((c for c in cites if c.get('quote')), None)
                if quote is None and cite and cr >= 0.5 and cite['quote'] not in used_quotes:
                    used_quotes.add(cite['quote'])
                    quote = {'text': _quote(cite['quote']), 'source': pages.get(str(cite.get('source_id')), 'your documents')}
                explanation = (record or {}).get('explanation') or {}
                rows.append({'text': _sentence(condition['text']), 'status': status,
                             'stage': STAGE_WORDS.get(condition['id'].rsplit('.', 1)[-1][:1], ''),
                             'quote': _quote(cite['quote'], 260) if cite and cr > 0 else '',
                             'source': pages.get(str(cite.get('source_id')), '') if cite and cr > 0 else '',
                             'found': explanation.get('found') or '', 'next_step': explanation.get('next_step') or '',
                             'follow_up': explanation.get('follow_up') or ''})
            iscore = indicator_scores.get(indicator['code'], {}).get('score')
            exp = indicator.get('explanation') or indicator_scores.get(indicator['code'], {}).get('explanation') or {}
            subareas.append({'code': indicator['code'], 'name': AREA_TITLES.get(indicator['code'], indicator.get('name', '')),
                             'score': iscore, 'stars': level(iscore or 0)['stars'], 'requirements': rows,
                             'summary': ' '.join(x for x in (exp.get('found'), exp.get('text')) if x)})
        ratio = credit / counted if counted else 1.0
        shown = min(100.0, pillar['score'] * ratio)
        exp = pillar.get('explanation') or {}
        areas.append({'code': code, 'name': PILLARS.get(code, code), 'score': pillar['score'], 'shown': shown,
                      'held': max(0.0, shown - pillar['score']), 'level': level(pillar['score']),
                      'requirements': sum(len(i['conditions']) for i in indicators), 'in_place': in_place,
                      'partly': partly, 'quote': quote,
                      'missing': [m for _, m in sorted(missing, key=lambda x: x[0])],
                      'summary': ' '.join(x for x in (exp.get('found'), exp.get('text')) if x),
                      'points_available': round(gains.get(code, 0.0), 1), 'subareas': subareas})

    by_score = sorted(areas, key=lambda a: -a['score'])
    strengths = [a for a in by_score if a['score'] > 0][:3]
    focus = [a for a in sorted(areas, key=lambda a: (a['score'], -a['points_available'])) if a not in strengths][:3]
    overall = level(score)
    actions = []
    for action in sorted(plan.get('actions') or [], key=lambda a: -float(a.get('score_gain') or 0)):
        conditions = action.get('conditions') or []
        role = next((goal_roles[c['condition_id']] for c in conditions if goal_roles.get(c['condition_id'])), '')
        actions.append({'title': AREA_TITLES.get(action['indicator'], action.get('name', '')),
                        'area': PILLARS.get(action.get('pillar') or action['indicator'].rsplit('.', 1)[0], ''),
                        'points': float(action.get('score_gain') or 0),
                        'show': [_sentence(c['requirement']) for c in conditions[:3]],
                        'more': max(0, len(conditions) - 3), 'lead': role})
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
            'actions': actions[:4], 'to_next': to_next,
            'started': [a for a in sorted(areas, key=lambda a: -a['score']) if a['score'] > 0 or a['partly']],
            'not_started': [a for a in areas if not (a['score'] > 0 or a['partly'])], 'to_next_points': gathered, 'summary': summary,
            'routes': routes, 'requirements': sum(a['requirements'] for a in areas),
            'in_place': sum(a['in_place'] for a in areas), 'partly': sum(a['partly'] for a in areas),
            'documents': len(payload.get('source_manifest') or []),
            'reference_period': payload.get('reference_period') or ''}
