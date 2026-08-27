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

export interface Scorecard {
  sprint_id: string;
  overall_cri: number;
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
