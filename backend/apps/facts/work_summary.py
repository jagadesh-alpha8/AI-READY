"""Outstanding confirmation work for a whole sprint -- every owner role, not the viewer's -- by role and by
assignee, and whether the sprint is ready for baseline review (GET /sprints/<id>/work-summary).

Ready for baseline review = no fact still waiting for a review (extracted or evidence requested), and no
open gap about a fact (needs confirmation, low confidence, conflict, rejected - needs replacement).
Document gaps (missing / stale) are counted too, but baseline approval itself decides on blocking gaps.
"""
from datetime import date

from apps.gaps.models import GapItem

from . import ownership
from .models import ExtractedFact

PENDING_FACT_STATUSES = (ExtractedFact.Status.EXTRACTED, ExtractedFact.Status.EVIDENCE_REQUESTED)
FACT_GAP_TYPES = (GapItem.GapType.UNCONFIRMED_FACT, GapItem.GapType.LOW_CONFIDENCE, GapItem.GapType.CONFLICT)


def _bucket(store, key, **meta):
    if key not in store:
        store[key] = {**meta, 'pending_facts': 0, 'evidence_requested': 0, 'open_gaps': 0, 'conflicts': 0,
                      'needs_replacement': 0, 'unassigned': 0, 'overdue': 0, 'total': 0}
    return store[key]


def _count(row, *, kind, status, assigned, overdue, gap_type=None):
    row['total'] += 1
    if kind == 'fact':
        row['pending_facts'] += 1
        if status == ExtractedFact.Status.EVIDENCE_REQUESTED:
            row['evidence_requested'] += 1
    else:
        row['open_gaps'] += 1
        if gap_type == GapItem.GapType.CONFLICT:
            row['conflicts'] += 1
        if status == GapItem.Status.NEEDS_REPLACEMENT:
            row['needs_replacement'] += 1
    if not assigned:
        row['unassigned'] += 1
    if overdue:
        row['overdue'] += 1


def work_summary(sprint):
    today = date.today()
    by_role, by_assignee = {}, {}
    facts = (ExtractedFact.objects.filter(sprint=sprint, status__in=PENDING_FACT_STATUSES)
             .select_related('assigned_to'))
    gaps = (GapItem.objects.filter(sprint=sprint, status__in=GapItem.ACTIVE_STATUSES)
            .select_related('source_fact', 'related_document', 'assigned_to'))
    fact_gaps = blocking = 0

    items = [('fact', f, ownership.fact_owner_role(f), None) for f in facts]
    items += [('gap', g, ownership.gap_owner_role(g), g.gap_type) for g in gaps]
    for kind, item, role, gap_type in items:
        assigned = item.assigned_to
        overdue = bool(item.due_date and item.due_date < today)
        meta_role = {'role': role, 'label': ownership.role_label(role) or 'Coordinators (no owner role)'}
        _count(_bucket(by_role, role or '', **meta_role), kind=kind, status=item.status, assigned=assigned,
               overdue=overdue, gap_type=gap_type)
        key = str(assigned.id) if assigned else ''
        meta_person = ({'user_id': key, 'name': ownership.person_name(assigned), 'role': assigned.role}
                       if assigned else {'user_id': None, 'name': 'Unassigned', 'role': ''})
        _count(_bucket(by_assignee, key, **meta_person), kind=kind, status=item.status, assigned=assigned,
               overdue=overdue, gap_type=gap_type)
        if kind == 'gap':
            if gap_type in FACT_GAP_TYPES or item.status == GapItem.Status.NEEDS_REPLACEMENT:
                fact_gaps += 1
            if item.priority == GapItem.Priority.BLOCKING:
                blocking += 1

    pending = facts.count()
    blockers = []
    if pending:
        blockers.append(f'{pending} fact(s) still need a review (confirm, correct or reject).')
    if fact_gaps:
        blockers.append(f'{fact_gaps} open gap(s) about facts (confirmation, low confidence, conflicts or '
                        'rejected values needing replacement).')
    return {
        'ready_for_baseline_review': not blockers,
        'blockers': blockers,
        'totals': {'pending_facts': pending, 'open_gaps': gaps.count(), 'fact_gaps': fact_gaps,
                   'blocking_gaps': blocking, 'unassigned': sum(r['unassigned'] for r in by_role.values()),
                   'overdue': sum(r['overdue'] for r in by_role.values())},
        'by_role': sorted(by_role.values(), key=lambda r: (-r['total'], r['label'])),
        'by_assignee': sorted(by_assignee.values(), key=lambda r: (r['user_id'] is not None, -r['total'], r['name'])),
    }
