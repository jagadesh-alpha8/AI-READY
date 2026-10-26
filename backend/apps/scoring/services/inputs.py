"""What a sprint's CRI depends on, as one fingerprint -- so a ScoringRun can be checked against the current data.

`scoring_inputs_fingerprint(sprint)` hashes every input the scoring engine and the coverage calculation read:
the sprint's facts (status, pillar, field, value change), their AI-QIF tags (review decisions, relationship,
indicator), its gaps (status, priority, pillar), its documents (processing state), the active scoring
configuration (pillars, criteria, weights), the published benchmark release and the college's benchmark
profile. `run_scoring_engine` stores it on each ScoringRun; a run whose fingerprint differs from the current one
no longer describes the sprint (services/baseline.py uses this to keep a pending baseline current).

Plain database reads, no AI, no writes.
"""
import hashlib
import json


def _rows(qs, *fields):
    return [list(r) for r in qs.order_by('pk').values_list('pk', *fields)]


def scoring_inputs_fingerprint(sprint):
    from apps.documents.models import Document
    from apps.facts.models import ExtractedFact, FactAIQIFMapping
    from apps.gaps.models import GapItem

    from ..models import Pillar, PillarCriterion

    parts = {
        'facts': _rows(ExtractedFact.objects.filter(sprint=sprint), 'status', 'pillar', 'field_key', 'updated_at'),
        'tags': _rows(FactAIQIFMapping.objects.filter(fact__sprint=sprint), 'indicator_code', 'criterion', 'status',
                      'review_status', 'relationship', 'auto_decision', 'pending_since', 'reviewed_at'),
        'gaps': _rows(GapItem.objects.filter(sprint=sprint), 'status', 'priority', 'pillar', 'updated_at'),
        'documents': _rows(Document.objects.filter(sprint=sprint), 'status', 'processing_status', 'updated_at'),
        'pillars': _rows(Pillar.objects.all(), 'key', 'weight', 'is_active', 'updated_at'),
        'criteria': _rows(PillarCriterion.objects.all(), 'key', 'weight', 'is_active', 'updated_at'),
        'release': _release(),
        'profile': _profile(sprint.institution_id),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _release():
    from apps.benchmarks.services.releases import current_release
    release = current_release()
    return [str(release.pk), release.content_hash] if release else None


def _profile(institution_id):
    from apps.assessments.models import BenchmarkProfile, Programme
    profile = BenchmarkProfile.objects.filter(institution_id=institution_id).values_list('updated_at', flat=True).first()
    programmes = _rows(Programme.objects.filter(institution_id=institution_id), 'programme_type_id', 'approval_body',
                       'active')
    return [str(profile), programmes]
