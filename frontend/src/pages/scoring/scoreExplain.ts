/**
 * Plain-language explanations for the Live CRI Preview's scores (`npm test` runs these on Node directly).
 * Every number comes from the score API (backend apps/scoring/services/cri_engine.py build_score_snapshot and
 * coverage.py compute_coverage); nothing here calculates a score. These only say what a value means and why
 * it is zero or missing.
 */
import type { EvidenceCoverage, PillarScore, Scorecard } from '../../types/scoring.ts';

/** The confidence band the page has always shown: High at 80% or more, otherwise Building. */
export function confidenceBand(confidence: number | null | undefined): string {
  if (confidence == null) return '—';
  return confidence >= 0.8 ? 'High (>=80%)' : 'Building (below 80%)';
}

/** "120 / 1000 (12%)" -- pillar weights are fractions of 1 (AI-QIF criterion weights out of 1000). */
export function weightLabel(weight: number | null | undefined): string {
  if (weight == null) return '—';
  return `${Math.round(weight * 1000)} / 1000 (${(weight * 100).toFixed(1).replace(/\.0$/, '')}%)`;
}

export function hasCoverage(c: Scorecard['evidence_coverage'] | null | undefined): c is EvidenceCoverage {
  return !!c && 'formula_version' in c;
}

/** Covered / uncovered / excluded / unresolved, straight from the API's counts. */
export function coverageCounts(c: EvidenceCoverage) {
  return {
    covered: c.covered_count,
    uncovered: Math.max(0, c.applicable_count - c.covered_count),
    excluded: c.excluded_count,
    unresolved: c.unresolved_applicability_count,
    applicable: c.applicable_count,
  };
}

/** Why the Raw CRI is 0, or '' when it is not. */
export function rawCriZeroReason(s: Scorecard): string {
  if (s.raw_cri > 0) return '';
  const reviewed = s.evidence_metrics.confirmed_facts + s.evidence_metrics.corrected_facts;
  if (reviewed === 0) {
    return s.evidence_metrics.total_extracted_facts > 0
      ? `None of the sprint's ${s.evidence_metrics.total_extracted_facts} extracted facts is confirmed or corrected yet; only reviewed facts count.`
      : 'This sprint has no extracted facts yet: process its documents, then review the facts.';
  }
  return `${reviewed} reviewed fact(s) exist, but open gap penalties bring every factor to 0.`;
}

/** Why coverage is 0 / unavailable, or '' when there is coverage to show. */
export function coverageReason(c: EvidenceCoverage | null): string {
  if (!c) return 'Coverage was not calculated for this score (it was made before coverage existed). Recalculate the CRI.';
  if (c.ratio == null) return 'No AI-QIF indicator is applicable, so coverage cannot be calculated.';
  if (c.covered_count > 0) return '';
  if (c.mappings_awaiting_review > 0) {
    return `No indicator is covered yet: ${c.mappings_awaiting_review} AI-QIF tag(s) on confirmed facts are waiting for a reviewer (the AI-QIF expert) to decide them.`;
  }
  return 'No indicator is covered: no confirmed or corrected AI-evidence fact carries an accepted AI-QIF tag. Context and profile facts never cover an indicator.';
}

/** Why the Coverage-Adjusted CRI is what it is (0, missing, or partly reduced). */
export function adjustedReason(s: Scorecard): string {
  const c = hasCoverage(s.evidence_coverage) ? s.evidence_coverage : null;
  if (s.coverage_adjusted_cri == null) return coverageReason(c) || 'Not calculated for this score. Recalculate the CRI.';
  if (s.coverage_adjusted_cri === 0) {
    if (s.raw_cri === 0) return `0 because the Raw CRI is 0. ${rawCriZeroReason(s)}`;
    return `0 because evidence coverage is 0%. ${coverageReason(c)}`;
  }
  if (c && c.ratio != null && c.ratio < 1) {
    return `Raw CRI ${s.raw_cri} reduced to ${Math.round(c.ratio * 100)}% because only ${c.covered_count} of ${c.applicable_count} applicable indicators are covered.`;
  }
  return '';
}

/** A factor's score in words, for the breakdown. */
export function factorNote(p: PillarScore): string {
  if (p.evidence_count === 0) return 'No confirmed or corrected fact backs this factor yet.';
  const gaps = p.gap_count ? ` · ${p.gap_count} open gap(s) deducted` : '';
  return `${p.evidence_count} reviewed fact(s)${gaps}`;
}

/** The sum the Raw CRI is built from, to show it adds up (backend rounds each factor and the total). */
export function weightedTotal(pillars: PillarScore[]): number {
  return Math.round(pillars.reduce((sum, p) => sum + p.weighted_score, 0) * 100) / 100;
}

/** "Academic year 2026-27 · 1 Jul 2026 to 31 Mar 2027" from the sprint's own fields; '' when none set. */
export function reportingPeriod(s: { academic_year?: string; start_date?: string | null; target_completion_date?: string | null }): string {
  const parts: string[] = [];
  if (s.academic_year) parts.push(`Academic year ${s.academic_year}`);
  if (s.start_date || s.target_completion_date) parts.push(`${s.start_date || '?'} to ${s.target_completion_date || '?'}`);
  return parts.join(' · ');
}
