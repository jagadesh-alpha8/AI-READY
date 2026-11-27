"""Learning from judged runs (learn-1): what a judge credited becomes a tag, so the next packet leads with it.

Only requirements that earned credit in the run count (26 Nov, Siddharth: test 13's judge marked parts as found on
requirements that ended with no credit, and those must not become tags). For such a requirement, every quotation a
part was credited with (in full, related or as digital groundwork) is added to its page's stored row:
- direct when the part was found in full and the requirement earned full credit;
- supporting otherwise.
Each tag carries `origin: judged_run`, the run and the version; re-tagging keeps it (tagging.kept_tags). A quotation
is added only when it is still on the page (the run's frozen text), and only to pages the tagger has read (a tagged
row). Pairs a reviewer marked not_evidence on a review sheet (scripts/retrieval/review_sheet.py) can be left out.
"""
from . import spec, tagging

VERSION = 'learn-1'
ORIGIN = 'judged_run'
CREDITED = ('full', 'related', 'digital_only')


def _cited(record):
    """[(citation, part kind)] for a record: its parts' credited citations, else (a condition-judge record) its own."""
    out = []
    for part in record.get('parts') or []:
        for key, label in (('citations', 'credited_as'), ('second_citations', 'second_credited_as'),
                           ('third_citations', 'third_credited_as')):
            kind = part.get(label)
            if kind in CREDITED:
                out += [(c, kind) for c in part.get(key) or []]
    if not record.get('parts'):
        out += [(c, 'full') for c in record.get('citations') or []]
    return out


def tags_from(records, sources, *, run_id, exclude=frozenset()):
    """({text hash: [tags]}, counts) from a completed run's records and its frozen pages.

    exclude: {(requirement, filename, page number)} a reviewer marked not_evidence; filename comes from the page's
    `filename` field (set by the caller from the run's manifest)."""
    from collections import Counter
    by_id = {s['id']: s for s in sources}
    found, counts = {}, Counter()
    for record in records:
        credit = float(record.get('credit') or 0)
        if credit <= 0:
            counts['requirement_without_credit'] += 1
            continue
        cid = record['condition_id']
        for citation, kind in _cited(record):
            page = by_id.get(citation.get('source_id'))
            if page is None:
                counts['page_not_in_run'] += 1
                continue
            if (cid, page.get('filename'), page.get('page_number')) in exclude:
                counts['excluded_by_review'] += 1
                continue
            quote = ' '.join(str(citation.get('quote') or '').split())
            if not quote or spec.locate(page['text'], quote) is None:
                counts['quote_not_on_page'] += 1
                continue
            strength = 'direct' if kind == 'full' and credit >= 1 else 'supporting'
            found.setdefault(spec.text_hash(page['text']), []).append({
                'indicator': cid.rsplit('.', 1)[0], 'requirements': [cid], 'strength': strength,
                'quote': quote[:2 * spec.QUOTE_MAX], 'quote_found': True,
                'reason': f'Credited by the judge ({kind}) in run {str(run_id)[:8]}.'[:spec.REASON_MAX],
                'origin': ORIGIN, 'learn_version': VERSION, 'run_id': str(run_id)})
            counts['tags'] += 1
    return found, counts


def from_run(run_id, *, map_version, model, exclude=frozenset(), dry_run=False):
    """Add a completed run's credited quotations to the map. Returns (tags added, counts)."""
    from apps.scoring.capability.run_view import ensure, inputs_part
    view = ensure(run_id)
    if view.event_id is None or not isinstance(view.assessment, dict):
        raise ValueError('Only a completed run can be learned from.')
    part = inputs_part(run_id, 'sources', 'manifest') or {}
    names = {str(d.get('document_id')): d.get('filename') for d in part.get('manifest') or []}
    sources = [{**s, 'filename': names.get(str(s.get('document_id')))} for s in part.get('sources') or []
               if (s.get('text') or '').strip()]
    found, counts = tags_from(view.assessment.get('records') or [], sources, run_id=run_id, exclude=exclude)
    if dry_run:
        return 0, counts
    return tagging.add_tags(map_version=map_version, model=model, found=found), counts
