"""Make the 9 InGage AI-QIF v1.0 criteria the CRI pillars.

- Creates the nine pillars (weights = AI-QIF weights / 1000), each with the
  same one generic "general_evidence" criterion the old pillars had.
- Deactivates the eight old pillars. They are NOT deleted: scores, runs and
  baselines decided under them keep their pillar names.
- Moves every fact, gap and recommendation to the matching criterion
  (governance -> C1, curriculum -> C3, faculty -> C4, students -> C5,
  infrastructure -> C6, research -> C7, industry & placement -> C8,
  evidence quality -> C9). C2 Responsible AI had no old pillar; it fills from
  new extractions.
- A baseline still PENDING was scored on the old pillars, so it is returned
  for re-scoring (with a note and a history entry); the sprint goes back to
  REVIEWING exactly as a manual return would. Approved / provisional
  baselines and their reports are untouched.

Data is inlined (not imported) so this migration never changes meaning later.
"""
from django.db import migrations

AIQIF = [
    ('aiqif_c1', 'Institutional AI Strategy & Governance', 0.12,
     'AI-QIF C1: AI vision, strategy & portfolio; AI governance & accountability; AI investment & resource '
     'planning; AI adoption, change & institutional alignment.'),
    ('aiqif_c2', 'Responsible AI, Risk, Ethics & Compliance', 0.10,
     'AI-QIF C2: responsible AI policy & principles; AI risk, privacy & security governance; AI model, data & '
     'lifecycle governance; human oversight, ethics & AI assurance.'),
    ('aiqif_c3', 'AI-Ready Curriculum & Learning', 0.13,
     'AI-QIF C3: AI curriculum integration & programme design; AI literacy across disciplines; AI-enabled '
     'pedagogy & assessment; experiential, project & applied AI learning.'),
    ('aiqif_c4', 'Faculty & Institutional Workforce AI Capability', 0.10,
     'AI-QIF C4: faculty AI literacy & awareness; role-based faculty AI capability; AI-enabled teaching, research '
     '& academic practice; staff AI capability, FDP & change enablement.'),
    ('aiqif_c5', 'Student AI Readiness, Skills & Employability', 0.13,
     'AI-QIF C5: universal student AI literacy; advanced & role-specific AI skills; student AI projects, portfolio '
     '& practice; AI employability, internships & career outcomes.'),
    ('aiqif_c6', 'AI Infrastructure, Data & Cybersecurity', 0.12,
     'AI-QIF C6: AI compute, cloud & platform readiness; institutional data readiness; AI cybersecurity & '
     'resilience; AI labs, digital learning environment & accessibility.'),
    ('aiqif_c7', 'AI Research, Innovation & Ecosystem', 0.10,
     'AI-QIF C7: AI research capability & agenda; AI centres of excellence & innovation; AI funding, IP & '
     'entrepreneurship; AI collaboration, knowledge transfer & societal impact.'),
    ('aiqif_c8', 'AI-Enabled Operations, Industry & Outcomes', 0.10,
     'AI-QIF C8: AI-enabled institutional operations & services; industry integration & AI partnerships; AI '
     'entrepreneurship, placement & workforce outcomes; measured AI business/educational outcomes.'),
    ('aiqif_c9', 'AI Assurance, Measurement & Continuous Improvement', 0.10,
     'AI-QIF C9: AI readiness measurement & CRI; evidence, traceability & auditability; benchmark evolution & AI '
     'readiness drift; outcome learning, UAT & continuous improvement.'),
]

LEGACY_TO_AIQIF = {
    'governance_strategy': 'aiqif_c1',
    'curriculum_academic_readiness': 'aiqif_c3',
    'faculty_ai_capability': 'aiqif_c4',
    'student_ai_readiness': 'aiqif_c5',
    'infrastructure_digital_capability': 'aiqif_c6',
    'research_innovation': 'aiqif_c7',
    'industry_placement': 'aiqif_c8',
    'evidence_quality': 'aiqif_c9',
}

RETURN_NOTE = ('The CRI pillars changed to the 9 InGage AI-QIF v1.0 criteria. This baseline was scored on the old '
               'pillars, so it was returned for re-scoring: recalculate the CRI, then submit the baseline again.')


def forward(apps, schema_editor):
    Pillar = apps.get_model('scoring', 'Pillar')
    PillarCriterion = apps.get_model('scoring', 'PillarCriterion')
    Baseline = apps.get_model('scoring', 'Baseline')
    History = apps.get_model('scoring', 'BaselineDecisionHistory')
    Sprint = apps.get_model('sprints', 'Sprint')

    for order, (key, name, weight, description) in enumerate(AIQIF):
        pillar, _ = Pillar.objects.update_or_create(key=key, defaults={
            'name': name, 'weight': weight, 'description': description, 'display_order': order, 'is_active': True})
        PillarCriterion.objects.update_or_create(pillar=pillar, key='general_evidence', defaults={
            'name': 'General Evidence Coverage',
            'description': 'Every confirmed/corrected fact tagged to this pillar, until more specific criteria '
                           '(e.g. one per AI-QIF key indicator) are configured.',
            'weight': 1.0, 'fact_field_keys': [], 'is_active': True})
    Pillar.objects.filter(key__in=LEGACY_TO_AIQIF).update(is_active=False)

    for app, model in (('facts', 'ExtractedFact'), ('gaps', 'GapItem'), ('recommendations', 'Recommendation')):
        Model = apps.get_model(app, model)
        for old, new in LEGACY_TO_AIQIF.items():
            Model.objects.filter(pillar=old).update(pillar=new)

    for baseline in Baseline.objects.filter(status='pending'):
        baseline.status = 'returned'
        baseline.comments = RETURN_NOTE
        baseline.save(update_fields=['status', 'comments', 'updated_at'])
        History.objects.create(baseline=baseline, action='returned', user=None, comments=RETURN_NOTE)
        Sprint.objects.filter(pk=baseline.sprint_id, status='baseline_pending').update(status='reviewing')


def backward(apps, schema_editor):
    Pillar = apps.get_model('scoring', 'Pillar')
    to_legacy = {new: old for old, new in LEGACY_TO_AIQIF.items()}
    to_legacy['aiqif_c2'] = 'governance_strategy'  # C2 had no legacy pillar; governance is closest
    for app, model in (('facts', 'ExtractedFact'), ('gaps', 'GapItem'), ('recommendations', 'Recommendation')):
        Model = apps.get_model(app, model)
        for new, old in to_legacy.items():
            Model.objects.filter(pillar=new).update(pillar=old)
    Pillar.objects.filter(key__in=LEGACY_TO_AIQIF).update(is_active=True)
    Pillar.objects.filter(key__in=[k for k, *_ in AIQIF]).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('scoring', '0003_baseline_baselinedecisionhistory'),
        ('facts', '0002_alter_extractedfact_value_and_more'),
        ('gaps', '0003_resolve_review_gaps_of_reviewed_facts'),
        ('recommendations', '0001_initial'),
        ('sprints', '0003_alter_sprint_status'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
