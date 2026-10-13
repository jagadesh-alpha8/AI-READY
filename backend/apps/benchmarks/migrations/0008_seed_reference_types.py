"""Seed institution and programme types (the blueprint's institution scope:
Engineering, Polytechnic, Arts and Science, ITI and university-linked health sciences)."""
from django.db import migrations

INSTITUTION_TYPES = [
    ('university', 'University'),
    ('engineering', 'Engineering college'),
    ('polytechnic', 'Polytechnic'),
    ('arts_science', 'Arts & Science college'),
    ('iti', 'Industrial Training Institute (ITI)'),
    ('health_sciences', 'Health-sciences institution'),
]

PROGRAMME_TYPES = [
    ('ug_engineering', 'UG engineering (B.E. / B.Tech)', 'technical'),
    ('pg_engineering', 'PG engineering (M.E. / M.Tech)', 'technical'),
    ('diploma_engineering', 'Diploma in engineering', 'technical'),
    ('mca', 'Computer applications (MCA)', 'technical'),
    ('mba_pgdm', 'Management (MBA / PGDM)', 'technical'),
    ('ug_arts_science', 'UG arts, science & commerce (B.A. / B.Sc. / B.Com)', 'higher_education'),
    ('pg_arts_science', 'PG arts, science & commerce (M.A. / M.Sc. / M.Com)', 'higher_education'),
    ('phd', 'Doctoral (PhD)', 'research'),
    ('iti_trade', 'ITI craftsman trade (CTS)', 'skills'),
    ('apprenticeship', 'Apprenticeship / NSQF qualification', 'skills'),
    ('health_ug', 'UG health sciences (MBBS / BDS / B.Sc. Nursing / B.Pharm)', 'health'),
]


def seed(apps, schema_editor):
    InstitutionType = apps.get_model('benchmarks', 'InstitutionType')
    ProgrammeType = apps.get_model('benchmarks', 'ProgrammeType')
    for code, name in INSTITUTION_TYPES:
        InstitutionType.objects.get_or_create(code=code, defaults={'name': name})
    for code, name, sector in PROGRAMME_TYPES:
        ProgrammeType.objects.get_or_create(code=code, defaults={'name': name, 'sector': sector})


class Migration(migrations.Migration):
    dependencies = [('benchmarks', '0007_institutiontype_programmetype_applicabilityrule')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
