from rest_framework import serializers

from apps.gaps.serializers import GapItemSerializer

from .models import Baseline, BaselineDecisionHistory, Pillar, PillarCriterion, PillarScore, ScoringRun


class PillarScoreSerializer(serializers.ModelSerializer):
    pillar = serializers.CharField(source='pillar.key', read_only=True)
    label = serializers.CharField(source='pillar.name', read_only=True)
    weight = serializers.FloatField(source='pillar.weight', read_only=True)
    # `score`/`confidence` are plain aliases of raw_score/confidence_score --
    # kept so the existing (unmodified) frontend's LiveCRIPreview.tsx, which
    # reads p.score/p.confidence off each pillar, keeps working unchanged.
    score = serializers.FloatField(source='raw_score', read_only=True)
    confidence = serializers.FloatField(source='confidence_score', read_only=True)

    class Meta:
        model = PillarScore
        fields = [
            'pillar', 'label', 'weight', 'raw_score', 'weighted_score', 'confidence_score', 'score', 'confidence',
            'status', 'evidence_count', 'gap_count', 'calculation_version', 'calculated_at',
        ]


class PillarSummarySerializer(serializers.ModelSerializer):
    """Lightweight per-pillar shape for the strengths/weaknesses lists --
    just enough to label and rank them, not the full PillarScore payload."""
    pillar = serializers.CharField(source='pillar.key', read_only=True)
    label = serializers.CharField(source='pillar.name', read_only=True)

    class Meta:
        model = PillarScore
        fields = ['pillar', 'label', 'raw_score', 'status']


class SprintScoreSerializer(serializers.Serializer):
    """The composed GET/POST .../score/ response -- not a ModelSerializer,
    since it's assembled from a live PillarScore queryset plus read-only
    evidence/gap aggregates rather than one model instance. See
    apps.scoring.services.cri_engine.build_score_snapshot."""
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    overall_cri = serializers.FloatField(read_only=True)
    overall_confidence = serializers.FloatField(read_only=True)
    # Aliases of overall_cri/overall_confidence, for the same reason as
    # PillarScoreSerializer's score/confidence: the unmodified frontend
    # reads scorecard.cri_score / scorecard.cri_confidence.
    cri_score = serializers.FloatField(source='overall_cri', read_only=True)
    cri_confidence = serializers.FloatField(source='overall_confidence', read_only=True)
    calculation_version = serializers.CharField(read_only=True)
    calculated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    pillar_scores = PillarScoreSerializer(many=True, read_only=True)
    strengths = PillarSummarySerializer(many=True, read_only=True)
    weaknesses = PillarSummarySerializer(many=True, read_only=True)
    evidence_metrics = serializers.DictField(read_only=True)
    unresolved_blocking_gaps = GapItemSerializer(many=True, read_only=True)


class ScoringRunSerializer(serializers.ModelSerializer):
    triggered_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ScoringRun
        fields = [
            'id', 'calculation_version', 'overall_cri', 'overall_confidence',
            'evidence_count', 'gap_count', 'pillar_snapshot', 'triggered_by', 'created_at',
        ]


class BaselineDecisionHistorySerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = BaselineDecisionHistory
        fields = ['id', 'action', 'user', 'user_name', 'comments', 'created_at']
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else ''


class BaselineSerializer(serializers.ModelSerializer):
    """A sprint's current (or a specific) baseline decision-cycle, plus the
    headline numbers off the exact ScoringRun it's pinned to -- so a report
    or the approval screen never has to make a second call just to show the
    CRI/confidence a decision was actually made against."""
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    scoring_run_id = serializers.PrimaryKeyRelatedField(source='scoring_run', read_only=True)
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    overall_cri = serializers.FloatField(source='scoring_run.overall_cri', read_only=True)
    overall_confidence = serializers.FloatField(source='scoring_run.overall_confidence', read_only=True)
    calculation_version = serializers.CharField(source='scoring_run.calculation_version', read_only=True)
    history = BaselineDecisionHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Baseline
        fields = [
            'id', 'sprint_id', 'scoring_run_id', 'status', 'overall_cri', 'overall_confidence',
            'calculation_version', 'approved_by', 'approved_by_name', 'approved_at', 'comments',
            'created_at', 'updated_at', 'history',
        ]
        read_only_fields = fields

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name() if obj.approved_by else ''


class BaselineActionSerializer(serializers.Serializer):
    """Shared body for approve / approve-provisional / return -- `comments`
    is optional for approve/approve-provisional, required for return (that
    stricter rule is enforced in apps.scoring.services.baseline, where the
    'required for return but not the others' business rule actually lives,
    rather than needing three near-identical serializer subclasses here)."""
    comments = serializers.CharField(required=False, allow_blank=True, default='')


class PillarCriterionConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PillarCriterion
        fields = ['key', 'name', 'description', 'weight', 'fact_field_keys', 'is_active']


class PillarConfigSerializer(serializers.ModelSerializer):
    """The `/api/v1/scoring/config` payload -- the live, database-backed
    scoring configuration (as opposed to a hardcoded weights dict)."""
    criteria = PillarCriterionConfigSerializer(many=True, read_only=True)

    class Meta:
        model = Pillar
        fields = ['key', 'name', 'description', 'weight', 'display_order', 'is_active', 'criteria']
