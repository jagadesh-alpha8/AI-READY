"""Fixed gap-scoring rubric.

`GapItem` no longer carries its own `score_impact` value -- that number is
now derived deterministically from `priority`, the same way `Sprint`'s
pillar weights are a fixed rubric rather than a per-row field. Used by
`apps.scoring.services` (as a scoring penalty) and
`apps.recommendations.services` (as a recommendation's expected CRI lift).
"""

GAP_PRIORITY_SCORE_PENALTY = {
    'blocking': 8.0,
    'high': 5.0,
    'medium': 3.0,
    'optional': 1.0,
}
