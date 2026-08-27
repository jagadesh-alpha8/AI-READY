from rest_framework import serializers

from .models import Institution


class InstitutionSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    sprint_count = serializers.SerializerMethodField()
    # Frontend-compatible aliases: the existing (unmodified) frontend's
    # SprintSetup.tsx posts `affiliation`/`accreditation_status` when
    # creating an institution, not `university_affiliation`/
    # `accreditation_details`. Writable (source=) so a create/update from
    # that form actually lands on the real column instead of being silently
    # dropped as an unrecognized key.
    affiliation = serializers.CharField(
        source='university_affiliation', required=False, allow_blank=True,
    )
    accreditation_status = serializers.CharField(
        source='accreditation_details', required=False, allow_blank=True,
    )

    def get_sprint_count(self, obj):
        return obj.sprints.count()

    class Meta:
        model = Institution
        fields = [
            'id', 'name', 'short_name', 'institution_type', 'university_affiliation', 'affiliation',
            'website_url', 'location', 'city', 'state', 'country', 'accreditation_details',
            'accreditation_status', 'contact_email', 'contact_phone', 'is_active', 'sprint_count',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'sprint_count', 'created_at', 'updated_at']
