import type { Job, Result, Action, Recommendation } from '../../api/capability';
export const active = (job?: Job | null) =>
  !!job && ['queued', 'running'].includes(job.status);
export const scoreLabel = (r: Result) =>
  r.exact_score !== null
    ? `${r.exact_score.toFixed(2)} / 100`
    : `${r.lower.toFixed(2)}–${r.upper.toFixed(2)} / 100`;
export const stateLabel = (state: string) =>
  ({
    met: 'Demonstrated',
    not_met: 'Documented shortfall',
    unknown: 'Evidence needed',
    conflicting: 'Contradictory evidence',
  })[state] || state.replace(/_/g, ' ');
export const tierLabel = (state: string) =>
  ({
    demonstrated: 'Demonstrated',
    requirements_unmet: 'Requirements unmet',
    unresolved: 'Unresolved evidence',
  })[state] || state;
export function actionsFor(
  assessment: { actions: Action[] },
  recommendation: Recommendation | null,
  plan?: Recommendation['plan'],
) {
  return recommendation?.plan.actions || plan?.actions || assessment.actions;
}
// A new explicit attempt retains its key for network retries of the same inputs.
export function attempt(
  previous: { signature: string; key: string } | null,
  signature: string,
  makeKey: () => string,
) {
  return previous?.signature === signature
    ? previous
    : { signature, key: makeKey() };
}
