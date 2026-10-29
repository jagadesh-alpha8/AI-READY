"""Stage 5 API. InGage staff run assessments; college members (not viewers) upload
evidence for their own college; everyone sees only their own college. A college
sees its scorecard once the assessment is finalized."""
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsInGageStaff, get_accessible_institution_ids, require_institution_access
from apps.benchmarks.models import (
    APPROVAL_BODIES, AUTONOMOUS_STATUSES, Benchmark, InstitutionType, ProgrammeType,
)
from apps.benchmarks.services.releases import current_release
from apps.institutions.models import Institution

from . import services as svc
from .models import (
    ApplicableBenchmark, AssessmentCycle, BenchmarkProfile, BenchmarkScoreRule, EvidenceItem, ScoringModel,
)
from .serializers import AssessmentSerializer, CycleSerializer, EvidenceItemSerializer, ProgrammeSerializer

Status = AssessmentCycle.Status


def _staff(user):
    return user.role in User.CROSS_INSTITUTION_ROLES


def _err(exc):
    return Response({'detail': str(exc), 'problems': getattr(exc, 'problems', [])}, status=status.HTTP_400_BAD_REQUEST)


def _forbid(msg='Only InGage staff can do this.'):
    return Response({'detail': msg}, status=status.HTTP_403_FORBIDDEN)


def _can_upload(user):
    return user.role in {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR}


def _cycle(request, pk):
    cycle = get_object_or_404(AssessmentCycle.objects.select_related('institution', 'release', 'created_by',
                                                                      'finalized_by'), pk=pk)
    require_institution_access(request.user, cycle)
    return cycle


def _applicable(request, pk, code):
    cycle = _cycle(request, pk)
    ab = get_object_or_404(ApplicableBenchmark.objects.select_related('benchmark', 'release_item', 'cycle'),
                           cycle=cycle, benchmark__benchmark_code=code)
    return cycle, ab


def _scores_visible(request, cycle):
    return _staff(request.user) or cycle.status == Status.FINALIZED


def _row(ab, show_scores):
    snap = ab.snapshot
    a = getattr(ab, 'assessment', None)
    return {
        'benchmark_code': ab.benchmark.benchmark_code, 'title': snap.get('title'), 'pillar': snap.get('pillar'),
        'kind': snap.get('kind'), 'applicability_result': ab.applicability_result,
        'applicability_reason': ab.applicability_reason.get('reason', ''), 'included': ab.included,
        'selected_by': ab.selected_by, 'decision_note': ab.decision_note, 'target_level': ab.target_level,
        'requests': len(snap.get('evidence_rules') or []),
        'evidence': getattr(ab, 'n_evidence', 0), 'accepted': getattr(ab, 'n_accepted', 0),
        'waiting': getattr(ab, 'n_waiting', 0),
        'assessment': AssessmentSerializer(a).data if (a and show_scores) else None,
    }


def _cycle_payload(request, cycle):
    abs_ = (cycle.benchmarks.select_related('benchmark', 'release_item', 'assessment')
            .annotate(n_evidence=Count('evidence'),
                      n_accepted=Count('evidence', filter=Q(evidence__status='accepted')),
                      n_waiting=Count('evidence', filter=Q(evidence__status='submitted'))))
    show = _scores_visible(request, cycle)
    return {**CycleSerializer(cycle).data, 'scores_visible': show,
            'benchmarks': [_row(ab, show) for ab in abs_]}


class ReferenceView(APIView):
    """GET /assessments/reference -- choices for the profile form + what is current."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rel = current_release()
        model = ScoringModel.objects.filter(active=True).first()
        return Response({
            'institution_types': list(InstitutionType.objects.values('code', 'name')),
            'programme_types': list(ProgrammeType.objects.values('code', 'name')),
            'autonomous_statuses': [{'code': c, 'name': n} for c, n in AUTONOMOUS_STATUSES],
            'approval_bodies': APPROVAL_BODIES,
            'current_release': rel.release_label if rel else None,
            'scoring_model': {'code': model.code, 'name': model.name, 'description': model.description} if model else None,
            'is_staff': _staff(request.user), 'can_upload': _can_upload(request.user),
        })


class InstitutionListView(APIView):
    """GET /assessments/institutions -- colleges this user can see, with profile status."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ids = get_accessible_institution_ids(request.user)
        qs = Institution.objects.filter(is_active=True).order_by('name')
        if ids is not None:
            qs = qs.filter(pk__in=ids)
        have = set(BenchmarkProfile.objects.values_list('institution_id', flat=True))
        return Response([{'id': str(i.pk), 'name': i.name, 'city': i.city, 'has_profile': i.pk in have} for i in qs])


