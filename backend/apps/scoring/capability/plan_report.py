"""What a college downloads after a plan check: a short PDF (what works, what doesn't yet, what we recommend) and the
recommended plan as a Word file. Built from the check's saved result only; no model calls.

The code writes every sentence here except the model's notes, summary and recommended changes, which passed the
wording check in plan_mapping. Two numbers at most in a sentence: the score today and with the plan done (and the
recommended plan done), each with its readiness level.
"""
import io
import re

from django.template.loader import render_to_string

from .plan_mapping import AREAS, WORKS

KIND = {'change': 'Change', 'add': 'Add', 'drop': 'Drop'}


def _whole(value):
    return int(round(float(value or 0)))


def _level(levels, key):
    tier = (levels or {}).get(key) or {}
    return tier.get('current') or 'Starting out'


def score_lines(scores):
    """The result in plain sentences: today, with the plan done, with the recommended plan done."""
    today, plan, rec = (float(scores[k]) for k in ('today', 'plan', 'recommended'))
    levels = scores.get('levels') or {}

    def at(value, key):
        return f'{_whole(value)} out of 100 ({_level(levels, key)})'

    lines = [f'Your score today is {at(today, "today")}.']
    if plan > today:
        if _whole(plan) == _whole(today):
            lines.append('Done in full, with records to show it, your plan would raise it a little: by less than '
                         'one point.')
        else:
            lines.append(f'Done in full, with records to show it, your plan would bring it to {at(plan, "plan")}.')
    else:
        lines.append('As written, your plan would not change your score: none of its actions would leave a record '
                     'of something your documents do not already show.')
    if rec > plan and _whole(rec) == _whole(plan):
        lines.append('The recommended version, with the same budget, timeline and reach, would raise it a little '
                     'further: by less than one point.')
    elif rec > plan:
        lines.append(f'The recommended version, with the same budget, timeline and reach, would bring it to '
                     f'{at(rec, "recommended")}.')
    else:
        lines.append('Our recommended changes do not raise the score further; they make the plan clearer to carry out.')
    return lines


def _passage_label(passages, ids):
    by_id = {p['id']: p for p in passages or []}
    return [by_id[i]['where'] for i in ids if i in by_id]


def _norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def _text(action):
    """The action's own words, when they say more than its title (empty when the title is just their start)."""
    return '' if _norm(action['text']).startswith(_norm(action['title'])) and \
        len(_norm(action['text'])) - len(_norm(action['title'])) < 25 else action['text']


def build(payload, *, institution, result_kind, checked_on):
    """The page's content from a completed check (plan_mapping.run_pipeline's result)."""
    review = payload
    original = review['original']['actions']
    rec = review['recommendation']
    titles = {a['id']: a['title'] for a in original}
    works = [{'title': a['title'], 'text': _text(a), 'note': a['note']} for a in original if a['status'] in WORKS]
    not_yet = [{'title': a['title'], 'text': _text(a), 'label': a['label'], 'note': a['note']}
               for a in original if a['status'] not in WORKS]
    changes = []
    for c in rec['changes']:
        if c['operation'] == 'add':
            title = 'New action'
        else:
            title = titles.get(c['action_id'], '')
        changes.append({'kind': KIND[c['operation']], 'operation': c['operation'], 'title': title, 'text': c['text'],
                        'why': c['why'], 'owner': c['owner'], 'done_when': c['done_when'],
                        'area': AREAS.get((c.get('areas') or [''])[0], ''),
                        'builds_on': _passage_label(rec.get('passages'), c.get('builds_on') or [])})
    kept = sum(1 for a in rec['actions'] if a['origin'] == 'kept')
    outside = list(dict.fromkeys(m['area'] for m in review.get('missed') or [] if not m['in_plan_area']))[:3]
    return {
        'institution': institution, 'result_kind': result_kind, 'checked_on': checked_on,
        'how_to_read': ('We read your plan against what your documents showed in your ' + result_kind + '. '
                        '"What works" lists the actions that would raise your score once they are done and recorded; '
                        '"What doesn\'t count yet" says why the others would not. "What we recommend" keeps your plan '
                        'and changes only what would make more of it count, within your budget, timeline and reach.'),
        'score_lines': score_lines(review['scores']), 'summary': rec.get('summary') or '',
        'works': works, 'not_yet': not_yet, 'changes': changes, 'kept': kept,
        'total': len(original), 'constraints': [c['quote'] for c in review['original']['constraints']],
        'unclear': review['original'].get('unclear') or [], 'warnings': review['original'].get('warnings') or [],
        'recommended': [{'n': n, 'text': a['text'], 'origin': a['origin'], 'owner': a.get('owner') or '',
                         'done_when': a.get('done_when') or ''} for n, a in enumerate(rec['actions'], 1)],
        'outside': outside,
        'limits': ('This is a projection, not a score: it assumes each action is done as written and that a record '
                   'shows it, such as minutes, an approved policy, attendance with results, or a report. Your score '
                   'changes only when a new assessment reads those records.')}


def masked(view):
    from apps.demo_mask import mask
    return mask.data(view) if mask.active() else view


def html(view):
    return render_to_string('scoring/plan_review.html', {'v': view})


def pdf(view):
    from .report_views import html_to_pdf
    return html_to_pdf(html(view))


def docx(view):
    """The recommended plan as a Word file the college can edit."""
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)
    doc.add_heading(f'{view["institution"]}: AI plan, recommended version', level=1)
    doc.add_paragraph(f'Checked on {view["checked_on"]} against your {view["result_kind"]}. Changed and added '
                      'actions are marked. Everything else is your plan as you wrote it.')
    for line in view['score_lines']:
        doc.add_paragraph(line)
    doc.add_heading('Actions', level=2)
    for a in view['recommended']:
        tag = {'changed': ' (changed)', 'added': ' (added)'}.get(a['origin'], '')
        p = doc.add_paragraph(style='List Number')
        p.add_run(a['text'])
        if tag:
            p.add_run(tag).italic = True
        details = [f'Owner: {a["owner"]}' if a['owner'] and a['owner'] != 'Not stated' else '',
                   f'Done when: {a["done_when"]}' if a['done_when'] else '']
        if any(details):
            doc.add_paragraph('; '.join(d for d in details if d))
    dropped = [c for c in view['changes'] if c['operation'] == 'drop']
    if dropped:
        doc.add_heading('Taken out', level=2)
        for c in dropped:
            doc.add_paragraph(f'{c["title"]}: {c["why"]}', style='List Bullet')
    if view['constraints']:
        doc.add_heading('Budget, timeline and scope, unchanged from your plan', level=2)
        for q in view['constraints']:
            doc.add_paragraph(q, style='List Bullet')
    doc.add_paragraph(view['limits'])
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def filename(institution, suffix):
    stem = re.sub(r'[^A-Za-z0-9]+', '-', institution or 'college').strip('-')[:60] or 'college'
    return f'{stem}-ai-plan-{suffix}'
