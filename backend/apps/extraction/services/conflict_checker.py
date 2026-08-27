"""Real, AI-backed `ConflictChecker`.

Per "do not replace deterministic business rules with AI unnecessarily":
finding *candidate* conflicts (two facts sharing a field_key with different
normalized values) is a cheap, deterministic set comparison -- AI (whichever
provider is configured, see `ai_service.get_ai_service`) is only ever
consulted to interpret a pair that's already been found to disagree,
deciding whether they genuinely conflict or could both be true (different
populations, timeframes, or units). It never picks a winner: the two facts'
own `value`s are never touched here, only a GapItem describing the
disagreement is created, for a human to actually resolve.
"""
import json
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


def _hashable(value):
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value


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

        if len(pairs) > self.max_pairs:
            logger.warning(
                'conflict_checker.too_many_pairs document_id=%s pair_count=%d max_pairs=%d',
                document.id, len(pairs), self.max_pairs,
            )
            pairs = pairs[:self.max_pairs]

        service = self._openai_service or get_ai_service()
        conflicts = []
        for fact_a, fact_b in pairs:
            try:
                verdict = self._evaluate_pair(service, document, fact_a, fact_b)
            except RecoverableExtractionError:
                raise
            except PermanentExtractionError as exc:
                logger.error(
                    'conflict_checker.pair_failed document_id=%s field_key=%s error=%s',
                    document.id, fact_a.field_key, exc,
                )
                continue

            if verdict is None:
                continue
            conflicts.append(self._build_gap(fact_a, fact_b, verdict))

        logger.info(
            'conflict_checker.complete document_id=%s stage=checking_conflicts '
            'pairs_checked=%d conflicts_confirmed=%d',
            document.id, len(pairs), len(conflicts),
        )
        return conflicts

    @staticmethod
    def _candidate_pairs(document):
        """Deterministic pre-filter: every fact this document contributed,
        paired with any other active fact in the sprint that shares its
        field_key but genuinely disagrees on normalized_value. No AI here --
        just a set comparison."""
        pairs = []
        for fact_a in document.extracted_facts.exclude(status=ExtractedFact.Status.REJECTED):
            others = (
                ExtractedFact.objects.filter(sprint=document.sprint, field_key=fact_a.field_key)
                .exclude(document=document)
                .exclude(status=ExtractedFact.Status.REJECTED)
            )
            for fact_b in others:
                if _hashable(fact_a.normalized_value) == _hashable(fact_b.normalized_value):
                    continue  # normalized values genuinely match -- nothing to interpret
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
        title = f'Conflicting values for {fact_a.field_name or fact_a.field_key}'
        return {
            'gap_type': GapItem.GapType.CONFLICT,
            'title': title,
            'description': verdict['explanation'],
            'pillar': fact_a.pillar,
            'priority': GapItem.Priority.HIGH,
            'dedup_filter': {'title': title},
            'source_fact': fact_a,
            'conflict_fact_b': fact_b,
            'conflict_value_a': fact_a.value,
            'conflict_value_b': fact_b.value,
            'conflict_confidence': verdict['confidence'],
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

    if not is_conflict:
        return None
    return {'confidence': float(confidence), 'explanation': explanation.strip()}
