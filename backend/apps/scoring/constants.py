"""The CRI (Campus Readiness Index) pillars: the 9 criteria of InGage AI-QIF v1.0.

`PILLAR_CHOICES`/`PILLAR_LABELS` are the fixed *enumeration* of valid pillar
keys -- used as `choices=` on the `pillar` CharField in apps.facts,
apps.gaps, and apps.recommendations, so a fact/gap/recommendation can only
ever be tagged to one of these keys. That's a closed set the framework
defines, not scoring configuration, so it stays a constant rather than a
database row.

Pillar *weights* and *criteria*, on the other hand, are configurable scoring
structures -- see `apps.scoring.models.Pillar` and `PillarCriterion`. The
database `Pillar` table (seeded with these keys and the AI-QIF weights by
`apps/scoring/migrations/0004_aiqif_pillars.py`) is the single source of
truth the scoring engine reads, so changing a weight is a data change, not a
code change.

Until 2026-10 the CRI used eight pillars of its own (`LEGACY_PILLARS`). They
stay in the database, inactive, so scores and baselines approved under them
keep their names; their facts, gaps and recommendations were moved to the
matching AI-QIF criterion (`LEGACY_TO_AIQIF`).
"""

#: key, AI-QIF code, name, weight out of 1000, the criterion's key indicators.
#: From source_library_work/InGage_AI_READY_AI_QIF_Master_v1_0_AI_Criteria.xlsx.
AIQIF_PILLARS = [
    ('aiqif_c1', 'AIQIF-C1', 'Institutional AI Strategy & Governance', 120,
     ['AI Vision, Strategy & Portfolio', 'AI Governance & Accountability', 'AI Investment & Resource Planning',
      'AI Adoption, Change & Institutional Alignment']),
    ('aiqif_c2', 'AIQIF-C2', 'Responsible AI, Risk, Ethics & Compliance', 100,
     ['Responsible AI Policy & Principles', 'AI Risk, Privacy & Security Governance',
      'AI Model, Data & Lifecycle Governance', 'Human Oversight, Ethics & AI Assurance']),
    ('aiqif_c3', 'AIQIF-C3', 'AI-Ready Curriculum & Learning', 130,
     ['AI Curriculum Integration & Programme Design', 'AI Literacy Across Disciplines',
      'AI-Enabled Pedagogy & Assessment', 'Experiential, Project & Applied AI Learning']),
    ('aiqif_c4', 'AIQIF-C4', 'Faculty & Institutional Workforce AI Capability', 100,
     ['Faculty AI Literacy & Awareness', 'Role-Based Faculty AI Capability',
      'AI-Enabled Teaching, Research & Academic Practice', 'Staff AI Capability, FDP & Change Enablement']),
    ('aiqif_c5', 'AIQIF-C5', 'Student AI Readiness, Skills & Employability', 130,
     ['Universal Student AI Literacy', 'Advanced & Role-Specific AI Skills',
      'Student AI Projects, Portfolio & Practice', 'AI Employability, Internships & Career Outcomes']),
    ('aiqif_c6', 'AIQIF-C6', 'AI Infrastructure, Data & Cybersecurity', 120,
     ['AI Compute, Cloud & Platform Readiness', 'Institutional Data Readiness', 'AI Cybersecurity & Resilience',
      'AI Labs, Digital Learning Environment & Accessibility']),
    ('aiqif_c7', 'AIQIF-C7', 'AI Research, Innovation & Ecosystem', 100,
     ['AI Research Capability & Agenda', 'AI Centres of Excellence & Innovation',
      'AI Funding, IP & Entrepreneurship', 'AI Collaboration, Knowledge Transfer & Societal Impact']),
    ('aiqif_c8', 'AIQIF-C8', 'AI-Enabled Operations, Industry & Outcomes', 100,
     ['AI-Enabled Institutional Operations & Services', 'Industry Integration & AI Partnerships',
      'AI Entrepreneurship, Placement & Workforce Outcomes', 'Measured AI Business/Educational Outcomes']),
    ('aiqif_c9', 'AIQIF-C9', 'AI Assurance, Measurement & Continuous Improvement', 100,
     ['AI Readiness Measurement & CRI', 'Evidence, Traceability & Auditability',
      'Benchmark Evolution & AI Readiness Drift', 'Outcome Learning, UAT & Continuous Improvement']),
]

PILLAR_CHOICES = [(key, name) for key, _code, name, _w, _kis in AIQIF_PILLARS]

#: The 36 AI-QIF key indicators, in framework order: code -> (criterion key,
#: indicator name). Codes are the criterion code + the indicator's position,
#: 'AIQIF-C4.1' -- the same codes the benchmark library imported
#: (apps.benchmarks.services.aiqif_import). Used to tag extracted facts by
#: category (apps.facts.models.FactAIQIFMapping); the CRI doesn't score these.
AIQIF_INDICATORS = {
    f'{code}.{position}': (key, name)
    for key, code, _name, _w, kis in AIQIF_PILLARS
    for position, name in enumerate(kis, start=1)
}
AIQIF_INDICATOR_CHOICES = [(code, f'{code} {name}') for code, (_key, name) in AIQIF_INDICATORS.items()]
#: Criterion key -> its AI-QIF code, e.g. 'aiqif_c4' -> 'AIQIF-C4'.
AIQIF_CRITERION_CODES = {key: code for key, code, _name, _w, _kis in AIQIF_PILLARS}

#: The eight pillars used before AI-QIF -- kept only to label history.
LEGACY_PILLARS = [
    ('governance_strategy', 'Governance & Strategy'),
    ('curriculum_academic_readiness', 'Curriculum & Academic Readiness'),
    ('faculty_ai_capability', 'Faculty AI Capability'),
    ('student_ai_readiness', 'Student AI Readiness'),
    ('infrastructure_digital_capability', 'Infrastructure & Digital Capability'),
    ('research_innovation', 'Research & Innovation'),
    ('industry_placement', 'Industry & Placement Outcomes'),
    ('evidence_quality', 'Evidence Quality & Data Confidence'),
]

#: Where each legacy pillar's facts, gaps and recommendations went.
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

PILLAR_LABELS = {**dict(LEGACY_PILLARS), **dict(PILLAR_CHOICES)}

#: Bumped when the scoring *algorithm* itself changes (not when someone edits
#: a Pillar/PillarCriterion weight in the database -- that's captured
#: automatically by the config fingerprint appended to this in
#: `cri_engine._compute_calculation_version`). See that function's docstring.
SCORING_ENGINE_VERSION = '2.0'  # 2.0: pillars are the 9 AI-QIF v1.0 criteria

#: Fixed status rubric a pillar's `raw_score` (0-100) is classified against,
#: same style as apps.gaps.constants.GAP_PRIORITY_SCORE_PENALTY -- a
#: deterministic business rule, not a magic number invented per-sprint.
#: A pillar with zero evidence is 'not_started' regardless of these
#: thresholds, and any unresolved *blocking* gap on a pillar forces
#: 'at_risk' regardless of how high its raw_score is -- see
#: cri_engine._classify_pillar_status.
PILLAR_STATUS_STRONG_THRESHOLD = 70.0
PILLAR_STATUS_DEVELOPING_THRESHOLD = 40.0
