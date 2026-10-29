"""Conflict detection that compares like with like, and conflict summaries that never go stale.

- `disagreements(facts)`: groups of a field's facts that measure the same thing (scope.comparable) and state
  different values once printing differences are removed (normalize.same_value). "1,234" vs 1234 is not a
  conflict; 2022-23 vs 2023-24 is not the same metric; the same file's earlier version is history, not a second
  source. Anything left that disagrees IS a conflict -- the AI may add a note, never remove one.
- `candidate_rows(facts)`: each candidate as a person needs to see it: value, document and version, page, period,
  population, validation and grounding result.
- `summary(gap)` / `refresh(gap)`: the conflict's description rebuilt from the facts as they are now; called
  whenever a candidate fact changes (review, correction, re-extraction).
"""
from apps.facts.models import ExtractedFact

from . import normalize, scope as scope_mod


def live_facts(facts):
    """Not rejected, and not from a document superseded by a newer version (that version speaks for it)."""
    out = []
    for fact in facts:
        if fact.status == ExtractedFact.Status.REJECTED:
            continue
        doc = fact.source_document or fact.document
        if doc is not None and doc.superseded_at is not None:
            continue
        out.append(fact)
    return out


def disagreements(facts):
    """[[fact, ...], ...]: each a set of comparable facts with more than one distinct value."""
    facts = live_facts(facts)
    scopes = {f.pk: scope_mod.read_scope(f) for f in facts}
    groups = []
    for fact in facts:
        for group in groups:
            if all(scope_mod.comparable(scopes[fact.pk], scopes[g.pk])[0] for g in group):
                group.append(fact)
                break
        else:
            groups.append([fact])
    out = []
    for group in groups:
        kinds = {normalize.comparable_value(f.value, f.data_type) for f in group}
        if len(kinds) > 1:
            out.append(group)
    return out


def comparable_pair(a, b):
    """(compatible, why_not) for two facts of the same field."""
    return scope_mod.comparable(scope_mod.read_scope(a), scope_mod.read_scope(b))


def candidate_row(fact):
    doc = fact.source_document or fact.document
    s = scope_mod.read_scope(fact)
    return {'fact_id': str(fact.id), 'value': fact.value, 'status': fact.status,
            'document_id': str(doc.id) if doc else None,
            'document_name': (doc.original_filename or doc.title) if doc else None,
            'document_version': doc.version_number if doc else None,
            'superseded': bool(doc and doc.superseded_at), 'page': fact.source_page or None,
            'period': s.get('period') or None, 'population': s.get('population') or [], 'unit': s.get('unit'),
            'includes': s.get('includes') or [], 'excludes': s.get('excludes') or [],
            'validation_status': fact.validation_status or None, 'grounding_status': fact.grounding_status or None,
            'verification_status': fact.verification_status or None}


def _where(row):
    parts = [row['document_name'] or 'an unknown document']
    if row.get('document_version'):
        parts[0] += f' v{row["document_version"]}'
    if row.get('page'):
        parts.append(f'page {row["page"]}')
    if row.get('period'):
        parts.append(row['period'])
    return ', '.join(parts)


def summary(gap):
    """The conflict's description from its facts as they are now."""
    from apps.gaps.services import conflict_facts
    facts = [f for f in conflict_facts(gap) if f.sprint_id == gap.sprint_id]
    rows = [candidate_row(f) for f in live_facts(facts)]
    if not rows:
        return 'None of the facts this conflict compared is still in play.'
    field = (gap.source_fact.field_name or gap.source_fact.field_key) if gap.source_fact_id else 'this field'
    values = '; '.join(f'{r["value"]!r} ({_where(r)})' for r in rows)
    distinct = {normalize.comparable_value(f.value, f.data_type) for f in live_facts(facts)}
    head = (f'Sources report {len(distinct)} different values for "{field}": ' if len(distinct) > 1
            else f'The sources now agree on "{field}": ')
    return head + values + '.'


def refresh(gap, *, user=None):
    """Rewrite a conflict's description from its live facts (with an event when it changed). Returns True if it
    changed. The detection-time snapshots (conflict_value_a/b) are kept: they are labelled 'at detection'."""
    from apps.gaps.models import GapEvent, GapItem
    if gap.gap_type != GapItem.GapType.CONFLICT:
        return False
    text = summary(gap)
    note = ''
    marker = '\n\nAI-assisted note'
    if marker in (gap.description or ''):
        note = gap.description[gap.description.index(marker):]
    new = text + note
    if new == gap.description:
        return False
    old = gap.description
    gap.description = new
    gap.save(update_fields=['description', 'updated_at'])
    GapEvent.objects.create(gap=gap, action=GapEvent.Action.SUMMARY_REFRESHED, user=user,
                            note='A fact this conflict compares changed.', data={'previous': old[:2000]})
    return True


def refresh_for_field(sprint_id, field_key, *, user=None):
    from apps.gaps.models import GapItem
    changed = 0
    for gap in GapItem.objects.filter(sprint_id=sprint_id, gap_type=GapItem.GapType.CONFLICT,
                                      status__in=GapItem.ACTIVE_STATUSES,
                                      source_fact__field_key__iexact=field_key).select_related(
            'source_fact', 'conflict_fact_b'):
        changed += refresh(gap, user=user)
    return changed
