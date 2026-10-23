import django_filters
from django.db.models import Q

from apps.scoring.constants import PILLAR_CHOICES

from .models import GapItem


def owner_role_q(role):
    """Gaps whose owner (apps/facts/ownership.gap_owner_role) is `role`: the source fact's owner, else the
    related document's; a Missing Document gap is owned by its upload-checklist entry (worked out per gap,
    there are only a few)."""
    from apps.facts.ownership import gap_owner_role, normalize_role
    role = normalize_role(role)
    q = (Q(source_fact__isnull=False, source_fact__owner_role__iexact=role)
         | Q(source_fact__isnull=True, related_document__isnull=False, related_document__owner_role__iexact=role))
    missing = GapItem.objects.filter(gap_type=GapItem.GapType.MISSING_DOCUMENT, source_fact__isnull=True,
                                     related_document__isnull=True)
    ids = [g.id for g in missing if gap_owner_role(g) == role]
    return q | Q(id__in=ids)


def source_document_q(filename):
    """Gaps shown with this Source (GapItemSerializer.get_source_document_filename)."""
    return (Q(source_fact__source_document__original_filename=filename)
            | Q(source_fact__source_document__isnull=True, source_fact__document__original_filename=filename)
            | Q(source_fact__isnull=True, related_document__original_filename=filename))


class GapItemFilter(django_filters.FilterSet):
    gap_type = django_filters.ChoiceFilter(choices=GapItem.GapType.choices)
    status = django_filters.ChoiceFilter(choices=GapItem.Status.choices)
    priority = django_filters.ChoiceFilter(choices=GapItem.Priority.choices)
    pillar = django_filters.ChoiceFilter(choices=PILLAR_CHOICES)
    owner_role = django_filters.CharFilter(method='filter_owner_role')
    source_document = django_filters.CharFilter(method='filter_source_document')
    #: Free text: title, description, field ID, quote, source file name.
    q = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = GapItem
        fields = ['gap_type', 'status', 'priority', 'pillar']

    def filter_owner_role(self, queryset, name, value):
        return queryset.filter(owner_role_q(value))

    def filter_source_document(self, queryset, name, value):
        return queryset.filter(source_document_q(value))

    def filter_search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
            | Q(source_fact__field_key__icontains=value) | Q(source_fact__source_snippet__icontains=value)
            | Q(conflict_fact_b__source_snippet__icontains=value)
            | Q(source_fact__source_document__original_filename__icontains=value)
            | Q(source_fact__document__original_filename__icontains=value)
            | Q(related_document__original_filename__icontains=value))