class ProfileView(APIView):
    """GET/PUT /assessments/institutions/<id>/profile"""
    permission_classes = [IsAuthenticated]

    def _payload(self, inst):
        p = BenchmarkProfile.objects.filter(institution=inst).select_related('institution_type', 'updated_by').first()
        return {
            'institution': str(inst.pk), 'institution_name': inst.name,
            'profile': None if p is None else {
                'institution_type': p.institution_type.code, 'institution_type_name': p.institution_type.name,
                'autonomous_status': p.autonomous_status, 'approval_bodies': p.approval_bodies,
                'jurisdiction': p.jurisdiction, 'updated_by': p.updated_by.email if p.updated_by else None,
                'updated_at': p.updated_at},
            'programmes': ProgrammeSerializer(inst.benchmark_programmes.select_related('programme_type'), many=True).data,
        }

    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)
        require_institution_access(request.user, inst)
        return Response(self._payload(inst))

    def put(self, request, pk):
        if not _staff(request.user):
            return _forbid('Only InGage staff can change the profile (it decides which benchmarks apply).')
        inst = get_object_or_404(Institution, pk=pk)
        try:
            svc.save_profile(inst, request.user, request.data)
        except svc.AssessmentError as exc:
            return _err(exc)
        return Response(self._payload(inst))


class CycleListView(APIView):
    """GET /assessments/cycles?institution=   POST {institution, name, opens_on, closes_on} (staff)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AssessmentCycle.objects.select_related('institution', 'release', 'created_by', 'finalized_by')
        ids = get_accessible_institution_ids(request.user)
        if ids is not None:
            qs = qs.filter(institution_id__in=ids)
        if request.query_params.get('institution'):
            qs = qs.filter(institution_id=request.query_params['institution'])
        return Response(CycleSerializer(qs, many=True).data)

    def post(self, request):
        if not _staff(request.user):
            return _forbid()
        inst = get_object_or_404(Institution, pk=request.data.get('institution'))
        try:
            cycle = svc.create_cycle(inst, request.user, request.data.get('name'), request.data.get('opens_on'),
                                     request.data.get('closes_on'))
        except svc.AssessmentError as exc:
            return _err(exc)
        return Response(_cycle_payload(request, cycle), status=status.HTTP_201_CREATED)


class CycleDetailView(APIView):
    """GET /assessments/cycles/<id>"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(_cycle_payload(request, _cycle(request, pk)))


class CycleActionView(APIView):
    """POST /assessments/cycles/<id>/<open|submit|return|score|finalize> {note}"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, action):
        cycle = _cycle(request, pk)
        user = request.user
        if action == 'submit':
            if not _can_upload(user):
                return _forbid('Viewers cannot submit.')
        elif not _staff(user):
            return _forbid()
        fn = {'open': svc.open_cycle, 'submit': svc.submit_cycle, 'score': svc.score_cycle,
              'finalize': svc.finalize_cycle,
              'return': lambda c, u: svc.return_cycle(c, u, request.data.get('note', ''))}.get(action)
        if fn is None:
            return Response({'detail': 'Unknown action.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            fn(cycle, user)
        except svc.AssessmentError as exc:
            return _err(exc)
        cycle.refresh_from_db()
        return Response(_cycle_payload(request, cycle))


class CycleBenchmarkView(APIView):
    """GET   /assessments/cycles/<id>/benchmarks/<code>  -- levels, evidence requests, evidence, scores
       PATCH {included, target_level, note} (staff)"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, code):
        cycle, ab = _applicable(request, pk, code)
        snap = ab.snapshot
        show = _scores_visible(request, cycle)
        a = getattr(ab, 'assessment', None)
        return Response({
            **_row(ab, show), 'cycle_status': cycle.status, 'release_label': cycle.release.release_label,
            'snapshot_hash': ab.release_item.snapshot_hash,
            'levels': snap.get('levels') or {}, 'requirements': snap.get('requirements') or [],
            'requests': [{**{k: v for k, v in r.items() if k != 'items'},
                          'items': EvidenceItemSerializer(r['items'], many=True).data}
                         for r in svc.evidence_requests(ab)],
            'assessment': AssessmentSerializer(a).data if (a and show) else None,
            'preview': _preview(ab, a) if _staff(request.user) and cycle.status != Status.FINALIZED else None,
        })

    def patch(self, request, pk, code):
        if not _staff(request.user):
            return _forbid()
        cycle, ab = _applicable(request, pk, code)
        try:
            svc.decide_benchmark(ab, request.user, included=request.data.get('included'),
                                 target_level=request.data.get('target_level'), note=request.data.get('note', ''))
        except svc.AssessmentError as exc:
            return _err(exc)
        return self.get(request, pk, code)


