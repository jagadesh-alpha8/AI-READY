from django.db import migrations

DESCRIPTION = (
    'Four separate scores per benchmark (0-100): compliance, maturity, evidence confidence and outcome. '
    'Composite = compliance_weight x compliance + maturity_weight x maturity + evidence_weight x evidence '
    'confidence + outcome_weight x outcome, using the weights the benchmark owner approved for each benchmark '
    '(they add up to 1). No approved weights = no composite.'
)


def seed(apps, schema_editor):
    ScoringModel = apps.get_model('assessments', 'ScoringModel')
    ScoringModel.objects.get_or_create(code='BM-SCORE-1', defaults={
        'name': 'Benchmark scoring model 1', 'formula_version': '1.0', 'description': DESCRIPTION, 'active': True})


class Migration(migrations.Migration):
    dependencies = [('assessments', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
