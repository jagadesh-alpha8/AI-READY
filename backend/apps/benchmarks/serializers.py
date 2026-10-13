from rest_framework import serializers

from .models import Requirement, RequirementCandidate, SourceDocument, SourceFeed, SourceVersion


class SourceVersionSerializer(serializers.ModelSerializer):
    collection_status_label = serializers.CharField(source='get_collection_status_display', read_only=True)
    supersedes = serializers.CharField(source='supersedes.version_label', default=None, read_only=True)
    approved_by = serializers.CharField(source='approved_by.email', default=None, read_only=True)
    pending_candidates = serializers.SerializerMethodField()
    requirement_count = serializers.SerializerMethodField()

    # Annotated by the views' queryset (one query); counted directly otherwise.
    def get_pending_candidates(self, obj):
        if hasattr(obj, 'pending_count'):
            return obj.pending_count
        return obj.requirement_candidates.filter(status=RequirementCandidate.Status.PENDING).count()

    def get_requirement_count(self, obj):
        return obj.req_count if hasattr(obj, 'req_count') else obj.requirements.count()

    class Meta:
        model = SourceVersion
        fields = ['id', 'version_label', 'status', 'issued_on', 'effective_from', 'effective_to', 'collection_status',
                  'collection_status_label', 'reported_status', 'direct_url', 'drive_url', 'file_size_kb', 'pages',
                  'checksum_sha256', 'file_uri', 'supersedes', 'collected_on', 'notes', 'register_row_id',
                  'review_flags', 'intake_status', 'intake_note', 'intake_at', 'extraction_status',
                  'extraction_note', 'approved_by', 'approved_at', 'pending_candidates', 'requirement_count',
                  'created_at', 'updated_at']
        read_only_fields = fields


class SourceFeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceFeed
        fields = ['id', 'feed_type', 'endpoint_url', 'polling_schedule', 'enabled', 'last_success_at']
        read_only_fields = fields


class SourceDocumentListSerializer(serializers.ModelSerializer):
    authority = serializers.CharField(source='framework.authority.code', read_only=True)
    authority_name = serializers.CharField(source='framework.authority.name', read_only=True)
    authority_kind = serializers.CharField(source='framework.authority.kind', read_only=True)
    source_role_label = serializers.CharField(source='get_source_role_display', read_only=True)
    latest_version = serializers.SerializerMethodField()
    version_count = serializers.IntegerField(read_only=True)
    review_flag_count = serializers.SerializerMethodField()

    class Meta:
        model = SourceDocument
        fields = ['id', 'source_code', 'title', 'authority', 'authority_name', 'authority_kind', 'category',
                  'source_role', 'source_role_label', 'document_type', 'applies_to', 'official_url',
                  'licensed_content', 'review_cadence_months', 'version_count', 'latest_version', 'review_flag_count']
        read_only_fields = fields

    @staticmethod
    def _latest(obj):
        versions = list(obj.versions.all())  # prefetched, newest first by Meta ordering
        return versions[0] if versions else None

    def get_latest_version(self, obj):
        v = self._latest(obj)
        return SourceVersionSerializer(v).data if v else None

    def get_review_flag_count(self, obj):
        return sum(len(v.review_flags or []) for v in obj.versions.all())


class SourceDocumentDetailSerializer(SourceDocumentListSerializer):
    versions = SourceVersionSerializer(many=True, read_only=True)
    feeds = SourceFeedSerializer(many=True, read_only=True)

    class Meta(SourceDocumentListSerializer.Meta):
        fields = SourceDocumentListSerializer.Meta.fields + ['programme_scope', 'owner_team', 'versions', 'feeds']
        read_only_fields = fields


class RequirementCandidateSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.CharField(source='reviewed_by.email', default=None, read_only=True)
    requirement_code = serializers.CharField(source='requirement.code', default=None, read_only=True)

    class Meta:
        model = RequirementCandidate
        fields = ['id', 'statement', 'kind', 'page', 'source_quote', 'confidence', 'rationale', 'model', 'status',
                  'reviewed_by', 'reviewed_at', 'review_note', 'requirement_code', 'created_at']
        read_only_fields = fields


class RequirementSerializer(serializers.ModelSerializer):
    source_code = serializers.CharField(source='version.document.source_code', read_only=True)
    version_label = serializers.CharField(source='version.version_label', read_only=True)
    approved_by = serializers.CharField(source='approved_by.email', read_only=True)
    benchmarks = serializers.SerializerMethodField()

    class Meta:
        model = Requirement
        fields = ['id', 'code', 'source_code', 'version_label', 'statement', 'kind', 'page', 'source_quote',
                  'approved_by', 'approved_at', 'benchmarks']
        read_only_fields = fields

    def get_benchmarks(self, obj):
        return [{'benchmark_code': link.benchmark.benchmark_code, 'relationship': link.relationship}
                for link in obj.benchmark_links.all()]


# -- stage 3: catalogue ----------------------------------------------------------

