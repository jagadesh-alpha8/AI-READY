import type { Gap } from './gaps';

export type PillarStatus = 'not_started' | 'at_risk' | 'developing' | 'strong';

export interface PillarScore {
  pillar: string;
  label: string;
  weight: number;
  raw_score: number;
  weighted_score: number;
  confidence_score: number;
  score: number;
  confidence: number;
  status: PillarStatus;
  evidence_count: number;
  gap_count: number;
  calculation_version: string;
  calculated_at: string | null;
}

export interface PillarSummary {
  pillar: string;
  label: string;
  raw_score: number;
  status: PillarStatus;
}

/** One AI-QIF indicator's row in a run's evidence coverage. */
export interface CoverageIndicator {
  code: string;
  criterion: string;
  name: string;
  applicability: 'applies' | 'optional' | 'requires_review' | 'does_not_apply';
  applicability_reason: string;
  applicable: boolean;
  weight: number;
  covered: boolean;
  fact_ids: string[];
}

/** AI-QIF evidence coverage frozen on a ScoringRun (formula AIQIF-COV-1). */
export interface EvidenceCoverage {
  formula_version: string;
  formula: string;
  status: 'complete' | 'incomplete' | 'no_applicable_indicators';
  ratio: number | null;
  covered_count: number;
  applicable_count: number;
  excluded_count: number;
  unresolved_applicability_count: number;
  covered_weight: number;
  applicable_weight: number;
  weights_source: 'release' | 'equal_within_criterion';
  weights_note: string;
  release_label: string | null;
  release_hash: string | null;
  applicability_note: string;
  mappings_awaiting_review: number;
  /** Items wait for the AI-QIF expert (Super Admin): the coverage may still change; no baseline until empty. */
  provisional?: boolean;
  expert_queue?: { tags: number; facts: number; total: number };
  indicators: CoverageIndicator[];
}

export interface Scorecard {
  sprint_id: string;
  overall_cri: number;
  /** Same as overall_cri: the CRI before coverage. */
  raw_cri: number;
  /** Raw CRI x coverage of the latest run; null when not calculated (older run) or no applicable weight. */
  coverage_adjusted_cri: number | null;
  /** {} when the latest run was made before coverage existed. */
  evidence_coverage: EvidenceCoverage | Record<string, never>;
  overall_confidence: number;
  cri_score: number;
  cri_confidence: number;
  calculation_version: string;
  calculated_at: string | null;
  pillar_scores: PillarScore[];
  strengths: PillarSummary[];
  weaknesses: PillarSummary[];
  evidence_metrics: {
    confirmed_facts: number;
    corrected_facts: number;
    total_extracted_facts: number;
    documents_processed: number;
    unresolved_gaps: number;
  };
  unresolved_blocking_gaps: Gap[];
}
