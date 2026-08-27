import django_filters

from .models import Institution


class InstitutionFilter(django_filters.FilterSet):
    class Meta:
        model = Institution
        fields = {
            'is_active': ['exact'],
            'institution_type': ['exact', 'icontains'],
            'state': ['exact', 'icontains'],
            'country': ['exact', 'icontains'],
            'created_by': ['exact'],
        }
