import { levelRank } from './maturity';

/** The four source classes the handoff asks to keep apart (catalogue benchmark_kind). */
export const KIND_LABEL: Record<string, string> = {
  mandatory: 'Mandatory regulatory requirement',
  recommended: 'Accreditation / ranking expectation',
  guidance: 'Recommended good practice',
  proposed: 'InGage proposed AI-readiness benchmark',
};

/** Distance from a benchmark's current level to its target: 'Met', 'N levels', or 'Not scored' (unknown stays unknown). */
export function gapText(row: { target_level: string; assessment: { current_level: string } | null }): string {
  const current = row.assessment?.current_level;
  if (!current) return 'Not scored';
  const diff = levelRank(row.target_level) - levelRank(current);
  return diff <= 0 ? 'Met' : `${diff} level${diff > 1 ? 's' : ''}`;
}