def _preview(ab, a):
    """What the scores would be right now (staff only, nothing saved)."""
    r = svc.compute(ab, a)
    return {'current_level': r['current_level'], 'composite': r['composite'],
            'scores': {k: (str(v) if v is not None else None) for k, v in r['scores'].items()}, 'detail': r['detail']}


class EvidenceSubmitView(APIView):
    """POST /assessments/cycles/<id>/benchmarks/<code>/evidence  (multipart: rule_key, title, file | source_url, ...)"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk, code):
        if not _can_upload(request.user):
            return _forbid('Viewers cannot upload evidence.')
        cycle, ab = _applicable(request, pk, code)
        try:
            item = svc.submit_evidence(ab, request.user, request.data, request.FILES.get('file'))
        except svc.AssessmentError as exc:
            return _err(exc)
        return Response(EvidenceItemSerializer(item).data, status=status.HTTP_201_CREATED)


class EvidenceFileView(APIView):
    """GET /assessments/evidence/<id>/file"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        item = get_object_or_404(EvidenceItem.objects.select_related('cycle'), pk=pk)
        require_institution_access(request.user, item.cycle)
        f = item.file or (item.sprint_document.file if item.sprint_document_id else None)
        if not f:
            return Response({'detail': 'This evidence is a link, not a file.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(f.open('rb'), as_attachment=True, filename=item.original_filename or 'evidence')


class EvidenceReviewView(APIView):
    """POST /assessments/evidence/<id>/review {decision, *_score x5, notes} (staff)"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk):
        item = get_object_or_404(EvidenceItem.objects.select_related('cycle'), pk=pk)
        try:
            svc.review_evidence(item, request.user, request.data)
        except svc.AssessmentError as exc:
            return _err(exc)
        item.refresh_from_db()
        return Response(EvidenceItemSerializer(item).data)


class AssessorInputView(APIView):
    """POST /assessments/cycles/<id>/benchmarks/<code>/assessment
       {outcome_score, outcome_note, level_override, override_note, assessor_notes} (staff)"""
    permission_classes = [IsInGageStaff]

    def post(self, request, pk, code):
        cycle, ab = _applicable(request, pk, code)
        try:
            a = svc.update_assessment(ab, request.user, request.data)
        except svc.AssessmentError as exc:
            return _err(exc)
        a.refresh_from_db()
        return Response(AssessmentSerializer(a).data)


class ScorecardView(APIView):
    """GET /assessments/cycles/<id>/scorecard -- staff any time; the college once finalized."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        cycle = _cycle(request, pk)
        if not _scores_visible(request, cycle):
            return Response({'detail': 'The scorecard is shared once InGage finalizes the assessment.'},
                            status=status.HTTP_403_FORBIDDEN)
        rows = []
        for ab in cycle.benchmarks.filter(included=True).select_related('benchmark', 'release_item', 'assessment'):
            a = getattr(ab, 'assessment', None)
            rows.append({'benchmark_code': ab.benchmark.benchmark_code, 'title': ab.snapshot.get('title'),
                         'pillar': ab.snapshot.get('pillar'), 'kind': ab.snapshot.get('kind'),
                         'target_level': ab.target_level, 'snapshot_hash': ab.release_item.snapshot_hash,
                         'assessment': AssessmentSerializer(a).data if a else None})
        model = ScoringModel.objects.filter(active=True).first()
        return Response({**CycleSerializer(cycle).data, 'benchmarks': rows,
                         'scoring_model': {'code': model.code, 'name': model.name, 'formula_version': model.formula_version,
                                           'description': model.description} if model else None,
                         'method': svc.SCORING_METHOD})


class ScoreRuleView(APIView):
    """GET /assessments/score-rules   PUT /assessments/score-rules/<code> {compliance_weight, maturity_weight,
       evidence_weight, outcome_weight, note} (staff)"""
    permission_classes = [IsInGageStaff]

    def get(self, request, code=None):
        model = ScoringModel.objects.filter(active=True).first()
        rules = {r.benchmark_id: r for r in BenchmarkScoreRule.objects.filter(scoring_model=model).select_related('approved_by')}
        out = []
        for b in Benchmark.objects.order_by('benchmark_code'):
            r = rules.get(b.pk)
            out.append({'benchmark_code': b.benchmark_code, 'title': b.title, 'status': b.status,
                        'weights': None if r is None else {k: str(v) for k, v in r.weights().items()},
                        'approved_by': r.approved_by.email if r else None, 'approved_at': r.approved_at if r else None,
                        'note': r.note if r else ''})
        return Response({'scoring_model': model.code if model else None, 'rules': out})

    def put(self, request, code=None):
        bench = get_object_or_404(Benchmark, benchmark_code=code)
        try:
            svc.set_score_rule(bench, request.user, request.data)
        except svc.AssessmentError as exc:
            return _err(exc)
        return self.get(request)
