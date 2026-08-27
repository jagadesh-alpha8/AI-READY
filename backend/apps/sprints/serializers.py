from rest_framework import serializers

from apps.institutions.models import Institution

from .models import Sprint


class SprintSerializer(serializers.ModelSerializer):
    institution_id = serializers.PrimaryKeyRelatedField(
        source='institution', queryset=Institution.objects.all(),
    )
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # Frontend-compatible alias: the existing (unmodified) frontend's
    # SprintSetup.tsx posts `sprint_mode`, and Dashboard.tsx reads
    # `sprint.sprint_mode` back off the list response -- without this,
    # creation silently ignores the user's picked mode (falls back to the
    # model default) and the dashboard table crashes calling `.replace()`
    # on `undefined`.
    sprint_mode = serializers.ChoiceField(
        source='mode', choices=Sprint.SprintMode.choices, required=False,
    )

    class Meta:
        model = Sprint
        fields = [
            'id', 'institution_id', 'name', 'sprint_code', 'mode', 'sprint_mode', 'status',
            'academic_year', 'description', 'start_date', 'target_completion_date',
            'completion_percentage', 'overall_cri', 'confidence_score',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'sprint_code', 'overall_cri', 'confidence_score',
            'created_by', 'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        target_date = attrs.get('target_completion_date', getattr(self.instance, 'target_completion_date', None))
        if start_date and target_date and target_date < start_date:
            raise serializers.ValidationError({
                'target_completion_date': 'Target completion date cannot be before the start date.',
            })

        new_status = attrs.get('status')
        if self.instance is None:
            # Creation: a sprint always enters the pipeline at 'draft'.
            if new_status is not None and new_status != Sprint.Status.DRAFT:
                raise serializers.ValidationError({
                    'status': "New sprints must start in 'draft' status.",
                })
        elif new_status is not None and new_status != self.instance.status:
            allowed = Sprint.ALLOWED_TRANSITIONS.get(self.instance.status, set())
            if new_status not in allowed:
                allowed_display = ', '.join(sorted(str(s) for s in allowed)) or 'none (terminal)'
                raise serializers.ValidationError({
                    'status': (
                        f"Cannot transition sprint status from '{self.instance.status}' to "
                        f"'{new_status}'. Allowed next statuses: {allowed_display}."
                    ),
                })
            # A status change advances completion to its pipeline milestone,
            # unless the caller explicitly set completion_percentage themselves.
            if 'completion_percentage' not in self.initial_data:
                attrs['completion_percentage'] = Sprint.STATUS_COMPLETION_MILESTONES[new_status]

        return attrs
