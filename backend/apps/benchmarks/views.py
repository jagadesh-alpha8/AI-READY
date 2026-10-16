"""Source Library API for Benchmark Studio (InGage staff only).

Reads: sources, versions, requirement drafts, requirements.
Actions: file intake, approve / withdraw a version, queue AI requirement
drafting, accept / reject a draft. Every action is audited
(SourceAuditEvent); bulk loading stays in the management commands.
"""
from django.db.models import Count, F, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsInGageStaff

from .models import Requirement, RequirementCandidate, SourceDocument, SourceVersion
from .serializers import (
    RequirementCandidateSerializer, RequirementSerializer, SourceDocumentDetailSerializer,
    SourceDocumentListSerializer, SourceVersionSerializer,
)
from .services import approval, file_intake
from .services.requirement_drafting import DraftingError, accept_candidate, reject_candidate

VERSIONS = (SourceVersion.objects.select_related('supersedes', 'approved_by', 'document')
            .annotate(pending_count=Count('requirement_candidates', distinct=True,
                                          filter=Q(requirement_candidates__status='pending')),
                      req_count=Count('requirements', distinct=True))
            # GROUP BY drops Meta.ordering; newest first is what "latest version" relies on.
            .order_by(F('issued_on').desc(nulls_last=True), '-created_at'))


def _documents():
    return (SourceDocument.objects.select_related('framework__authority')
            .prefetch_related(Prefetch('versions', queryset=VERSIONS), 'feeds')
            .annotate(version_count=Count('versions', distinct=True))
            .order_by('source_code'))


