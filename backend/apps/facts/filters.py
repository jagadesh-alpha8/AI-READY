import django_filters

from apps.scoring.constants import AIQIF_INDICATOR_CHOICES, PILLAR_CHOICES

from .models import ExtractedFact


class ExtractedFactFilter(django_filters.FilterSet):
    pillar = django_filters.ChoiceFilter(choices=PILLAR_CHOICES)
    status = django_filters.ChoiceFilter(choices=ExtractedFact.Status.choices)
    # AI-QIF category tags: a fact matches if any of its tags does.
    aiqif_criterion = django_filters.ChoiceFilter(
        field_name='aiqif_mappings__criterion', choices=PILLAR_CHOICES, distinct=True,
    )
    aiqif_indicator = django_filters.ChoiceFilter(
        field_name='aiqif_mappings__indicator_code', choices=AIQIF_INDICATOR_CHOICES, distinct=True,
    )
    aiqif_mapping_status = django_filters.ChoiceFilter(choices=ExtractedFact.AIQIFMappingStatus.choices)
    owner_role = django_filters.CharFilter(field_name='owner_role', lookup_expr='iexact')
    document = django_filters.UUIDFilter(field_name='document_id')
    confidence = django_filters.NumberFilter(field_name='confidence_score')
    confidence_min = django_filters.NumberFilter(field_name='confidence_score', lookup_expr='gte')
    confidence_max = django_filters.NumberFilter(field_name='confidence_score', lookup_expr='lte')

    class Meta:
        model = ExtractedFact
        fields = ['pillar', 'status', 'owner_role', 'document', 'confidence']
