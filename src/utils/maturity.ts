/**
 * Maturity vocabulary of the roadmap design, mapped onto what the backend actually stores.
 *
 * The backend's benchmark levels are L3 "Foundational", L2 "Good / Recommended" and L1 "Advanced /
 * Aspirational" (apps/benchmarks/models.py). The handoff's Silver (Foundation), Gold (Institutional adoption)
 * and Platinum (Leadership) read naturally as those three levels, and the handoff prototype's own benchmark
 * table shows "L3 current, L2 required for Gold". This mapping is presentational only. The backend has no
 * Silver / Gold / Platinum CRI thresholds, pillar floors or gates, so none are shown or invented here.
 */
export type Tier = 'silver' | 'gold' | 'platinum';

export const TIERS: { tier: Tier; level: 'L3' | 'L2' | 'L1'; name: string; summary: string }[] = [
  { tier: 'silver', level: 'L3', name: 'Silver', summary: 'Foundation: baseline governance, infrastructure, safeguards and selected AI adoption' },
  { tier: 'gold', level: 'L2', name: 'Gold', summary: 'Institutional adoption: consistent AI capability, operational governance, measured outcomes' },
  { tier: 'platinum', level: 'L1', name: 'Platinum', summary: 'Leadership and optimisation: continuous improvement, verified outcomes, external leadership' },
];

const LEVEL_TO_TIER: Record<string, Tier> = { L3: 'silver', L2: 'gold', L1: 'platinum' };

/** 'L2' -> 'Gold'; unknown or empty -> 'Unverified'. */
export function tierName(level: string | null | undefined): string {
  const tier = level ? LEVEL_TO_TIER[level] : undefined;
  return tier ? TIERS.find((t) => t.tier === tier)!.name : 'Unverified';
}

/** Rank so a higher tier compares greater: L3 = 1, L2 = 2, L1 = 3, anything else 0. */
export function levelRank(level: string | null | undefined): number {
  return level === 'L3' ? 1 : level === 'L2' ? 2 : level === 'L1' ? 3 : 0;
}

/** Whether an achieved level meets a target level (L1 meets L2 and L3; '' meets nothing). */
export function meetsLevel(current: string | null | undefined, target: string | null | undefined): boolean {
  return levelRank(current) > 0 && levelRank(current) >= levelRank(target);
}

/** The next tier above the achieved one (Unverified -> Silver, Silver -> Gold, ...), or null at Platinum. */
export function nextTier(level: string | null | undefined): (typeof TIERS)[number] | null {
  const rank = levelRank(level);
  return TIERS[rank] ?? null;
}

/**
 * The institution's achieved level from its benchmark rows: the lowest level achieved across every included,
 * scored benchmark (one weak benchmark holds the institution back). Null when nothing is scored yet, so an
 * unscored institution is shown as unverified rather than failed.
 */
export function institutionLevel(rows: { included: boolean | null; assessment: { current_level: string } | null }[]): string | null {
  const levels = rows
    .filter((r) => r.included !== false && r.assessment && r.assessment.current_level)
    .map((r) => r.assessment!.current_level);
  if (levels.length === 0) return null;
  return levels.reduce((low, l) => (levelRank(l) < levelRank(low) ? l : low));
}

/** The three pacing routes of the handoff (section 5). Descriptive only: the backend has no route model. */
export const ROUTES = [
  { key: 'immediate', name: 'Immediate', eyebrow: 'High intensity', period: '5–7 months', effort: 'High',
    text: 'Parallel delivery with dedicated programme resources and higher near-term investment.' },
  { key: 'progressive', name: 'Progressive', eyebrow: 'Balanced', period: '9–12 months', effort: 'Medium',
    text: 'Sequenced delivery that balances business continuity, capacity and measurable progress.' },
  { key: 'gradual', name: 'Gradual', eyebrow: 'Lower intensity', period: '15–18 months', effort: 'Low',
    text: 'Phased delivery using existing teams with lower immediate investment and longer duration.' },
] as const;
