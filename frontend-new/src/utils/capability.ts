/** Wording for capability-run results, matching A1's frontend/src/pages/capability/presentation.ts. */
import type { Job, Result } from '../types/capability';

export const isActive = (job?: Pick<Job, 'status'> | null) => !!job && (job.status === 'queued' || job.status === 'running');

/**
 * A2 part-credit runs: the one headline score. Earlier runs: the exact score when every condition is decided,
 * otherwise the demonstrated–possible bounds (matches A2's frontend/src/pages/capability/presentation.ts).
 */
export const scoreLabel = (r: Pick<Result, 'exact_score' | 'lower' | 'upper'> & Partial<Pick<Result, 'score'>>) =>
  r.score != null ? `${r.score.toFixed(1)} / 100`
    : r.exact_score !== null ? `${r.exact_score.toFixed(1)} / 100` : `${r.lower.toFixed(1)}–${r.upper.toFixed(1)} / 100`;

/** The single number a run reports, or null when it only has bounds. */
export const headlineScore = (r: Pick<Result, 'exact_score'> & Partial<Pick<Result, 'score'>>): number | null =>
  r.score != null ? r.score : r.exact_score;

/** Whether this run was scored with A2 part credit (one score, no upper bound). */
export const isPartCredit = (r: Partial<Pick<Result, 'score' | 'documented'>>) => r.score != null || !!r.documented;

/** Part-credit runs report one score per readiness area; earlier runs keep their recorded bounds. */
export function pillarScoreLabel(r: Partial<Pick<Result, 'documented'>>, code: string, lower: number, upper: number) {
  const d = r.documented?.pillars.find((p) => p.code === code);
  return d ? `${d.score} / 100` : `${lower}–${upper} / 100`;
}
export function indicatorScoreLabel(r: Partial<Pick<Result, 'documented'>>, code: string, lower: number, upper: number) {
  const d = r.documented?.indicators.find((i) => i.code === code);
  return d ? `${d.score} / 100` : `${lower}–${upper} / 100`;
}

export const PART_LABEL: Record<string, string> = { full: 'Evidenced', related: 'Related evidence only', not_found: 'Not found' };
export const partLabel = (s: string) => PART_LABEL[s] || s.replace(/_/g, ' ');
export const partTone = (s: string) => (s === 'full' ? 'good' : s === 'related' ? 'warn' : 'bad');

export const CAUSE_LABEL: Record<string, string> = {
  assessed: 'Assessed against the evidence',
  scope_or_period_unsupported: 'Population or period not established',
  review_guard: 'Held for review (rejected or superseded claim)',
  response_invalid: 'Model response could not be used',
  not_evaluated: 'Not evaluated',
  assessor_disagreement: 'Assessor passes disagreed',
};
export const causeLabel = (s: string) => CAUSE_LABEL[s] || s.replace(/_/g, ' ');

export const STATE_LABEL: Record<string, string> = {
  met: 'Demonstrated',
  not_met: 'Documented shortfall',
  unknown: 'Evidence needed',
  conflicting: 'Contradictory evidence',
};
export const stateLabel = (s: string) => STATE_LABEL[s] || s.replace(/_/g, ' ');

export const TIER_ELIGIBILITY: Record<string, string> = {
  demonstrated: 'Demonstrated',
  requirements_unmet: 'Requirements unmet',
  unresolved: 'Unresolved evidence',
};
export const tierLabel = (s: string) => TIER_ELIGIBILITY[s] || s.replace(/_/g, ' ');

/** Status pill tone for a tier eligibility or condition state. */
export const capabilityTone = (s: string) =>
  s === 'demonstrated' || s === 'met' ? 'good' : s === 'requirements_unmet' || s === 'not_met' || s === 'conflicting' ? 'bad' : 'warn';

/** Highest tier the run demonstrates, or null (never inferred from the upper bound). */
export function achievedTier(r: Pick<Result, 'tiers' | 'badge_policy'>): string | null {
  if (r.badge_policy === 'not_calibrated') return null;
  const shown = r.tiers.filter((t) => t.eligibility === 'demonstrated');
  return shown.length ? shown[shown.length - 1].name : null;
}

/** Count of conditions per state across every indicator. */
export function stateCounts(r: Pick<Result, 'indicators'>): Record<string, number> {
  const out: Record<string, number> = { met: 0, not_met: 0, unknown: 0, conflicting: 0 };
  for (const i of r.indicators) for (const c of i.conditions) out[c.state] = (out[c.state] || 0) + 1;
  return out;
}

/** A fresh idempotency key for one explicit "start" click. */
export const newKey = () =>
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
