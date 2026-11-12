/**
 * The handoff's gap classes (section 6.12) for the audit gaps the backend raises (apps/gaps GapItem.gap_type).
 * Every audit gap is about evidence, so each one is either an evidence-only gap or a contradiction; capability,
 * compliance and outcome gaps come from the benchmark assessment's improvement plan instead.
 */
export const GAP_CLASS: Record<string, string> = {
  missing_document: 'Evidence-only gap',
  unconfirmed_fact: 'Evidence-only gap',
  low_confidence: 'Evidence-only gap',
  stale_data: 'Evidence-only gap',
  conflict: 'Contradiction requiring resolution',
};

export const gapClass = (gapType: string): string => GAP_CLASS[gapType] || 'Applicability question';

/** Next-level impact in words, from the backend's per-priority penalty. */
export function gapImpact(priority: string): string {
  switch (priority) {
    case 'blocking': return 'Blocks the next level';
    case 'high': return 'High';
    case 'medium': return 'Medium';
    default: return 'Low';
  }
}
