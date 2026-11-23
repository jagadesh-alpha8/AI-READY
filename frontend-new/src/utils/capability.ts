/** Wording for capability-run results, matching A1's frontend/src/pages/capability/presentation.ts. */
import type { ConditionRecord, DepthReserve, Job, Result } from '../types/capability';
import { LEVELS } from './levels';

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

/** The readiness levels as score bands on the part-credit score (backend action_plan.DEFAULT_TIERS; utils/levels.ts). */
export const TIER_BANDS: [string, number][] = LEVELS.map((l) => [l.name, l.from]);
export const TIER_BANDS_TEXT = TIER_BANDS.map(([n, v]) => `${n} ${v}`).join(', ');

/** The band a part-credit score reaches, the next one and the points to it. */
export function bandTier(score: number): { current: string | null; next: string | null; pointsToNext: number } {
  const reached = TIER_BANDS.filter(([, v]) => score >= v);
  const ahead = TIER_BANDS.filter(([, v]) => score < v);
  return { current: reached.length ? reached[reached.length - 1][0] : null, next: ahead.length ? ahead[0][0] : null,
    pointsToNext: ahead.length ? Math.round((ahead[0][1] - score) * 100) / 100 : 0 };
}

/** Highest tier the run demonstrates, or null (never inferred from the upper bound). A part-credit run's tier is
 * its score band; the rubric's own tiers are not calibrated. */
export function achievedTier(r: Pick<Result, 'tiers' | 'badge_policy'> & Partial<Pick<Result, 'score'>>): string | null {
  if (r.score != null) return bandTier(r.score).current;
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

/** A fraction the backend sends as "1/4", "0.25" or a number; 0 when absent or unreadable. */
export function fraction(value: string | number | null | undefined): number {
  if (value == null || value === '') return 0;
  if (typeof value === 'number') return value;
  const [n, d] = value.split('/');
  const out = d === undefined ? Number(n) : Number(n) / Number(d);
  return Number.isFinite(out) ? out : 0;
}

const DEPTH_FRACTION: Record<string, number> = { evidenced: 0, substantiated: 0.5, strong: 1 };

/**
 * Share of a requirement's credit the headline counts (reserve.record_factor): 1 when nothing is held, otherwise
 * (1 - share) + share x depth shown. Credit below depth_min_credit is not asked about depth and holds nothing.
 */
export function countedShare(r: Pick<ConditionRecord, 'credit' | 'depth_share' | 'depth_level' | 'depth_min_credit'>): number {
  const share = fraction(r.depth_share);
  if (!share || !(r.credit && r.credit > 0)) return 1;
  const minimum = fraction(r.depth_min_credit);
  if (minimum && r.credit < minimum) return 1;
  return (1 - share) + share * (DEPTH_FRACTION[r.depth_level || 'evidenced'] ?? 0);
}

/** "credit 100%", or "credit 100% (75% counted until follow-up answers show depth)" while part of it is held. */
export function creditLabel(r: ConditionRecord): string {
  const credit = `credit ${Math.round((r.credit || 0) * 100)}%`;
  const counted = countedShare(r);
  return counted < 1 ? `${credit} (${Math.round(counted * 100)}% counted until follow-up answers show depth)` : credit;
}

const pts = (n: number) => `${Number(n.toFixed(2))} point${n === 1 ? '' : 's'}`;

/** One line for beside the headline score: what is still held and what answers earned back; null when nothing is held. */
export function heldLine(held?: DepthReserve | null): string | null {
  if (!held || !held.held_points) return null;
  const parts: string[] = [];
  if (held.still_held_points > 0) parts.push(`${pts(held.still_held_points)} held until you answer the follow-up questions`);
  if (held.earned_back_points > 0) parts.push(`${pts(held.earned_back_points)} earned back by your follow-up answers`);
  return parts.length ? parts.join(' · ') : null;
}
/** The two stages a college sees (23 Nov): the Stage 1 result before the follow-up questions, and the Final AI-READY
 * Score once the follow-up stage is closed (publishing the final result closes it). */
export const STAGE_ONE = 'Stage 1 result: Document Review';
export const FINAL_SCORE = 'Final AI-READY Score';
export const stageLabel = (stage?: string | null) => (stage === 'final' ? FINAL_SCORE : STAGE_ONE);
/** The tier is shown only on the final score: before the follow-ups the result is still open. */
export const tierShown = (stage?: string | null) => stage === 'final';
export const TIER_LATER = 'The tier is awarded on the final AI-READY Score, once the follow-up questions are complete.';

/** The readiness areas' names, as the reports print them (backend report_projection.PILLARS). */
export const PILLAR_NAMES: Record<string, string> = {
  'AIQIF-C1': 'Leadership and investment', 'AIQIF-C2': 'Responsible and safe AI', 'AIQIF-C3': 'Curriculum and teaching',
  'AIQIF-C4': 'Faculty and staff', 'AIQIF-C5': 'Student skills and careers', 'AIQIF-C6': 'Technology and data',
  'AIQIF-C7': 'Research and innovation', 'AIQIF-C8': 'Services and partnerships', 'AIQIF-C9': 'Measurement and improvement',
};
export const pillarName = (code: string) => PILLAR_NAMES[code] || code;