from .models import Benchmark, EvidenceType, MaturityDefinition, Pillar  # noqa: E402


class EvidenceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceType
        fields = ['code', 'name', 'validation_method', 'examples', 'assessment_use']
        read_only_fields = fields


class MaturityDefinitionSerializer(serializers.ModelSerializer):
    level_label = serializers.CharField(source='get_level_display', read_only=True)
    edited_by = serializers.CharField(source='edited_by.email', default=None, read_only=True)

    class Meta:
        model = MaturityDefinition
        fields = ['level', 'level_label', 'definition', 'measurement_rule', 'is_placeholder',
                  'observable_requirements', 'minimum_evidence', 'outcome_expectations', 'non_examples',
                  'requires_manual_review', 'edited_by', 'edited_at']
        read_only_fields = fields


class PillarSerializer(serializers.ModelSerializer):
    benchmark_count = serializers.IntegerField(read_only=True)
    mandatory_count = serializers.IntegerField(read_only=True)
    guidance_count = serializers.IntegerField(read_only=True)
    proposed_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Pillar
        fields = ['code', 'name', 'coverage', 'catalogue_status', 'benchmark_count', 'mandatory_count',
                  'guidance_count', 'proposed_count']
        read_only_fields = fields


class BenchmarkSerializer(serializers.ModelSerializer):
    pillar_code = serializers.CharField(source='pillar.code', read_only=True)
    pillar_name = serializers.CharField(source='pillar.name', read_only=True)
    capability = serializers.CharField(source='capability.definition', read_only=True)
    kind_label = serializers.CharField(source='get_benchmark_kind_display', read_only=True)
    evidence_types = serializers.SlugRelatedField(many=True, read_only=True, slug_field='code')
    maturity_levels = MaturityDefinitionSerializer(many=True, read_only=True)
    requirement_count = serializers.IntegerField(read_only=True)
    levels_defined = serializers.SerializerMethodField()

    class Meta:
        model = Benchmark
        fields = ['id', 'benchmark_code', 'title', 'pillar_code', 'pillar_name', 'capability', 'benchmark_kind',
                  'kind_label', 'benchmark_class', 'version_label', 'status', 'applicability', 'source_basis',
                  'scoring_dimensions', 'activation_status', 'expert_owner', 'target_guidance', 'evidence_types',
                  'maturity_levels', 'requirement_count', 'levels_defined']
        read_only_fields = fields

    def get_levels_defined(self, obj):
        """True only when all three levels are real, benchmark-specific text."""
        levels = list(obj.maturity_levels.all())
        return len(levels) == 3 and not any(lv.is_placeholder for lv in levels)


# -- stage 3.2: links -------------------------------------------------------------

from .models import BenchmarkRequirement  # noqa: E402


class BenchmarkLinkSerializer(serializers.ModelSerializer):
    benchmark_code = serializers.CharField(source='benchmark.benchmark_code', read_only=True)
    requirement_code = serializers.CharField(source='requirement.code', read_only=True)
    statement = serializers.CharField(source='requirement.statement', read_only=True)
    kind = serializers.CharField(source='requirement.kind', read_only=True)
    page = serializers.IntegerField(source='requirement.page', read_only=True)
    source_quote = serializers.CharField(source='requirement.source_quote', read_only=True)
    source_code = serializers.CharField(source='requirement.version.document.source_code', read_only=True)
    linked_by = serializers.CharField(source='linked_by.email', default=None, read_only=True)

    class Meta:
        model = BenchmarkRequirement
        fields = ['benchmark_code', 'requirement_code', 'statement', 'kind', 'page', 'source_quote', 'source_code',
                  'relationship', 'note', 'linked_by', 'linked_at']
        read_only_fields = fields


# -- stage 3.4: evidence rules ------------------------------------------------------------

from .models import EvidenceRule  # noqa: E402


class EvidenceRuleSerializer(serializers.ModelSerializer):
    evidence_type = serializers.CharField(source='evidence_type.code', read_only=True)
    evidence_type_name = serializers.CharField(source='evidence_type.name', read_only=True)
    benchmark_code = serializers.CharField(source='benchmark.benchmark_code', default=None, read_only=True)
    requirement_code = serializers.CharField(source='requirement.code', default=None, read_only=True)
    validation_method_label = serializers.CharField(source='get_validation_method_display', read_only=True)
    created_by = serializers.CharField(source='created_by.email', default=None, read_only=True)

    class Meta:
        model = EvidenceRule
        fields = ['id', 'benchmark_code', 'requirement_code', 'level', 'evidence_type', 'evidence_type_name', 'title',
                  'description', 'mandatory', 'minimum_count', 'minimum_currency_months', 'scope_rule',
                  'validation_method', 'validation_method_label', 'privacy_classification', 'created_by',
                  'created_at', 'updated_at']
        read_only_fields = fields


# -- stage 3.5: applicability -------------------------------------------------------------

from .models import ApplicabilityRule, InstitutionType, ProgrammeType  # noqa: E402


class InstitutionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstitutionType
        fields = ['code', 'name']
        read_only_fields = fields


class ProgrammeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgrammeType
        fields = ['code', 'name', 'sector']
        read_only_fields = fields


class ApplicabilityRuleSerializer(serializers.ModelSerializer):
    benchmark_code = serializers.CharField(source='benchmark.benchmark_code', default=None, read_only=True)
    requirement_code = serializers.CharField(source='requirement.code', default=None, read_only=True)
    result_label = serializers.CharField(source='get_result_display', read_only=True)
    institution_types = serializers.SlugRelatedField(many=True, read_only=True, slug_field='code')
    programme_types = serializers.SlugRelatedField(many=True, read_only=True, slug_field='code')
    created_by = serializers.CharField(source='created_by.email', default=None, read_only=True)

    class Meta:
        model = ApplicabilityRule
        fields = ['id', 'benchmark_code', 'requirement_code', 'result', 'result_label', 'priority', 'institution_types',
                  'autonomous_statuses', 'programme_types', 'approval_bodies', 'jurisdiction', 'reason', 'created_by',
                  'created_at', 'updated_at']
        read_only_fields = fields


# -- stage 3.6: releases ----------------------------------------------------------------

from .models import BenchmarkRelease, BenchmarkReleaseItem  # noqa: E402


class ReleaseItemSerializer(serializers.ModelSerializer):
    benchmark_code = serializers.CharField(source='benchmark.benchmark_code', read_only=True)
    title = serializers.CharField(source='benchmark.title', read_only=True)
    pillar_code = serializers.CharField(source='benchmark.pillar.code', read_only=True)
    benchmark_status = serializers.CharField(source='benchmark.status', read_only=True)
    change_type_label = serializers.CharField(source='get_change_type_display', read_only=True)

    class Meta:
        model = BenchmarkReleaseItem
        fields = ['benchmark_code', 'title', 'pillar_code', 'benchmark_status', 'change_type', 'change_type_label',
                  'impact_summary', 'snapshot_hash']
        read_only_fields = fields


class ReleaseSerializer(serializers.ModelSerializer):
    based_on = serializers.CharField(source='based_on.release_label', default=None, read_only=True)
    created_by = serializers.CharField(source='created_by.email', default=None, read_only=True)
    submitted_by = serializers.CharField(source='submitted_by.email', default=None, read_only=True)
    approved_by = serializers.CharField(source='approved_by.email', default=None, read_only=True)
    published_by = serializers.CharField(source='published_by.email', default=None, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = BenchmarkRelease
        fields = ['id', 'release_label', 'status', 'release_notes', 'based_on', 'created_by', 'created_at',
                  'submitted_by', 'submitted_at', 'approved_by', 'approved_at', 'published_by', 'published_at',
                  'retired_at', 'content_hash', 'item_count']
        read_only_fields = fields

    def get_item_count(self, obj):
        return obj.items.count()


# -- Stage 4: daily watcher ---------------------------------------------------------------
from .models import SourceChangeEvent, SourceFeed, WatcherRun  # noqa: E402


class SourceFeedSerializer(serializers.ModelSerializer):
    source_code = serializers.CharField(source='document.source_code', read_only=True)
    source_title = serializers.CharField(source='document.title', read_only=True)
    authority = serializers.CharField(source='document.framework.authority.code', read_only=True)
    feed_type_label = serializers.CharField(source='get_feed_type_display', read_only=True)
    snapshot_count = serializers.IntegerField(read_only=True)
    open_events = serializers.IntegerField(read_only=True)

    class Meta:
        model = SourceFeed
        fields = ['id', 'source_code', 'source_title', 'authority', 'feed_type', 'feed_type_label', 'endpoint_url',
                  'enabled', 'last_checked_at', 'last_success_at', 'last_result', 'last_error', 'snapshot_count',
                  'open_events']
        read_only_fields = fields


class SourceChangeEventSerializer(serializers.ModelSerializer):
    source_code = serializers.CharField(source='document.source_code', read_only=True)
    source_title = serializers.CharField(source='document.title', read_only=True)
    endpoint_url = serializers.CharField(source='feed.endpoint_url', default='', read_only=True)
    change_kind_label = serializers.CharField(source='get_change_kind_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    reviewed_by = serializers.CharField(source='reviewed_by.email', default=None, read_only=True)

    class Meta:
        model = SourceChangeEvent
        fields = ['id', 'source_code', 'source_title', 'endpoint_url', 'change_kind', 'change_kind_label',
                  'materiality_score', 'summary', 'details', 'impact', 'detected_at', 'status', 'status_label',
                  'reviewed_by', 'reviewed_at', 'review_note']
        read_only_fields = fields


class WatcherRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatcherRun
        fields = ['id', 'started_at', 'completed_at', 'status', 'trigger', 'feeds_checked', 'changes_detected',
                  'candidates_created', 'failure_detail']
        read_only_fields = fields
