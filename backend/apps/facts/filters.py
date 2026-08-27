import django_filters

from apps.scoring.constants import PILLAR_CHOICES

from .models import ExtractedFact


class ExtractedFactFilter(django_filters.FilterSet):
    pillar = django_filters.ChoiceFilter(choices=PILLAR_CHOICES)
    status = django_filters.ChoiceFilter(choices=ExtractedFact.Status.choices)
    owner_role = django_filters.CharFilter(field_name='owner_role', lookup_expr='iexact')
    document = django_filters.UUIDFilter(field_name='document_id')
    confidence = django_filters.NumberFilter(field_name='confidence_score')
    confidence_min = django_filters.NumberFilter(field_name='confidence_score', lookup_expr='gte')
    confidence_max = django_filters.NumberFilter(field_name='confidence_score', lookup_expr='lte')

    class Meta:
        model = ExtractedFact
        fields = ['pillar', 'status', 'owner_role', 'document', 'confidence']
