import django_filters

from apps.scoring.constants import PILLAR_CHOICES

from .models import GapItem


class GapItemFilter(django_filters.FilterSet):
    gap_type = django_filters.ChoiceFilter(choices=GapItem.GapType.choices)
    status = django_filters.ChoiceFilter(choices=GapItem.Status.choices)
    priority = django_filters.ChoiceFilter(choices=GapItem.Priority.choices)
    pillar = django_filters.ChoiceFilter(choices=PILLAR_CHOICES)

    class Meta:
        model = GapItem
        fields = ['gap_type', 'status', 'priority', 'pillar']
