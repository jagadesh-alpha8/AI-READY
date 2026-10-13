from django.contrib import admin

from .models import Authority, Framework, SourceAuditEvent, SourceDocument, SourceFeed, SourceVersion


@admin.register(Authority)
class AuthorityAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'kind']
    list_filter = ['kind']
    search_fields = ['code', 'name']


@admin.register(Framework)
class FrameworkAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'authority']
    list_filter = ['authority']
    search_fields = ['code', 'name']


class SourceVersionInline(admin.TabularInline):
    model = SourceVersion
    extra = 0
    fields = ['version_label', 'status', 'collection_status', 'issued_on', 'checksum_sha256']
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = ['source_code', 'title', 'framework', 'source_role', 'category', 'licensed_content']
    list_filter = ['source_role', 'category', 'licensed_content', 'framework__authority']
    search_fields = ['source_code', 'title']
    inlines = [SourceVersionInline]


@admin.register(SourceVersion)
class SourceVersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'version_label', 'status', 'collection_status', 'issued_on', 'register_row_id']
    list_filter = ['status', 'collection_status', 'document__category']
    search_fields = ['document__source_code', 'document__title', 'version_label']

    def get_readonly_fields(self, request, obj=None):
        # An approved (non-draft) version's content is frozen; only its status can move on.
        if obj and obj.is_locked:
            return [f.name for f in obj._meta.fields if f.name not in ('status', 'effective_to')]
        return ['review_flags', 'register_row_id']

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.is_locked


@admin.register(SourceFeed)
class SourceFeedAdmin(admin.ModelAdmin):
    list_display = ['document', 'feed_type', 'endpoint_url', 'enabled']
    list_filter = ['feed_type', 'enabled']


@admin.register(SourceAuditEvent)
class SourceAuditEventAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'actor', 'action', 'object_type', 'object_id']
    list_filter = ['action', 'object_type']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import Benchmark, Capability, EvidenceType, MaturityDefinition, Pillar  # noqa: E402


@admin.register(Pillar)
class PillarAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'catalogue_status']


@admin.register(EvidenceType)
class EvidenceTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'validation_method']


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'domain']
    search_fields = ['code', 'name']


class MaturityInline(admin.TabularInline):
    model = MaturityDefinition
    extra = 0
    fields = ['level', 'definition', 'measurement_rule', 'is_placeholder']


@admin.register(Benchmark)
class BenchmarkAdmin(admin.ModelAdmin):
    list_display = ['benchmark_code', 'title', 'pillar', 'benchmark_kind', 'status', 'expert_owner']
    list_filter = ['pillar', 'benchmark_kind', 'status']
    search_fields = ['benchmark_code', 'title', 'source_basis']
    filter_horizontal = ['evidence_types']
    inlines = [MaturityInline]


from .models import EvidenceRule  # noqa: E402


@admin.register(EvidenceRule)
class EvidenceRuleAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'mandatory', 'minimum_count', 'minimum_currency_months', 'validation_method']
    list_filter = ['evidence_type', 'mandatory', 'validation_method', 'privacy_classification']


from .models import ApplicabilityRule, InstitutionType, ProgrammeType  # noqa: E402

admin.site.register(InstitutionType)
admin.site.register(ProgrammeType)


@admin.register(ApplicabilityRule)
class ApplicabilityRuleAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'result', 'priority', 'jurisdiction']
    list_filter = ['result']
    filter_horizontal = ['institution_types', 'programme_types']


from .models import BenchmarkRelease, BenchmarkReleaseItem  # noqa: E402


class ReleaseItemInline(admin.TabularInline):
    model = BenchmarkReleaseItem
    extra = 0
    fields = ['benchmark', 'change_type', 'impact_summary', 'snapshot_hash']
    readonly_fields = fields
    can_delete = False


@admin.register(BenchmarkRelease)
class BenchmarkReleaseAdmin(admin.ModelAdmin):
    """Read-only: releases move only through the audited workflow (Studio / API)."""
    list_display = ['release_label', 'status', 'published_at', 'content_hash']
    inlines = [ReleaseItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
