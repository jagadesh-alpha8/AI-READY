"""The eight-pillar CRI (Campus Readiness Index) rubric.

`PILLAR_CHOICES`/`PILLAR_LABELS` are the fixed *enumeration* of valid pillar
keys -- used as `choices=` on the `pillar` CharField in apps.facts,
apps.gaps, and apps.recommendations, so a fact/gap/recommendation can only
ever be tagged to one of these eight keys. That's a closed set the CRI
framework itself defines, not scoring configuration, so it stays a constant
rather than a database row.

Pillar *weights* and *criteria*, on the other hand, are genuinely
configurable scoring structures -- see `apps.scoring.models.Pillar` and
`PillarCriterion`. There is deliberately no `PILLAR_WEIGHTS` constant here:
the database `Pillar` table (seeded with these same eight keys by
`apps/scoring/migrations/0002_seed_pillars.py`) is the single source of
truth the scoring engine reads, so changing a weight is a data change, not a
code change.
"""

PILLAR_CHOICES = [
    ('governance_strategy', 'Governance & Strategy'),
    ('curriculum_academic_readiness', 'Curriculum & Academic Readiness'),
    ('faculty_ai_capability', 'Faculty AI Capability'),
    ('student_ai_readiness', 'Student AI Readiness'),
    ('infrastructure_digital_capability', 'Infrastructure & Digital Capability'),
    ('research_innovation', 'Research & Innovation'),
    ('industry_placement', 'Industry & Placement Outcomes'),
    ('evidence_quality', 'Evidence Quality & Data Confidence'),
]

PILLAR_LABELS = dict(PILLAR_CHOICES)

#: Bumped when the scoring *algorithm* itself changes (not when someone edits
#: a Pillar/PillarCriterion weight in the database -- that's captured
#: automatically by the config fingerprint appended to this in
#: `cri_engine._compute_calculation_version`). See that function's docstring.
SCORING_ENGINE_VERSION = '1.0'

#: Fixed status rubric a pillar's `raw_score` (0-100) is classified against,
#: same style as apps.gaps.constants.GAP_PRIORITY_SCORE_PENALTY -- a
#: deterministic business rule, not a magic number invented per-sprint.
#: A pillar with zero evidence is 'not_started' regardless of these
#: thresholds, and any unresolved *blocking* gap on a pillar forces
#: 'at_risk' regardless of how high its raw_score is -- see
#: cri_engine._classify_pillar_status.
PILLAR_STATUS_STRONG_THRESHOLD = 70.0
PILLAR_STATUS_DEVELOPING_THRESHOLD = 40.0
