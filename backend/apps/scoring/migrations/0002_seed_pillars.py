"""Seed the eight fixed CRI pillars as configurable database rows.

These are the same eight pillars/weights the project has used as a fixed
business rubric since the sprint/scoring work began (see the now-removed
`apps.scoring.constants.PILLAR_WEIGHTS`) -- this migration just moves them
from a Python constant into the database, which is what makes them
genuinely reconfigurable (an admin can retune a weight or add a criterion
without a code change) instead of a hardcoded table. It is not the
frontend's demo score data (that's fabricated per-pillar *scores*, e.g. 62.5
or 58.0; this is the pillar *definitions and weights* the engine computes
real scores against).

Each pillar gets one generic starter criterion ("general_evidence", weight
1.0, no `fact_field_keys` restriction) so the engine is fully functional out
of the box: it counts every confirmed/corrected fact tagged to that pillar.
More specific, narrower criteria can be layered in later purely as data
changes.
"""
from django.db import migrations

PILLARS = [
    ('governance_strategy', 'Governance & Strategy', 0.10, 0),
    ('curriculum_academic_readiness', 'Curriculum & Academic Readiness', 0.15, 1),
    ('faculty_ai_capability', 'Faculty AI Capability', 0.18, 2),
    ('student_ai_readiness', 'Student AI Readiness', 0.18, 3),
    ('infrastructure_digital_capability', 'Infrastructure & Digital Capability', 0.14, 4),
    ('research_innovation', 'Research & Innovation', 0.10, 5),
    ('industry_placement', 'Industry & Placement Outcomes', 0.10, 6),
    ('evidence_quality', 'Evidence Quality & Data Confidence', 0.05, 7),
]


def seed_pillars(apps, schema_editor):
    Pillar = apps.get_model('scoring', 'Pillar')
    PillarCriterion = apps.get_model('scoring', 'PillarCriterion')

    for key, name, weight, display_order in PILLARS:
        pillar, _ = Pillar.objects.update_or_create(
            key=key,
            defaults={'name': name, 'weight': weight, 'display_order': display_order},
        )
        PillarCriterion.objects.update_or_create(
            pillar=pillar, key='general_evidence',
            defaults={
                'name': 'General Evidence Coverage',
                'description': (
                    'Every confirmed/corrected fact tagged to this pillar, until '
                    'more specific criteria are configured.'
                ),
                'weight': 1.0,
                'fact_field_keys': [],
            },
        )


def unseed_pillars(apps, schema_editor):
    Pillar = apps.get_model('scoring', 'Pillar')
    Pillar.objects.filter(key__in=[key for key, *_ in PILLARS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('scoring', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_pillars, unseed_pillars),
    ]
