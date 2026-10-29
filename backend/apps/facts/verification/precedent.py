"""Earlier reviewer decisions that can save a repeated review -- with the safeguards spelled out.

The precedent rules (all must hold for an EXACT match, which policy.decide may use in place of a person):

1. Same sprint. A decision is never carried to another sprint (or institution).
2. Same field (field_key, case-insensitive).
3. The earlier fact was decided by a person (confirmed, corrected or rejected) -- never by the rules, so a
   precedent cannot chain automatic decisions -- and that decision still stands.
4. The earlier fact's document is an earlier *version* of this fact's document (the same file uploaded again),
   or the same document.
5. The same value, the same quote (word for word, after normalization) and the same scope (period, population).
6. The new fact passes its own verification first (policy.decide only consults a precedent for `verified` facts):
   an earlier value is never evidence that a new value is true -- the precedent only stands in for the human
   judgement that this kind of citation is acceptable.

Anything less is a PARTIAL match: shown to the reviewer as a suggestion ("confirmed 42 from v1, page 3; the quote
differs"), never applied. A matching person's REJECTION is shown as a warning and the fact goes to review; the rules
never reject anything.
"""
from apps.facts.models import ExtractedFact

from . import normalize, scope as scope_mod

DECIDED = (ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED, ExtractedFact.Status.REJECTED)


def _lineage(document):
    """This document and every earlier version of it."""
    seen, out = set(), []
    while document is not None and document.pk not in seen:
        seen.add(document.pk)
        out.append(document.pk)
        document = document.previous_version
    return out


def find(fact, fact_scope):
    """The closest earlier person decision for `fact`, or None:
    {'match': 'exact'|'partial'|'rejected', 'fact_id', 'action', 'value', 'decided_by', 'decided_by_name',
     'decided_at', 'document_version', 'source_page', 'differences': [...]}"""
    from apps.facts.auto_confirm import AUTO_CONFIRM_EMAIL
    if not fact.sprint_id or not fact.field_key:
        return None
    candidates = (ExtractedFact.objects.filter(sprint_id=fact.sprint_id, field_key__iexact=fact.field_key,
                                               status__in=DECIDED, reviewed_by__isnull=False)
                  .exclude(pk=fact.pk).exclude(reviewed_by__email=AUTO_CONFIRM_EMAIL)
                  .select_related('reviewed_by', 'document', 'source_document').order_by('-reviewed_at'))
    lineage = _lineage(fact.document) if fact.document_id else []
    quote = ' '.join(normalize.tokens(fact.source_snippet))
    best = None
    for earlier in candidates[:20]:
        differences = []
        if earlier.document_id not in lineage:
            differences.append('a different document (not an earlier version of this one)')
        if not normalize.same_value(earlier.value, fact.value, fact.data_type):
            differences.append(f'a different value ({earlier.value!r})')
        if ' '.join(normalize.tokens(earlier.source_snippet)) != quote:
            differences.append('a different quote')
        earlier_scope = scope_mod.read_scope(earlier)
        ok, why = scope_mod.comparable(fact_scope, earlier_scope)
        if not ok:
            differences.append(why)
        elif scope_mod.unknown_parts(fact_scope, earlier_scope) and earlier_scope.get('period') != fact_scope.get('period'):
            differences.append('the reporting period could not be matched')
        rejected = earlier.status == ExtractedFact.Status.REJECTED
        match = 'rejected' if rejected and len(differences) <= 1 else (
            'exact' if not differences and not rejected else 'partial')
        if rejected and len(differences) > 1:
            continue  # an unrelated rejection says nothing about this fact
        row = {'match': match, 'fact_id': str(earlier.id), 'action': earlier.get_status_display().lower(),
               'value': earlier.value, 'decided_by': str(earlier.reviewed_by_id),
               'decided_by_name': earlier.reviewed_by.get_full_name() or earlier.reviewed_by.email,
               'decided_at': earlier.reviewed_at.isoformat() if earlier.reviewed_at else None,
               'document_version': (earlier.source_document or earlier.document).version_number
               if (earlier.source_document or earlier.document) else None,
               'source_page': earlier.source_page, 'differences': differences}
        rank = {'exact': 0, 'rejected': 1, 'partial': 2}[match], len(differences)
        if best is None or rank < best[0]:
            best = (rank, row)
    return best[1] if best else None
