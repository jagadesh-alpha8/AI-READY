from django.db.models import Sum
from rest_framework import serializers

from .constants import DIGITAL_MATURITY_DESCRIPTIONS
from .models import Department, Institution, InstitutionLeader, InstitutionSystem


class InstitutionLeaderSerializer(serializers.ModelSerializer):
    initials = serializers.SerializerMethodField()

    class Meta:
        model = InstitutionLeader
        fields = ['id', 'name', 'role', 'email', 'initials', 'display_order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'initials', 'created_at', 'updated_at']

    def get_initials(self, obj):
        """Derived, never stored — an avatar label is a function of the name,
        and a stored copy would go stale the moment the name is corrected."""
        parts = [word for word in obj.name.replace('.', ' ').split() if word]
        return ''.join(word[0].upper() for word in parts[:3])


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'head_name', 'faculty_count', 'student_count', 'program_count',
            'display_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        """Rejects a duplicate name here rather than letting the database's
        unique constraint surface as a 500 — and case-insensitively, since
        "Computer Science" and "computer science" are the same department to
        everyone except the constraint."""
        name = value.strip()
        institution = self.context.get('institution')
        if institution is None:
            return name
        clash = institution.departments.filter(name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError('This institution already has a department with that name.')
        return name


class InstitutionSystemSerializer(serializers.ModelSerializer):
    tag_label = serializers.CharField(source='get_tag_display', read_only=True)

    class Meta:
        model = InstitutionSystem
        fields = [
            'id', 'name', 'tag', 'tag_label', 'notes', 'display_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tag_label', 'created_at', 'updated_at']


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

    def validate_priorities(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Priorities must be a list of labels.')
        cleaned = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError('Each priority must be a text label.')
            label = item.strip()
            if label and label not in cleaned:
                cleaned.append(label)
        return cleaned

    class Meta:
        model = Institution
        fields = [
            'id', 'name', 'short_name', 'institution_type', 'university_affiliation', 'affiliation',
            'website_url', 'location', 'city', 'state', 'country', 'accreditation_details',
            'accreditation_status', 'contact_email', 'contact_phone', 'is_active', 'sprint_count',
            'student_count', 'faculty_count', 'priorities',
            'digital_maturity_level', 'current_ai_usage',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'sprint_count', 'created_at', 'updated_at']


class InstitutionDetailSerializer(InstitutionSerializer):
    """What the Institution DNA screen reads.

    Kept separate from the list serializer because everything it adds costs an
    extra query or a prefetch per institution — fine for one record, wasteful
    across a list that only needs names.
    """
    leaders = InstitutionLeaderSerializer(many=True, read_only=True)
    department_count = serializers.SerializerMethodField()
    program_count = serializers.SerializerMethodField()
    digital_maturity_label = serializers.SerializerMethodField()
    digital_maturity_description = serializers.SerializerMethodField()

    class Meta(InstitutionSerializer.Meta):
        fields = InstitutionSerializer.Meta.fields + [
            'leaders', 'department_count', 'program_count',
            'digital_maturity_label', 'digital_maturity_description',
        ]
        read_only_fields = InstitutionSerializer.Meta.read_only_fields + [
            'leaders', 'department_count', 'program_count',
            'digital_maturity_label', 'digital_maturity_description',
        ]

    def get_department_count(self, obj):
        return obj.departments.count()

    def get_program_count(self, obj):
        """Summed from the departments actually recorded, so it can never
        disagree with the Departments tab. Null-safe: an institution with no
        departments yet reports 0, not None."""
        return obj.departments.aggregate(total=Sum('program_count'))['total'] or 0

    def get_digital_maturity_label(self, obj):
        return obj.get_digital_maturity_level_display() if obj.digital_maturity_level else ''

    def get_digital_maturity_description(self, obj):
        return DIGITAL_MATURITY_DESCRIPTIONS.get(obj.digital_maturity_level, '')