class SourceDocumentListView(generics.ListAPIView):
    """GET  /benchmarks/sources?category=&authority=&role=&collection=&q=
       POST /benchmarks/sources  multipart: source fields + optional `file` (services/source_create.py)"""
    serializer_class = SourceDocumentListSerializer
    permission_classes = [IsInGageStaff]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        from .services.source_create import SourceCreateError, create_source
        try:
            doc, _version = create_source(request.user, request.data, upload=request.FILES.get('file'))
        except SourceCreateError as exc:
            return Response({'detail': 'Please fix the highlighted fields.', 'errors': exc.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(SourceDocumentDetailSerializer(_documents().get(pk=doc.pk)).data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        qs = _documents()
        p = self.request.query_params
        if p.get('category'):
            qs = qs.filter(category=p['category'])
        if p.get('authority'):
            qs = qs.filter(framework__authority__code=p['authority'].upper())
        if p.get('role'):
            qs = qs.filter(source_role=p['role'])
        if p.get('collection'):
            qs = qs.filter(versions__collection_status=p['collection']).distinct()
        if p.get('q'):
            qs = qs.filter(Q(title__icontains=p['q']) | Q(source_code__icontains=p['q']))
        return qs


class SourceDocumentDetailView(generics.RetrieveAPIView):
    """GET /benchmarks/sources/<source_code>"""
    serializer_class = SourceDocumentDetailSerializer
    permission_classes = [IsInGageStaff]
    lookup_field = 'source_code'

    def get_queryset(self):
        return _documents()


class SourceReferenceView(APIView):
    """GET /benchmarks/sources/reference -- choices for the Add Source form."""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        from .models import Authority
        from .services.source_create import MAX_FILE_BYTES, supported_extensions
        return Response({
            'authorities': list(Authority.objects.order_by('code').values('code', 'name', 'kind')),
            'authority_kinds': [{'value': k, 'label': l} for k, l in Authority.Kind.choices],
            'source_roles': [{'value': k, 'label': l} for k, l in SourceDocument.Role.choices],
            'categories': sorted(c for c in SourceDocument.objects.values_list('category', flat=True).distinct() if c),
            'document_types': sorted(t for t in SourceDocument.objects.values_list('document_type', flat=True).distinct() if t),
            'file_extensions': supported_extensions(),
            'max_file_mb': MAX_FILE_BYTES // (1024 * 1024),
        })


class SourceLibrarySummaryView(APIView):
    """GET /benchmarks/sources/summary -- counts for the Studio header."""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        versions = SourceVersion.objects.all()
        return Response({
            'documents': SourceDocument.objects.count(),
            'versions': versions.count(),
            'by_collection_status': dict(versions.values_list('collection_status').annotate(n=Count('id'))),
            'by_status': dict(versions.values_list('status').annotate(n=Count('id'))),
            'by_intake_status': dict(versions.values_list('intake_status').annotate(n=Count('id'))),
            'by_category': dict(SourceDocument.objects.values_list('category').annotate(n=Count('id'))),
            'flagged_versions': versions.exclude(review_flags=[]).count(),
            'pending_drafts': RequirementCandidate.objects.filter(status=RequirementCandidate.Status.PENDING).count(),
            'requirements': Requirement.objects.count(),
        })


# -- actions ------------------------------------------------------------------

def _version(pk):
    return get_object_or_404(VERSIONS, pk=pk)


def _version_data(pk):
    return SourceVersionSerializer(_version(pk)).data


class VersionIntakeView(APIView):
    """POST /benchmarks/versions/<id>/intake -- fetch, store and verify this version's file now."""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        result = file_intake.ingest(_version(pk), actor=request.user.email)
        return Response({'result': result.status, 'note': result.note, 'version': _version_data(pk)})


class VersionApproveView(APIView):
    """POST /benchmarks/versions/<id>/approve {note, acknowledge_flags}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        try:
            approval.approve(_version(pk), request.user, note=request.data.get('note', ''),
                             acknowledge_flags=bool(request.data.get('acknowledge_flags')))
        except approval.ApprovalError as exc:
            return Response({'detail': str(exc), 'flags': exc.flags}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_version_data(pk))


class VersionWithdrawView(APIView):
    """POST /benchmarks/versions/<id>/withdraw {note}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        try:
            approval.withdraw(_version(pk), request.user, note=request.data.get('note', ''))
        except approval.ApprovalError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_version_data(pk))


class VersionDraftRequirementsView(APIView):
    """POST /benchmarks/versions/<id>/draft-requirements -- queue AI drafting (Celery)."""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        from .tasks import draft_source_requirements

        version = _version(pk)
        if not version.file_uri:
            return Response({'detail': 'Store and verify the file first (file intake).'},
                            status=status.HTTP_400_BAD_REQUEST)
        queued = SourceVersion.objects.filter(pk=pk).exclude(
            extraction_status__in=[SourceVersion.Extraction.QUEUED, SourceVersion.Extraction.RUNNING],
        ).update(extraction_status=SourceVersion.Extraction.QUEUED, extraction_note='')
        if not queued:
            return Response({'detail': 'Drafting is already queued or running for this version.'},
                            status=status.HTTP_409_CONFLICT)
        try:
            draft_source_requirements.delay(str(pk), actor=request.user.email)
        except Exception as exc:  # broker down: don't leave it "queued" forever
            SourceVersion.objects.filter(pk=pk).update(extraction_status=SourceVersion.Extraction.FAILED,
                                                       extraction_note=f'Could not reach the Celery broker: {exc}')
        return Response(_version_data(pk), status=status.HTTP_202_ACCEPTED)


class VersionCandidatesView(generics.ListAPIView):
    """GET /benchmarks/versions/<id>/candidates?status=pending"""
    serializer_class = RequirementCandidateSerializer
    permission_classes = [IsInGageStaff]

    def get_queryset(self):
        qs = RequirementCandidate.objects.filter(version_id=self.kwargs['pk']).select_related('reviewed_by', 'requirement')
        if self.request.query_params.get('status'):
            qs = qs.filter(status=self.request.query_params['status'])
        return qs


class CandidateReviewView(APIView):
    """POST /benchmarks/candidates/<id>/review {decision: accept|reject, statement?, kind?, note?}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        candidate = get_object_or_404(RequirementCandidate.objects.select_related('version__document'), pk=pk)
        decision = request.data.get('decision')
        try:
            if decision == 'accept':
                accept_candidate(candidate, request.user, statement=request.data.get('statement') or None,
                                 kind=request.data.get('kind') or None, note=request.data.get('note', ''))
            elif decision == 'reject':
                reject_candidate(candidate, request.user, note=request.data.get('note', ''))
            else:
                return Response({'detail': 'decision must be "accept" or "reject".'},
                                status=status.HTTP_400_BAD_REQUEST)
        except DraftingError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        candidate.refresh_from_db()
        return Response(RequirementCandidateSerializer(candidate).data)


class RequirementListView(generics.ListAPIView):
    """GET /benchmarks/requirements?source_code=&kind="""
    serializer_class = RequirementSerializer
    permission_classes = [IsInGageStaff]

    def get_queryset(self):
        qs = (Requirement.objects.select_related('version__document', 'approved_by')
              .prefetch_related('benchmark_links__benchmark'))
        p = self.request.query_params
        if p.get('unlinked'):
            qs = qs.filter(benchmark_links__isnull=True)
        if p.get('source_code'):
            qs = qs.filter(version__document__source_code=p['source_code'])
        if p.get('kind'):
            qs = qs.filter(kind=p['kind'])
        return qs


# -- stage 3: catalogue (read-only; edits come with 3.2/3.3) -----------------------

from .models import Benchmark, EvidenceType, Pillar  # noqa: E402
from .serializers import BenchmarkSerializer, EvidenceTypeSerializer, PillarSerializer  # noqa: E402


def _benchmarks():
    return (Benchmark.objects.select_related('pillar', 'capability')
            .prefetch_related('evidence_types', 'maturity_levels')
            .annotate(requirement_count=Count('requirements', distinct=True))
            .order_by('benchmark_code'))


class BenchmarkListView(generics.ListAPIView):
    """GET /benchmarks/catalogue?pillar=P01&kind=proposed&q=&status=   (withdrawn hidden unless status=withdrawn|all)"""
    serializer_class = BenchmarkSerializer
    permission_classes = [IsInGageStaff]

    def get_queryset(self):
        qs = _benchmarks().select_related('framework')
        p = self.request.query_params
        wanted = p.get('status', '')
        if wanted and wanted != 'all':
            qs = qs.filter(status=wanted)
        elif not wanted:
            qs = qs.exclude(status=Benchmark.Status.WITHDRAWN)
        if p.get('pillar'):
            qs = qs.filter(pillar__code=p['pillar'])
        if p.get('kind'):
            qs = qs.filter(benchmark_kind=p['kind'])
        if p.get('q'):
            qs = qs.filter(Q(title__icontains=p['q']) | Q(benchmark_code__icontains=p['q'])
                           | Q(source_basis__icontains=p['q']))
        return qs


class BenchmarkDetailView(generics.RetrieveAPIView):
    """GET   /benchmarks/catalogue/<benchmark_code>
       PATCH /benchmarks/catalogue/<benchmark_code> {expert_owner, target_guidance}"""
    serializer_class = BenchmarkSerializer
    permission_classes = [IsInGageStaff]
    lookup_field = 'benchmark_code'

    def get_queryset(self):
        return _benchmarks()

    def patch(self, request, benchmark_code):
        from .services import authoring
        try:
            authoring.update_benchmark(get_object_or_404(Benchmark, benchmark_code=benchmark_code), request.user,
                                       request.data)
        except authoring.AuthoringError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BenchmarkSerializer(_benchmarks().get(benchmark_code=benchmark_code)).data)


class PillarListView(generics.ListAPIView):
    """GET /benchmarks/pillars -- with benchmark counts by kind. Withdrawn benchmarks are not
    counted, and a pillar whose benchmarks are all withdrawn (a replaced catalogue) is hidden."""
    serializer_class = PillarSerializer
    permission_classes = [IsInGageStaff]
    pagination_class = None

    def get_queryset(self):
        live = ~Q(benchmarks__status=Benchmark.Status.WITHDRAWN)
        return Pillar.objects.annotate(
            total_count=Count('benchmarks'),
            benchmark_count=Count('benchmarks', filter=live),
            mandatory_count=Count('benchmarks', filter=live & Q(benchmarks__benchmark_kind='mandatory')),
            guidance_count=Count('benchmarks', filter=live & Q(benchmarks__benchmark_kind='guidance')),
            proposed_count=Count('benchmarks', filter=live & Q(benchmarks__benchmark_kind='proposed')),
        ).filter(Q(benchmark_count__gt=0) | Q(total_count=0)).order_by('code')


class EvidenceTypeListView(generics.ListAPIView):
    """GET /benchmarks/evidence-types"""
    serializer_class = EvidenceTypeSerializer
    permission_classes = [IsInGageStaff]
    pagination_class = None
    queryset = EvidenceType.objects.order_by('code')


# -- stage 3.2: requirement <-> benchmark links ----------------------------------

from .models import BenchmarkRequirement  # noqa: E402
from .serializers import BenchmarkLinkSerializer  # noqa: E402
from .services import linking  # noqa: E402


class BenchmarkRequirementsView(APIView):
    """GET  /benchmarks/catalogue/<code>/requirements
       POST /benchmarks/catalogue/<code>/requirements {requirement_code, relationship, note}"""
    permission_classes = [IsInGageStaff]

    def _links(self, benchmark):
        return (BenchmarkRequirement.objects.filter(benchmark=benchmark)
                .select_related('requirement__version__document', 'linked_by', 'benchmark'))

    def get(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        return Response(BenchmarkLinkSerializer(self._links(benchmark), many=True).data)

    def post(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        code = (request.data.get('requirement_code') or '').strip()
        requirement = Requirement.objects.select_related('version').filter(code=code).first()
        if requirement is None:
            return Response({'detail': f'No approved requirement with code "{code}".'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            linking.link(benchmark, requirement, request.user,
                         relationship=request.data.get('relationship', 'primary'), note=request.data.get('note', ''))
        except linking.LinkError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BenchmarkLinkSerializer(self._links(benchmark), many=True).data, status=status.HTTP_201_CREATED)


class BenchmarkRequirementDetailView(APIView):
    """DELETE /benchmarks/catalogue/<code>/requirements/<requirement_code>"""
    permission_classes = [IsInGageStaff]

    def delete(self, request, benchmark_code, requirement_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        requirement = get_object_or_404(Requirement, code=requirement_code)
        try:
            linking.unlink(benchmark, requirement, request.user, note=request.data.get('note', ''))
        except linking.LinkError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequirementSuggestionsView(APIView):
    """GET /benchmarks/requirements/<code>/suggestions -- explainable benchmark suggestions."""
    permission_classes = [IsInGageStaff]

    def get(self, request, code):
        requirement = get_object_or_404(Requirement.objects.select_related('version__document__framework__authority'),
                                        code=code)
        return Response([{'benchmark_code': s['benchmark'].benchmark_code, 'title': s['benchmark'].title,
                          'pillar_code': s['benchmark'].pillar.code, 'score': s['score'], 'reasons': s['reasons']}
                         for s in linking.suggest_benchmarks(requirement, limit=int(request.query_params.get('limit', 5)))])


# -- stage 3.3: writing levels ---------------------------------------------------------

from .serializers import MaturityDefinitionSerializer  # noqa: E402
from .services import authoring  # noqa: E402


class BenchmarkLevelView(APIView):
    """PUT /benchmarks/catalogue/<code>/levels/<L3|L2|L1>
       {definition, measurement_rule, observable_requirements[], minimum_evidence[], outcome_expectations[],
        non_examples[], requires_manual_review, note}"""
    permission_classes = [IsInGageStaff]

    def put(self, request, benchmark_code, level):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        try:
            md = authoring.save_level(benchmark, level.upper(), request.user, request.data)
        except authoring.AuthoringError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(MaturityDefinitionSerializer(md).data)


class BenchmarkReadinessView(APIView):
    """GET /benchmarks/catalogue/<code>/readiness -- what is still missing before release."""
    permission_classes = [IsInGageStaff]

    def get(self, request, benchmark_code):
        return Response(authoring.readiness(get_object_or_404(Benchmark, benchmark_code=benchmark_code)))


class BenchmarkHistoryView(APIView):
    """GET /benchmarks/catalogue/<code>/history -- audited edits, newest first."""
    permission_classes = [IsInGageStaff]

    def get(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        return Response([{'at': e.created_at, 'actor': e.actor, 'action': e.action, 'before': e.before,
                          'after': e.after, 'reason': e.reason} for e in authoring.history(benchmark)])


# -- stage 3.4: evidence rules ------------------------------------------------------------

from .models import EvidenceRule  # noqa: E402
from .serializers import EvidenceRuleSerializer  # noqa: E402
from .services import evidence_rules  # noqa: E402

_RULES = EvidenceRule.objects.select_related('evidence_type', 'benchmark', 'requirement', 'created_by')


class BenchmarkEvidenceRulesView(APIView):
    """GET  /benchmarks/catalogue/<code>/evidence-rules  -- the benchmark's rules + its linked requirements' rules
       POST /benchmarks/catalogue/<code>/evidence-rules  {level?, evidence_type, title, ...}"""
    permission_classes = [IsInGageStaff]

    def get(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        own = _RULES.filter(benchmark=benchmark)
        via = _RULES.filter(requirement__in=benchmark.requirements.all())
        return Response({'benchmark_rules': EvidenceRuleSerializer(own, many=True).data,
                         'requirement_rules': EvidenceRuleSerializer(via, many=True).data,
                         'level_coverage': evidence_rules.level_coverage(benchmark)})

    def post(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        try:
            rule = evidence_rules.create_rule(request.user, request.data, benchmark=benchmark)
        except evidence_rules.EvidenceRuleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EvidenceRuleSerializer(_RULES.get(pk=rule.pk)).data, status=status.HTTP_201_CREATED)


class RequirementEvidenceRulesView(APIView):
    """GET  /benchmarks/requirements/<code>/evidence-rules
       POST /benchmarks/requirements/<code>/evidence-rules  {evidence_type, title, mandatory, minimum_currency_months, scope_rule, ...}"""
    permission_classes = [IsInGageStaff]

    def get(self, request, code):
        requirement = get_object_or_404(Requirement, code=code)
        return Response(EvidenceRuleSerializer(_RULES.filter(requirement=requirement), many=True).data)

    def post(self, request, code):
        requirement = get_object_or_404(Requirement, code=code)
        try:
            rule = evidence_rules.create_rule(request.user, request.data, requirement=requirement)
        except evidence_rules.EvidenceRuleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EvidenceRuleSerializer(_RULES.get(pk=rule.pk)).data, status=status.HTTP_201_CREATED)


class EvidenceRuleDetailView(APIView):
    """PATCH / DELETE /benchmarks/evidence-rules/<id>"""
    permission_classes = [IsInGageStaff]

    def patch(self, request, pk):
        rule = get_object_or_404(_RULES, pk=pk)
        try:
            evidence_rules.update_rule(rule, request.user, request.data)
        except evidence_rules.EvidenceRuleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EvidenceRuleSerializer(_RULES.get(pk=pk)).data)

    def delete(self, request, pk):
        rule = get_object_or_404(_RULES, pk=pk)
        try:
            evidence_rules.delete_rule(rule, request.user)
        except evidence_rules.EvidenceRuleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- stage 3.5: applicability -------------------------------------------------------------

from .models import APPROVAL_BODIES, AUTONOMOUS_STATUSES, ApplicabilityRule, InstitutionType, ProgrammeType  # noqa: E402
from .serializers import ApplicabilityRuleSerializer, InstitutionTypeSerializer, ProgrammeTypeSerializer  # noqa: E402
from .services import applicability  # noqa: E402

_APPLIC = ApplicabilityRule.objects.select_related('benchmark', 'requirement', 'created_by').prefetch_related(
    'institution_types', 'programme_types')


class ApplicabilityReferenceView(APIView):
    """GET /benchmarks/applicability/reference -- the closed lists rules and profiles use."""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        return Response({
            'institution_types': InstitutionTypeSerializer(InstitutionType.objects.all(), many=True).data,
            'programme_types': ProgrammeTypeSerializer(ProgrammeType.objects.all(), many=True).data,
            'autonomous_statuses': [{'code': c, 'name': n} for c, n in AUTONOMOUS_STATUSES],
            'approval_bodies': APPROVAL_BODIES,
            'results': [{'code': c, 'name': n} for c, n in ApplicabilityRule.Result.choices],
        })


class BenchmarkApplicabilityRulesView(APIView):
    """GET/POST /benchmarks/catalogue/<code>/applicability-rules"""
    permission_classes = [IsInGageStaff]

    def get(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        return Response(ApplicabilityRuleSerializer(_APPLIC.filter(benchmark=benchmark), many=True).data)

    def post(self, request, benchmark_code):
        benchmark = get_object_or_404(Benchmark, benchmark_code=benchmark_code)
        try:
            rule = applicability.create_rule(request.user, request.data, benchmark=benchmark)
        except applicability.ApplicabilityError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApplicabilityRuleSerializer(_APPLIC.get(pk=rule.pk)).data, status=status.HTTP_201_CREATED)


class RequirementApplicabilityRulesView(APIView):
    """GET/POST /benchmarks/requirements/<code>/applicability-rules"""
    permission_classes = [IsInGageStaff]

    def get(self, request, code):
        requirement = get_object_or_404(Requirement, code=code)
        return Response(ApplicabilityRuleSerializer(_APPLIC.filter(requirement=requirement), many=True).data)

    def post(self, request, code):
        requirement = get_object_or_404(Requirement, code=code)
        try:
            rule = applicability.create_rule(request.user, request.data, requirement=requirement)
        except applicability.ApplicabilityError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApplicabilityRuleSerializer(_APPLIC.get(pk=rule.pk)).data, status=status.HTTP_201_CREATED)


class ApplicabilityRuleDetailView(APIView):
    """PATCH / DELETE /benchmarks/applicability-rules/<id>"""
    permission_classes = [IsInGageStaff]

    def patch(self, request, pk):
        rule = get_object_or_404(_APPLIC, pk=pk)
        try:
            applicability.update_rule(rule, request.user, request.data)
        except applicability.ApplicabilityError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApplicabilityRuleSerializer(_APPLIC.get(pk=pk)).data)

    def delete(self, request, pk):
        rule = get_object_or_404(_APPLIC, pk=pk)
        try:
            applicability.delete_rule(rule, request.user)
        except applicability.ApplicabilityError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApplicabilityPreviewView(APIView):
    """POST /benchmarks/applicability/preview {institution_type, autonomous_status, programme_types[],
    approval_bodies[], jurisdiction} -> every benchmark with its result and reason."""
    permission_classes = [IsInGageStaff]

    def post(self, request):
        try:
            profile = applicability.Profile.from_data(request.data)
        except applicability.ApplicabilityError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        rows = [{'benchmark_code': r['benchmark'].benchmark_code, 'title': r['benchmark'].title,
                 'pillar_code': r['benchmark'].pillar.code, 'result': r['decision'].result,
                 'reason': r['decision'].reason, 'rule_id': r['decision'].rule_id}
                for r in applicability.resolve_benchmarks(profile)]
        counts = {}
        for row in rows:
            counts[row['result']] = counts.get(row['result'], 0) + 1
        return Response({'counts': counts, 'benchmarks': rows})


# -- stage 3.6: releases ----------------------------------------------------------------

from .models import BenchmarkRelease  # noqa: E402
from .serializers import ReleaseItemSerializer, ReleaseSerializer  # noqa: E402
from .services import releases as release_svc  # noqa: E402


def _release(label):
    return get_object_or_404(BenchmarkRelease.objects.select_related('based_on'), release_label=label)


def _release_payload(release):
    problems, warnings = release_svc.check_release(release) if release.status in ('draft', 'review', 'approved') else ([], [])
    items = release.items.select_related('benchmark__pillar')
    return {**ReleaseSerializer(release).data, 'items': ReleaseItemSerializer(items, many=True).data,
            'problems': problems, 'warnings': warnings}


def _release_error(exc):
    return Response({'detail': str(exc), 'problems': getattr(exc, 'problems', [])}, status=status.HTTP_400_BAD_REQUEST)


class ReleaseListView(APIView):
    """GET /benchmarks/releases   POST {release_label, release_notes}"""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        return Response(ReleaseSerializer(BenchmarkRelease.objects.select_related('based_on'), many=True).data)

    def post(self, request):
        try:
            release = release_svc.create_release(request.data.get('release_label'), request.user,
                                                 request.data.get('release_notes', ''))
        except release_svc.ReleaseError as exc:
            return _release_error(exc)
        return Response(_release_payload(release), status=status.HTTP_201_CREATED)


class CurrentReleaseView(APIView):
    """GET /benchmarks/releases/current -- the release new scorecards must use (404 if none yet)."""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        release = release_svc.current_release()
        if release is None:
            return Response({'detail': 'No release has been published yet.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_release_payload(release))


class ReleaseDetailView(APIView):
    """GET /benchmarks/releases/<label>"""
    permission_classes = [IsInGageStaff]

    def get(self, request, label):
        return Response(_release_payload(_release(label)))


class ReleaseItemsView(APIView):
    """POST /benchmarks/releases/<label>/items {benchmark_code, retire, impact_summary}
       DELETE /benchmarks/releases/<label>/items/<benchmark_code>"""
    permission_classes = [IsInGageStaff]

    def post(self, request, label, benchmark_code=None):
        release = _release(label)
        benchmark = get_object_or_404(Benchmark, benchmark_code=request.data.get('benchmark_code', ''))
        try:
            release_svc.add_item(release, benchmark, request.user, retire=bool(request.data.get('retire')),
                                 impact_summary=request.data.get('impact_summary', ''))
        except release_svc.ReleaseError as exc:
            return _release_error(exc)
        return Response(_release_payload(release), status=status.HTTP_201_CREATED)

    def delete(self, request, label, benchmark_code=None):
        release = _release(label)
        try:
            release_svc.remove_item(release, get_object_or_404(Benchmark, benchmark_code=benchmark_code), request.user)
        except release_svc.ReleaseError as exc:
            return _release_error(exc)
        return Response(_release_payload(release))


class ReleaseActionView(APIView):
    """POST /benchmarks/releases/<label>/<submit|approve|publish|send-back> {note}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, label, action):
        release = _release(label)
        note = request.data.get('note', '')
        try:
            if action == 'submit':
                release_svc.submit(release, request.user)
            elif action == 'approve':
                release_svc.approve(release, request.user, note)
            elif action == 'publish':
                release_svc.publish(release, request.user)
            elif action == 'send-back':
                release_svc.send_back(release, request.user, note)
            else:
                return Response({'detail': 'Unknown action.'}, status=status.HTTP_404_NOT_FOUND)
        except release_svc.ReleaseError as exc:
            return _release_error(exc)
        release.refresh_from_db()
        return Response(_release_payload(release))


class ReleaseDiffView(APIView):
    """GET /benchmarks/releases/<label>/diff -- what changes against the release it is based on."""
    permission_classes = [IsInGageStaff]

    def get(self, request, label):
        return Response(release_svc.diff(_release(label)))


class BenchmarkReopenView(APIView):
    """POST /benchmarks/catalogue/<code>/reopen {reason} -- active benchmark back to draft for the next release."""
    permission_classes = [IsInGageStaff]

    def post(self, request, benchmark_code):
        try:
            release_svc.reopen_benchmark(get_object_or_404(Benchmark, benchmark_code=benchmark_code), request.user,
                                         request.data.get('reason', ''))
        except release_svc.ReleaseError as exc:
            return _release_error(exc)
        return Response(BenchmarkSerializer(_benchmarks().get(benchmark_code=benchmark_code)).data)


# -- Stage 4: daily watcher ---------------------------------------------------------------
from django.conf import settings  # noqa: E402

from .models import SourceChangeEvent, SourceFeed, WatcherRun  # noqa: E402
from .serializers import SourceChangeEventSerializer, SourceFeedSerializer, WatcherRunSerializer  # noqa: E402
from .services import watcher  # noqa: E402

_OPEN = ['triaged', 'under_review']


def _feeds():
    return (SourceFeed.objects.select_related('document__framework__authority')
            .annotate(snapshot_count=Count('snapshots', distinct=True),
                      open_events=Count('change_events', filter=Q(change_events__status__in=_OPEN), distinct=True))
            .order_by('document__source_code', 'endpoint_url'))


def _feed_data(pk):
    return SourceFeedSerializer(_feeds().get(pk=pk)).data


class WatcherSummaryView(APIView):
    """GET /benchmarks/watcher/summary"""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        last = WatcherRun.objects.first()
        open_q = SourceChangeEvent.objects.filter(status__in=_OPEN)
        return Response({
            'schedule_enabled': settings.WATCHER_ENABLED,
            'schedule_hour_utc': settings.WATCHER_HOUR_UTC,
            'feeds': SourceFeed.objects.count(),
            'feeds_enabled': SourceFeed.objects.filter(enabled=True).count(),
            'open_events': open_q.count(),
            'new_events': open_q.filter(status='triaged').count(),
            'last_run': WatcherRunSerializer(last).data if last else None,
        })


class WatcherFeedListView(generics.ListAPIView):
    """GET /benchmarks/watcher/feeds?enabled=true|false&q=..."""
    serializer_class = SourceFeedSerializer
    permission_classes = [IsInGageStaff]
    pagination_class = None

    def get_queryset(self):
        qs = _feeds()
        enabled = self.request.query_params.get('enabled')
        if enabled in ('true', 'false'):
            qs = qs.filter(enabled=enabled == 'true')
        q = self.request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(Q(document__source_code__icontains=q) | Q(document__title__icontains=q)
                           | Q(endpoint_url__icontains=q))
        return qs


class WatcherFeedEnableView(APIView):
    """POST /benchmarks/watcher/feeds/<id>/enable {enabled: bool, note} -- audited."""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        feed = get_object_or_404(SourceFeed, pk=pk)
        enabled = request.data.get('enabled')
        if not isinstance(enabled, bool):
            return Response({'detail': 'enabled must be true or false.'}, status=status.HTTP_400_BAD_REQUEST)
        if enabled and feed.feed_type == SourceFeed.FeedType.MANUAL_UPLOAD:
            return Response({'detail': 'Manual-upload sources have no page to watch; a person uploads new versions.'},
                            status=status.HTTP_400_BAD_REQUEST)
        watcher.set_feed_enabled(feed, request.user, enabled, request.data.get('note', ''))
        return Response(_feed_data(pk))


class WatcherFeedCheckView(APIView):
    """POST /benchmarks/watcher/feeds/<id>/check -- check this one page now (a single request)."""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        feed = get_object_or_404(SourceFeed.objects.select_related('document'), pk=pk)
        result = watcher.check_feed(feed)
        return Response({'result': result, 'feed': _feed_data(pk)})


class WatcherRunListView(APIView):
    """GET /benchmarks/watcher/runs (latest 30)   POST -- queue a run over every enabled feed now."""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        return Response(WatcherRunSerializer(WatcherRun.objects.all()[:30], many=True).data)

    def post(self, request):
        from .tasks import run_source_watcher

        if not SourceFeed.objects.filter(enabled=True).exists():
            return Response({'detail': 'No pages are being watched yet. Turn on the pages to watch first.'},
                            status=status.HTTP_400_BAD_REQUEST)
        run_source_watcher.delay(trigger=request.user.email[:40])
        return Response({'detail': 'Watcher run queued. Refresh in a minute to see the result.'},
                        status=status.HTTP_202_ACCEPTED)


class WatcherEventListView(generics.ListAPIView):
    """GET /benchmarks/watcher/events?status=open|all|triaged|...&source_code=&kind="""
    serializer_class = SourceChangeEventSerializer
    permission_classes = [IsInGageStaff]
    pagination_class = None

    def get_queryset(self):
        qs = SourceChangeEvent.objects.select_related('document', 'feed', 'reviewed_by')
        p = self.request.query_params
        st = p.get('status', 'open')
        if st == 'open':
            qs = qs.filter(status__in=_OPEN)
        elif st != 'all':
            qs = qs.filter(status=st)
        if p.get('source_code'):
            qs = qs.filter(document__source_code=p['source_code'])
        if p.get('kind'):
            qs = qs.filter(change_kind=p['kind'])
        return qs.order_by('-detected_at')[:200]


class WatcherEventReviewView(APIView):
    """POST /benchmarks/watcher/events/<id>/review {status: ignored|under_review|accepted|rejected, note}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        event = get_object_or_404(SourceChangeEvent, pk=pk)
        st, note = request.data.get('status', ''), (request.data.get('note') or '').strip()
        if st in ('ignored', 'rejected', 'accepted') and not note:
            return Response({'detail': 'Please add a short note explaining the decision.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            watcher.review_event(event, request.user, st, note)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        event.refresh_from_db()
        return Response(SourceChangeEventSerializer(event).data)


# -- Stage 4b: benchmark candidates -----------------------------------------------------
from .models import BenchmarkCandidate  # noqa: E402
from .serializers import BenchmarkCandidateSerializer  # noqa: E402
from .services import candidates as candidate_svc  # noqa: E402


def _candidate(pk):
    return get_object_or_404(
        BenchmarkCandidate.objects.select_related('benchmark', 'source_document', 'change_event')
        .prefetch_related('reviews__reviewer'), pk=pk)


def _candidate_error(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BenchmarkCandidateListView(APIView):
    """GET /benchmarks/benchmark-candidates?status=open|all|research|review|approved|rejected|published
       POST {candidate_type, title, source_rationale, benchmark_code?, source_code?, change_event?}"""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        qs = (BenchmarkCandidate.objects.select_related('benchmark', 'source_document', 'change_event')
              .prefetch_related('reviews__reviewer'))
        st = request.query_params.get('status', 'open')
        if st == 'open':
            qs = qs.filter(status__in=candidate_svc.OPEN_STATUSES)
        elif st != 'all':
            qs = qs.filter(status=st)
        return Response(BenchmarkCandidateSerializer(qs.order_by('-created_at')[:300], many=True).data)

    def post(self, request):
        try:
            c = candidate_svc.create(request.user, request.data)
        except candidate_svc.CandidateError as exc:
            return _candidate_error(exc)
        return Response(BenchmarkCandidateSerializer(_candidate(c.pk)).data, status=status.HTTP_201_CREATED)


class BenchmarkCandidateDetailView(APIView):
    """GET / PATCH /benchmarks/benchmark-candidates/<id>"""
    permission_classes = [IsInGageStaff]

    def get(self, request, pk):
        return Response(BenchmarkCandidateSerializer(_candidate(pk)).data)

    def patch(self, request, pk):
        try:
            candidate_svc.update(_candidate(pk), request.user, request.data)
        except candidate_svc.CandidateError as exc:
            return _candidate_error(exc)
        return Response(BenchmarkCandidateSerializer(_candidate(pk)).data)


class BenchmarkCandidateActionView(APIView):
    """POST /benchmarks/benchmark-candidates/<id>/submit
       POST /benchmarks/benchmark-candidates/<id>/review {reviewer_role, decision, notes}
       POST /benchmarks/benchmark-candidates/<id>/open-revision"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk, action):
        c = _candidate(pk)
        try:
            if action == 'submit':
                candidate_svc.submit(c, request.user)
            elif action == 'review':
                candidate_svc.review(c, request.user, request.data.get('reviewer_role', ''),
                                     request.data.get('decision', ''), request.data.get('notes', ''))
            elif action == 'open-revision':
                candidate_svc.reopen_for_revision(c, request.user)
            else:
                return Response({'detail': 'Unknown action.'}, status=status.HTTP_404_NOT_FOUND)
        except candidate_svc.CandidateError as exc:
            return _candidate_error(exc)
        return Response(BenchmarkCandidateSerializer(_candidate(pk)).data)


class WatcherEventProposeView(APIView):
    """POST /benchmarks/watcher/events/<id>/propose -- the watcher's automatic
    candidates for this event, if none were made (e.g. below the threshold) a
    'review this source' candidate in research."""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        event = get_object_or_404(SourceChangeEvent.objects.select_related('document', 'feed'), pk=pk)
        if event.candidates.exists():
            return Response({'detail': 'This change already has candidates.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            c = candidate_svc.create(request.user, {
                'candidate_type': 'source_update', 'change_event': str(event.pk),
                'title': f'Review the change to {event.document.source_code}: {event.document.title}'[:300],
                'source_rationale': candidate_svc._rationale(event)})
        except candidate_svc.CandidateError as exc:
            return _candidate_error(exc)
        return Response(BenchmarkCandidateSerializer(_candidate(c.pk)).data, status=status.HTTP_201_CREATED)


# -- confirming a draft benchmark (separate from publishing) ---------------------------------------
from .services import confirmation as confirmation_svc  # noqa: E402


class BenchmarkConfirmView(APIView):
    """POST /benchmarks/catalogue/<code>/confirm {note}
       POST /benchmarks/catalogue/<code>/unconfirm {reason}"""
    permission_classes = [IsInGageStaff]

    def post(self, request, benchmark_code, action='confirm'):
        benchmark = get_object_or_404(Benchmark.objects.select_related('pillar', 'capability'), benchmark_code=benchmark_code)
        try:
            if action == 'confirm':
                confirmation_svc.confirm(benchmark, request.user, request.data.get('note', ''))
            else:
                confirmation_svc.withdraw_confirmation(benchmark, request.user, request.data.get('reason', ''))
        except confirmation_svc.ConfirmationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BenchmarkSerializer(_benchmarks().get(benchmark_code=benchmark_code)).data)


class BenchmarkUnconfirmView(BenchmarkConfirmView):
    def post(self, request, benchmark_code):
        return super().post(request, benchmark_code, action='unconfirm')
