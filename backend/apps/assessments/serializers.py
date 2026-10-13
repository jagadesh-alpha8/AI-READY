from rest_framework import serializers

from .models import AssessmentCycle, BenchmarkAssessment, EvidenceItem, EvidenceReview, Programme


class ProgrammeSerializer(serializers.ModelSerializer):
    programme_type = serializers.CharField(source='programme_type.code')
    programme_type_name = serializers.CharField(source='programme_type.name')

    class Meta:
        model = Programme
        fields = ['id', 'name', 'programme_type', 'programme_type_name', 'approval_body', 'active']


class CycleSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source='institution.name', read_only=True)
    release_label = serializers.CharField(source='release.release_label', read_only=True)
    release_hash = serializers.CharField(source='release.content_hash', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    created_by = serializers.CharField(source='created_by.email', read_only=True)
    finalized_by = serializers.CharField(source='finalized_by.email', default=None, read_only=True)

    class Meta:
        model = AssessmentCycle
        fields = ['id', 'institution', 'institution_name', 'name', 'opens_on', 'closes_on', 'status', 'status_label',
                  'release_label', 'release_hash', 'profile_snapshot', 'created_by', 'created_at', 'finalized_by',
                  'finalized_at']
        read_only_fields = fields


class EvidenceReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(source='reviewer.email', read_only=True)
    decision_label = serializers.CharField(source='get_decision_display', read_only=True)

    class Meta:
        model = EvidenceReview
        fields = ['id', 'reviewer', 'decision', 'decision_label', 'relevance_score', 'completeness_score',
                  'currency_score', 'authenticity_score', 'scope_score', 'notes', 'reviewed_at']
        read_only_fields = fields


class EvidenceItemSerializer(serializers.ModelSerializer):
    evidence_type = serializers.CharField(source='evidence_type.code', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    submitted_by = serializers.CharField(source='submitted_by.email', read_only=True)
    has_file = serializers.SerializerMethodField()
    reviews = EvidenceReviewSerializer(many=True, read_only=True)

    class Meta:
        model = EvidenceItem
        fields = ['id', 'rule_key', 'evidence_type', 'title', 'description', 'has_file', 'original_filename',
                  'file_sha256', 'source_url', 'issued_on', 'valid_until', 'status', 'status_label', 'submitted_by',
                  'created_at', 'reviews']
        read_only_fields = fields

    def get_has_file(self, obj):
        return bool(obj.file)


class AssessmentSerializer(serializers.ModelSerializer):
    scoring_model = serializers.CharField(source='scoring_model.code', default=None, read_only=True)
    scored_by = serializers.CharField(source='scored_by.email', default=None, read_only=True)

    class Meta:
        model = BenchmarkAssessment
        fields = ['computed_level', 'level_override', 'override_note', 'current_level', 'compliance_score',
                  'maturity_score', 'evidence_confidence_score', 'outcome_score', 'outcome_note', 'composite_score',
                  'scoring_model', 'weights', 'detail', 'assessor_notes', 'scored_at', 'scored_by']
        read_only_fields = fields
