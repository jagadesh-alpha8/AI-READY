"""Dependency analysis and safe deletion enforcement for Institution records."""

import logging
from django.db import models
from django.db.models import ProtectedError

logger = logging.getLogger(__name__)


def get_institution_deletion_dependencies(institution):
    """Inspect all related models to determine whether the institution can be safely deleted.

    Protected / historically significant records that BLOCK permanent deletion:
    - Sprints (any sprint)
    - Documents (sprint documents)
    - Extracted facts
    - Evidence requests & evidence submissions (EvidenceRequestDocument)
    - Gaps, Baselines, and Reports
    - Benchmark assessment cycles and evidence items
    - Historical audit logs

    Safe institutional DNA records that can cascade when no protected records exist:
    - Departments
    - Leaders
    - Systems
    - Coordinator invitations & events
    """
    from apps.sprints.models import Sprint
    from apps.documents.models import Document
    from apps.facts.models import (
        EvidenceRequest,
        EvidenceRequestDocument,
        EvidenceRequestEvent,
        ExtractedFact,
        FactReviewHistory,
    )
    from apps.gaps.models import GapItem
    from apps.scoring.models import Baseline
    from apps.reports.models import Report
    from apps.assessments.models import AssessmentCycle, BenchmarkAssessment, EvidenceItem
    from apps.institutions.models import CoordinatorEvent

    sprint_ids = list(Sprint.objects.filter(institution=institution).values_list('id', flat=True))
    sprint_count = len(sprint_ids)

    doc_count = Document.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0
    fact_count = ExtractedFact.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0
    req_count = EvidenceRequest.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0
    sub_count = (
        EvidenceRequestDocument.objects.filter(request__sprint_id__in=sprint_ids).count()
        if sprint_count else 0
    )
    gap_count = GapItem.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0
    baseline_count = Baseline.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0
    report_count = Report.objects.filter(sprint_id__in=sprint_ids).count() if sprint_count else 0

    fact_history_count = (
        FactReviewHistory.objects.filter(fact__sprint_id__in=sprint_ids).count()
        if sprint_count else 0
    )
    req_event_count = (
        EvidenceRequestEvent.objects.filter(request__sprint_id__in=sprint_ids).count()
        if sprint_count else 0
    )

    benchmark_cycle_count = AssessmentCycle.objects.filter(institution=institution).count()
    if benchmark_cycle_count > 0:
        benchmark_assessment_count = BenchmarkAssessment.objects.filter(applicable__cycle__institution=institution).count()
        benchmark_evidence_count = EvidenceItem.objects.filter(cycle__institution=institution).count()
    else:
        benchmark_assessment_count = 0
        benchmark_evidence_count = 0

    coordinator_events_count = CoordinatorEvent.objects.filter(institution=institution).count()

    dept_count = institution.departments.count()
    leader_count = institution.leaders.count()
    system_count = institution.systems.count()

    # Total audit records across facts, requests, and benchmarks
    total_audit_records = (
        fact_history_count + req_event_count + (1 if benchmark_cycle_count > 0 else 0)
    )

    has_protected_records = (
        sprint_count > 0
        or doc_count > 0
        or fact_count > 0
        or req_count > 0
        or sub_count > 0
        or gap_count > 0
        or baseline_count > 0
        or report_count > 0
        or benchmark_cycle_count > 0
        or benchmark_assessment_count > 0
        or benchmark_evidence_count > 0
    )

    block_items = []
    if sprint_count > 0:
        block_items.append(f"{sprint_count} sprint{'s' if sprint_count > 1 else ''}")
    if doc_count > 0:
        block_items.append(f"{doc_count} document{'s' if doc_count > 1 else ''}")
    if fact_count > 0:
        block_items.append(f"{fact_count} extracted fact{'s' if fact_count > 1 else ''}")
    if sub_count > 0:
        block_items.append(f"{sub_count} evidence submission{'s' if sub_count > 1 else ''}")
    elif req_count > 0:
        block_items.append(f"{req_count} evidence request{'s' if req_count > 1 else ''}")
    if baseline_count > 0:
        block_items.append(f"{baseline_count} approved baseline{'s' if baseline_count > 1 else ''}")
    if report_count > 0:
        block_items.append(f"{report_count} report{'s' if report_count > 1 else ''}")
    if benchmark_cycle_count > 0 or benchmark_assessment_count > 0:
        block_items.append(f"{benchmark_cycle_count} benchmark assessment cycle{'s' if benchmark_cycle_count > 1 else ''}")

    if has_protected_records:
        block_reason = (
            f"Cannot delete '{institution.name}' because it contains protected assessment evidence and audit records "
            f"({', '.join(block_items)}). Permanent deletion would destroy historical audit lineage and evidence records. "
            "Archive or deactivate this institution instead to preserve data integrity."
        )
    else:
        block_reason = None

    dependencies = {
        'sprints': sprint_count,
        'documents': doc_count,
        'facts': fact_count,
        'evidence_requests': req_count,
        'evidence_submissions': sub_count,
        'gaps': gap_count,
        'baselines': baseline_count,
        'reports': report_count,
        'benchmark_cycles': benchmark_cycle_count,
        'benchmark_assessments': benchmark_assessment_count,
        'benchmark_evidence': benchmark_evidence_count,
        'audit_records': total_audit_records,
        'coordinator_events': coordinator_events_count,
        'departments': dept_count,
        'leaders': leader_count,
        'systems': system_count,
    }

    protected_counts = {
        'sprints': sprint_count,
        'documents': doc_count,
        'facts': fact_count,
        'evidence_requests': req_count,
        'evidence_submissions': sub_count,
        'baselines': baseline_count,
        'reports': report_count,
        'benchmark_assessments': benchmark_assessment_count,
        'audit_records': total_audit_records,
    }

    return {
        'institution_id': str(institution.id),
        'institution_name': institution.name,
        'can_delete': not has_protected_records,
        'is_blocked': has_protected_records,
        'block_reason': block_reason,
        'recommended_action': 'archive' if has_protected_records else 'delete',
        'alternative_available': True,
        'alternative_action': 'archive',
        'dependencies': dependencies,
        'protected_counts': protected_counts,
    }
