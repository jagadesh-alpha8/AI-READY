"""Conflict detection between documents: deterministic first, AI only as a labelled note.

Finding a conflict is deterministic (apps/facts/verification/conflicts.py): two facts of the same field in the
sprint, that measure the same thing (compatible period, population, unit and included / excluded categories --
verification/scope.py) and state different values once printing differences are removed ("1,234" == 1234).
Facts of an earlier version of the same file are history, not a second source.

Every such pair becomes a conflict gap for a person. The AI (whichever provider is configured, see
`ai_service.get_ai_service`) is asked whether the two could both be true; its answer is appended to the gap as an
"AI-assisted note" and may lower the gap's priority, but it never removes the conflict, never picks a winner, and
never touches either fact's value -- AI confidence alone never resolves a conflict.
"""
import logging

from django.conf import settings

from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem

from ..exceptions import PermanentExtractionError, RecoverableExtractionError
from .ai_service import get_ai_service
from .base import ConflictChecker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are reviewing two pieces of evidence for a higher-education AI-readiness audit \
that appear to disagree on the same field. Decide whether they genuinely conflict, or could both \
honestly be true -- for example because they describe different populations (a department vs. the \
whole institution), different time periods, different units, or one is a subtotal of the other.

You are not choosing which value is correct -- only judging whether the two pieces of evidence \
actually contradict each other. Do not invent context that isn't in the text you were given.

