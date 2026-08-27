import django_filters

from .models import Sprint


class SprintFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Sprint.Status.choices)
    mode = django_filters.ChoiceFilter(choices=Sprint.SprintMode.choices)
    institution = django_filters.UUIDFilter(field_name='institution_id')
    created_by = django_filters.UUIDFilter(field_name='created_by_id')

    class Meta:
        model = Sprint
        fields = ['status', 'mode', 'institution', 'created_by']
