/** Wording for capability-run results, matching A1's frontend/src/pages/capability/presentation.ts. */
import type { Job, Result } from '../types/capability';

export const isActive = (job?: Pick<Job, 'status'> | null) => !!job && (job.status === 'queued' || job.status === 'running');

/** Exact score when every condition is decided, otherwise the demonstrated–possible bounds. */
export const scoreLabel = (r: Pick<Result, 'exact_score' | 'lower' | 'upper'>) =>
  r.exact_score !== null ? `${r.exact_score.toFixed(1)} / 100` : `${r.lower.toFixed(1)}–${r.upper.toFixed(1)} / 100`;

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
