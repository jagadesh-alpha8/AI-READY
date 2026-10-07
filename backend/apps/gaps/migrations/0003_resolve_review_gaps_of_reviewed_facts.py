"""One-time backfill: close the "unconfirmed fact" gap of every fact that was
already Confirmed or Corrected before doing so started closing it
automatically (apps.gaps.services.resolve_unconfirmed_fact_gap). Without
this, those gaps would keep their -3 CRI penalty forever.

Same narrow rule as the live code: only gap_type=unconfirmed_fact, only for
confirmed/corrected facts. Conflicts, missing documents, low-confidence
flags and rejected facts are left alone. Safe to re-run: only touches
still-open gaps."""
from django.db import migrations
from django.utils import timezone


def resolve_unconfirmed_fact_gaps(apps, schema_editor):
    GapItem = apps.get_model('gaps', 'GapItem')
    now = timezone.now()
    GapItem.objects.filter(
        gap_type='unconfirmed_fact',
        status__in=['open', 'in_progress'],
        source_fact__status__in=['confirmed', 'corrected'],
    ).update(
        status='resolved',
        resolution='Automatically resolved: the fact had already been confirmed or corrected.',
        resolved_at=now,
        updated_at=now,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('gaps', '0002_gapitem_conflict_confidence_gapitem_conflict_fact_b_and_more'),
        ('facts', '0002_alter_extractedfact_value_and_more'),
    ]

    operations = [
        migrations.RunPython(resolve_unconfirmed_fact_gaps, migrations.RunPython.noop),
    ]
