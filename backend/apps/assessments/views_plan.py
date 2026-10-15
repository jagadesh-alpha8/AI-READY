"""Stage 6 API: improvement plan (gaps, initiatives, tasks), transformation
templates, and audit documents a college can reuse as benchmark evidence.

Who may do what:
  generate the plan, validate / close gaps, edit templates  -> InGage staff
  update initiatives and tasks (owner, status, dates)       -> staff, and the
                                                               college's members except viewers
  read the plan                                             -> staff, and the college (only finalized cycles have one)
"""
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsInGageStaff, require_institution_access
from apps.benchmarks.models import Benchmark

from . import plan
from .models import AssessmentCycle, AssessmentGap, EvidenceItem, Initiative, Task, TransformationTemplate


def _staff(user):
    return user.role in User.CROSS_INSTITUTION_ROLES


def _err(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TaskSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Task
        fields = ['id', 'title', 'owner', 'due_date', 'status', 'status_label', 'evidence_due', 'order']
        read_only_fields = fields


class InitiativeSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    from_template = serializers.BooleanField(source='template_id', read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta:
        model = Initiative
        fields = ['id', 'title', 'description', 'expected_evidence', 'expected_outcome', 'owner', 'status',
                  'status_label', 'target_date', 'from_template', 'tasks']
        read_only_fields = fields


class GapSerializer(serializers.ModelSerializer):
    benchmark_code = serializers.CharField(source='assessment.applicable.benchmark.benchmark_code', read_only=True)
    benchmark_title = serializers.SerializerMethodField()
    type_label = serializers.CharField(source='get_gap_type_display', read_only=True)
    severity_label = serializers.CharField(source='get_severity_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    closing_evidence_title = serializers.CharField(source='closing_evidence.title', default=None, read_only=True)
    validated_by = serializers.CharField(source='validated_by.email', default=None, read_only=True)
    initiatives = InitiativeSerializer(many=True, read_only=True)

    class Meta:
        model = AssessmentGap
        fields = ['id', 'benchmark_code', 'benchmark_title', 'gap_type', 'type_label', 'severity', 'severity_label',
                  'description', 'root_cause', 'status', 'status_label', 'closing_evidence', 'closing_evidence_title',
                  'validated_by', 'validated_at', 'validation_note', 'initiatives']
        read_only_fields = fields

    def get_benchmark_title(self, obj):
        return obj.assessment.applicable.snapshot.get('title')


class TemplateSerializer(serializers.ModelSerializer):
    benchmark_code = serializers.CharField(source='benchmark.benchmark_code', read_only=True)

    class Meta:
        model = TransformationTemplate
        fields = ['id', 'benchmark_code', 'gap_type', 'title', 'intervention', 'expected_evidence',
                  'expected_outcome', 'tasks', 'updated_at']
        read_only_fields = ['id', 'benchmark_code', 'updated_at']


def _cycle(request, pk):
    cycle = get_object_or_404(AssessmentCycle.objects.select_related('institution'), pk=pk)
    require_institution_access(request.user, cycle)
    return cycle


def _plan_payload(cycle):
    gaps = (AssessmentGap.objects.filter(assessment__applicable__cycle=cycle)
            .select_related('assessment__applicable__benchmark', 'assessment__applicable__release_item',
                            'closing_evidence', 'validated_by')
            .prefetch_related('initiatives__tasks'))
    data = GapSerializer(gaps, many=True).data
    open_ = [g for g in data if g['status'] not in ('validated', 'closed')]
    return {'cycle': str(cycle.pk), 'has_plan': bool(data), 'gaps': data,
            'summary': {'gaps': len(data), 'open': len(open_),
                        'critical_open': sum(g['severity'] == 'critical' for g in open_),
                        'tasks': sum(len(i['tasks']) for g in data for i in g['initiatives']),
                        'tasks_done': sum(t['status'] == 'complete' for g in data for i in g['initiatives']
                                          for t in i['tasks'])}}


class CyclePlanView(APIView):
    """GET /assessments/cycles/<id>/plan     POST -- generate (staff, finalized cycles)"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(_plan_payload(_cycle(request, pk)))

    def post(self, request, pk):
        if not _staff(request.user):
            return Response({'detail': 'Only InGage staff can generate the plan.'}, status=status.HTTP_403_FORBIDDEN)
        cycle = _cycle(request, pk)
        try:
            plan.generate_plan(cycle, request.user)
        except plan.PlanError as exc:
            return _err(exc)
        return Response(_plan_payload(cycle), status=status.HTTP_201_CREATED)


class GapView(APIView):
    """PATCH /assessments/gaps/<id> {status, root_cause} (staff)
       POST  /assessments/gaps/<id>/validate {evidence_item, note} (staff)"""
    permission_classes = [IsInGageStaff]

    def _gap(self, pk):
        return get_object_or_404(AssessmentGap.objects.select_related('assessment__applicable__cycle'), pk=pk)

    def patch(self, request, pk):
        gap = self._gap(pk)
        try:
            plan.set_gap_status(gap, request.user, request.data.get('status', gap.status),
                                request.data.get('root_cause'))
        except plan.PlanError as exc:
            return _err(exc)
        return Response(GapSerializer(self._gap(pk)).data)

    def post(self, request, pk):
        gap = self._gap(pk)
        item = get_object_or_404(EvidenceItem.objects.select_related('cycle', 'applicable'),
                                 pk=request.data.get('evidence_item'))
        try:
            plan.validate_gap(gap, request.user, item, request.data.get('note', ''))
        except plan.PlanError as exc:
            return _err(exc)
        return Response(GapSerializer(self._gap(pk)).data)


def _can_edit_plan(user):
    return user.role != User.Role.VIEWER


class InitiativeView(APIView):
    """PATCH /assessments/initiatives/<id> {title, description, owner, status, target_date}
       POST  /assessments/initiatives/<id>/tasks {title, owner, due_date, evidence_due}"""
    permission_classes = [IsAuthenticated]

    def _ini(self, request, pk):
        ini = get_object_or_404(Initiative.objects.select_related('cycle'), pk=pk)
        require_institution_access(request.user, ini.cycle)
        return ini

    def patch(self, request, pk):
        if not _can_edit_plan(request.user):
            return Response({'detail': 'Viewers cannot change the plan.'}, status=status.HTTP_403_FORBIDDEN)
        ini = self._ini(request, pk)
        try:
            plan.update_initiative(ini, request.user, request.data)
        except plan.PlanError as exc:
            return _err(exc)
        return Response(InitiativeSerializer(self._ini(request, pk)).data)

    def post(self, request, pk):
        if not _can_edit_plan(request.user):
            return Response({'detail': 'Viewers cannot change the plan.'}, status=status.HTTP_403_FORBIDDEN)
        ini = self._ini(request, pk)
        try:
            plan.add_task(ini, request.user, request.data)
        except plan.PlanError as exc:
            return _err(exc)
        return Response(InitiativeSerializer(self._ini(request, pk)).data, status=status.HTTP_201_CREATED)


class TaskView(APIView):
    """PATCH /assessments/tasks/<id> {title, owner, status, due_date, evidence_due}"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _can_edit_plan(request.user):
            return Response({'detail': 'Viewers cannot change the plan.'}, status=status.HTTP_403_FORBIDDEN)
        task = get_object_or_404(Task.objects.select_related('initiative__cycle'), pk=pk)
        require_institution_access(request.user, task.initiative.cycle)
        try:
            plan.update_task(task, request.user, request.data)
        except plan.PlanError as exc:
            return _err(exc)
        return Response(TaskSerializer(task).data)


class TemplateListView(APIView):
    """GET /assessments/templates?benchmark=<code>   POST {benchmark_code, gap_type, title, intervention,
       expected_evidence, expected_outcome, tasks[]} (staff)"""
    permission_classes = [IsInGageStaff]

    def get(self, request):
        qs = TransformationTemplate.objects.select_related('benchmark')
        if request.query_params.get('benchmark'):
            qs = qs.filter(benchmark__benchmark_code=request.query_params['benchmark'])
        return Response(TemplateSerializer(qs, many=True).data)

    def post(self, request):
        bench = get_object_or_404(Benchmark, benchmark_code=request.data.get('benchmark_code', ''))
        ser = TemplateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if TransformationTemplate.objects.filter(benchmark=bench, gap_type=ser.validated_data['gap_type']).exists():
            return _err('This benchmark already has a template for that gap type; edit it instead.')
        tasks = [str(t).strip()[:300] for t in (ser.validated_data.get('tasks') or []) if str(t).strip()]
        t = ser.save(benchmark=bench, created_by=request.user, tasks=tasks)
        return Response(TemplateSerializer(t).data, status=status.HTTP_201_CREATED)


class TemplateDetailView(APIView):
    """PATCH / DELETE /assessments/templates/<id> (staff). Used for plans generated afterwards."""
    permission_classes = [IsInGageStaff]

    def patch(self, request, pk):
        t = get_object_or_404(TransformationTemplate, pk=pk)
        ser = TemplateSerializer(t, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        get_object_or_404(TransformationTemplate, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SprintDocumentsView(APIView):
    """GET /assessments/cycles/<id>/sprint-documents -- this college's audit documents
    that can be reused as benchmark evidence (processed or uploaded, with a file)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.documents.models import Document

        cycle = _cycle(request, pk)
        docs = (Document.objects.filter(sprint__institution_id=cycle.institution_id).exclude(file='')
                .select_related('sprint').order_by('-created_at')[:300])
        return Response([{'id': str(d.pk), 'title': d.title or d.original_filename,
                          'filename': d.original_filename, 'document_type': d.document_type,
                          'sprint': d.sprint.name or d.sprint.sprint_code, 'uploaded_at': d.uploaded_at or d.created_at}
                         for d in docs])
