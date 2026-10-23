import django_filters
from django.db.models import Q, TextField
from django.db.models.functions import Cast

from apps.scoring.constants import AIQIF_INDICATOR_CHOICES, PILLAR_CHOICES

from .models import ExtractedFact

#: Confidence bands of the Facts Review filter: (lower bound inclusive, upper bound exclusive).
CONFIDENCE_BANDS = {'high': (0.8, None), 'medium': (0.5, 0.8), 'low': (None, 0.5)}


def confidence_band_q(band, field='confidence_score'):
    low, high = CONFIDENCE_BANDS[band]
    q = Q()
    if low is not None:
        q &= Q(**{f'{field}__gte': low})
    if high is not None:
        q &= Q(**{f'{field}__lt': high})
    return q


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
    confidence_band = django_filters.ChoiceFilter(choices=[(b, b) for b in CONFIDENCE_BANDS], method='filter_band')
    #: 'none' = not classified yet.
    fact_kind = django_filters.ChoiceFilter(choices=[*ExtractedFact.FactKind.choices, ('none', 'Not classified')],
                                            method='filter_kind')
    #: The source document's file name, as the Facts Review "Source document" filter shows it.
    source_document = django_filters.CharFilter(method='filter_source_document')
    #: Facts with a tag in this review state: confirmed / rejected (by an expert), reviewed (either), pending
    #: (waiting for one).
    tag_review = django_filters.ChoiceFilter(choices=[('confirmed', 'confirmed'), ('rejected', 'rejected'),
                                                      ('reviewed', 'reviewed'), ('pending', 'pending')],
                                             method='filter_tag_review')
    #: Free text: field ID / name, value, quote, source file name, AI-QIF indicator.
    q = django_filters.CharFilter(method='filter_search')

    def filter_tag_review(self, queryset, name, value):
        from .aiqif_tagging import queued_tags_q
        from .models import FactAIQIFMapping
        if value == 'pending':
            tags = FactAIQIFMapping.objects.filter(queued_tags_q())
        elif value == 'reviewed':
            tags = FactAIQIFMapping.objects.filter(review_status__in=['confirmed', 'rejected'])
        else:
            tags = FactAIQIFMapping.objects.filter(review_status=value)
        return queryset.filter(id__in=tags.values('fact_id'))

    def filter_band(self, queryset, name, value):
        return queryset.filter(confidence_band_q(value))

    def filter_kind(self, queryset, name, value):
        return queryset.filter(fact_kind='' if value == 'none' else value)

    def filter_source_document(self, queryset, name, value):
        return queryset.filter(source_document__original_filename=value)

    def filter_search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        matching = (ExtractedFact.objects.filter(sprint_id__in=queryset.values('sprint_id'))
                    .annotate(value_text=Cast('value', output_field=TextField()))
                    .filter(Q(field_key__icontains=value) | Q(field_name__icontains=value)
                            | Q(value_text__icontains=value) | Q(source_snippet__icontains=value)
                            | Q(source_document__original_filename__icontains=value)
                            | Q(aiqif_mappings__indicator_code__icontains=value))
                    .values('id'))
        return queryset.filter(id__in=matching)

    class Meta:
        model = ExtractedFact
        fields = ['pillar', 'status', 'owner_role', 'document', 'confidence']