- is_conflict: true only if the two pieces of evidence cannot both be honestly true at once.
- confidence: a number between 0 and 1, reflecting how sure you are of that is_conflict judgement.
- explanation: briefly state, in your own words, what in the two snippets grounds your answer."""

CONFLICT_SCHEMA = {
    'type': 'object',
    'properties': {
        'is_conflict': {'type': 'boolean'},
        'confidence': {'type': 'number', 'description': 'Between 0 and 1.'},
        'explanation': {'type': 'string'},
    },
    'required': ['is_conflict', 'confidence', 'explanation'],
    'additionalProperties': False,
}


class ConflictValidationError(PermanentExtractionError):
    """The AI's conflict verdict failed this app's own validation. Callers
    drop just this one candidate pair, not the whole document."""


class OpenAIConflictChecker(ConflictChecker):
    def __init__(self, *, openai_service=None, max_pairs=None):
        # Lazy, like the other OpenAI-backed services: no client is built
        # until a candidate pair actually needs a semantic judgement.
        self._openai_service = openai_service
        self.max_pairs = max_pairs if max_pairs is not None else settings.GAP_CONFLICT_CHECK_MAX_PAIRS

    def check_conflicts(self, document, mapped_facts):
        pairs = self._candidate_pairs(document)
        if not pairs:
            return []

        # Every pair is a conflict; the AI note is only asked for the first max_pairs (cost bound).
        if len(pairs) > self.max_pairs:
            logger.warning(
                'conflict_checker.too_many_pairs document_id=%s pair_count=%d max_pairs=%d (rest without AI note)',
                document.id, len(pairs), self.max_pairs,
            )

        service = None
        conflicts = []
        for index, (fact_a, fact_b) in enumerate(pairs):
            if index >= self.max_pairs:
                conflicts.append(self._build_gap(fact_a, fact_b, None))
                continue
            service = service or self._openai_service or get_ai_service()
            try:
                verdict = self._evaluate_pair(service, document, fact_a, fact_b)
            except RecoverableExtractionError:
                raise
            except PermanentExtractionError as exc:
                # The deterministic disagreement stands; only the AI's note is missing.
                logger.error(
                    'conflict_checker.pair_failed document_id=%s field_key=%s error=%s',
                    document.id, fact_a.field_key, exc,
                )
                verdict = None

            conflicts.append(self._build_gap(fact_a, fact_b, verdict))

        logger.info(
            'conflict_checker.complete document_id=%s stage=checking_conflicts '
            'pairs_checked=%d conflicts_confirmed=%d',
            document.id, len(pairs), len(conflicts),
        )
        return conflicts

    @staticmethod
    def _candidate_pairs(document):
        """Deterministic: every fact this document contributed, paired with each other live fact of the sprint
        with the same field_key that measures the same thing and states a different value. No AI here."""
        from apps.facts.verification import conflicts as rules
        from apps.facts.verification.normalize import same_value
        from apps.facts.verification.precedent import _lineage

        pairs = []
        lineage = set(_lineage(document))
        for fact_a in rules.live_facts(document.extracted_facts.select_related('source_document', 'document')):
            others = (
                ExtractedFact.objects.filter(sprint=document.sprint, field_key=fact_a.field_key)
                .exclude(document=document)
                .exclude(document_id__in=lineage)  # an earlier version of this same file is history
                .select_related('source_document', 'document')
            )
            for fact_b in rules.live_facts(others):
                if same_value(fact_a.value, fact_b.value, fact_a.data_type):
                    continue  # the same value once printing differences are removed
                if not rules.comparable_pair(fact_a, fact_b)[0]:
                    continue  # different period / population / unit / categories: not the same metric
                pairs.append((fact_a, fact_b))
        return pairs

    @staticmethod
    def _evaluate_pair(service, document, fact_a, fact_b):
        user_content = '\n'.join([
            f'Field: {fact_a.field_name or fact_a.field_key}',
            '',
            f'Evidence A -- from {fact_a.source_document.original_filename if fact_a.source_document else "an earlier document"}:',
            f'  Value: {fact_a.value!r}',
            f'  Snippet: "{fact_a.source_snippet}"',
            '',
            f'Evidence B -- from {fact_b.source_document.original_filename if fact_b.source_document else document.original_filename}:',
            f'  Value: {fact_b.value!r}',
            f'  Snippet: "{fact_b.source_snippet}"',
        ])
        result = service.extract_structured_data(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            response_schema=CONFLICT_SCHEMA,
            schema_name='conflict_verdict',
        )
        return _validate_verdict(result)

    @staticmethod
    def _build_gap(fact_a, fact_b, verdict):
        """The conflict for a person. `verdict` is the AI's view ({'is_conflict', 'confidence', 'explanation'}),
        or None when it could not be asked -- recorded as a labelled note only."""
        from apps.facts.verification import conflicts as rules
        title = f'Conflicting values for {fact_a.field_name or fact_a.field_key}'
        rows = [rules.candidate_row(f) for f in (fact_a, fact_b)]
        description = (f'Sources report different values for "{fact_a.field_name or fact_a.field_key}": '
                       + '; '.join(f'{r["value"]!r} ({rules._where(r)})' for r in rows) + '.')
        priority = GapItem.Priority.HIGH
        if verdict is not None:
            view = ('they genuinely conflict' if verdict['is_conflict']
                    else 'they may both be true')
            description += (f'\n\nAI-assisted note (not a decision; confidence {verdict["confidence"]:.2f}): '
                            f'{view} -- {verdict["explanation"]}')
            if not verdict['is_conflict']:
                priority = GapItem.Priority.MEDIUM
        return {
            'gap_type': GapItem.GapType.CONFLICT,
            'title': title,
            'description': description,
            'pillar': fact_a.pillar,
            'priority': priority,
            'dedup_filter': {'title': title},
            'source_fact': fact_a,
            'conflict_fact_b': fact_b,
            'conflict_value_a': fact_a.value,
            'conflict_value_b': fact_b.value,
            'conflict_confidence': verdict['confidence'] if verdict is not None else None,
        }


def _validate_verdict(result):
    if not isinstance(result, dict):
        raise ConflictValidationError(f'Expected a conflict verdict object, got {type(result).__name__}.')

    is_conflict = result.get('is_conflict')
    if not isinstance(is_conflict, bool):
        raise ConflictValidationError(f'is_conflict must be a boolean, got {is_conflict!r}.')

    confidence = result.get('confidence')
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ConflictValidationError(f'confidence must be a number, got {confidence!r}.')
    if not (0.0 <= confidence <= 1.0):
        raise ConflictValidationError(f'confidence must be between 0 and 1, got {confidence!r}.')

    explanation = result.get('explanation')
    if not isinstance(explanation, str) or not explanation.strip():
        raise ConflictValidationError(f'explanation must be a non-empty string, got {explanation!r}.')

    return {'is_conflict': is_conflict, 'confidence': float(confidence), 'explanation': explanation.strip()}
