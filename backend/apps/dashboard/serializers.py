from rest_framework import serializers

from apps.sprints.models import Sprint


class DashboardSprintSerializer(serializers.ModelSerializer):
    """One row of the dashboard's sprint list. Every field here is read off
    an already-annotated/prefetched queryset (see
    apps.dashboard.views.DashboardView) -- nothing triggers its own query,
    so serializing a page of these never adds N+1 queries."""
    institution = serializers.CharField(source='institution.name', read_only=True)
    completion = serializers.IntegerField(source='completion_percentage', read_only=True)
    cri = serializers.FloatField(source='overall_cri', read_only=True)
    confidence = serializers.FloatField(source='confidence_score', read_only=True)
    #: From the `pending_gaps_count` annotation (Count over active gaps).
    pending_gaps = serializers.IntegerField(source='pending_gaps_count', read_only=True)
    #: From the `ordered_reports` prefetch (Report rows for this sprint,
    #: newest version first) -- null if the sprint has never had a report
    #: generated, never a fabricated "ready"/"pending" placeholder.
    report_status = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = [
            'id', 'institution', 'name', 'status', 'completion', 'cri', 'confidence',
            'pending_gaps', 'report_status', 'updated_at',
        ]

    def get_report_status(self, obj):
        reports = getattr(obj, 'ordered_reports', None)
        return reports[0].status if reports else None
