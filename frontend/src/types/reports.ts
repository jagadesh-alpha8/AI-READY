export type ReportStatus = 'draft' | 'generating' | 'ready' | 'failed';

export interface ReportActionPlanBucket {
  timeline: string;
  items: { title: string; [key: string]: unknown }[];
}

export interface ReportData {
  institution: { name: string; [key: string]: unknown };
  sprint: { id: string; sprint_code: string; name: string; mode: string; status: string };
  generated_at: string;
  executive_summary: string;
  overall_cri: number;
  /** Reports made since coverage existed: the same as overall_cri, then the adjusted score and coverage. */
  raw_cri?: number;
  coverage_adjusted_cri?: number | null;
  evidence_coverage?: {
    available: boolean;
    summary: string;
    formula_version?: string;
    formula?: string;
    status?: string;
    ratio?: number | null;
    covered_count?: number;
    applicable_count?: number;
    excluded_count?: number;
    unresolved_applicability_count?: number;
    weights_note?: string;
    applicability_note?: string;
  };
  confidence_score: number;
  pillar_scorecards: {
    pillar: string; label: string; weight: number; raw_score: number; weighted_score: number;
    confidence_score: number; status: string; evidence_count: number; gap_count: number;
  }[];
  strengths: { pillar: string; label: string; raw_score: number; status: string }[];
  areas_for_improvement: { pillar: string; label: string; raw_score: number; status: string }[];
  missing_data_appendix: unknown[];
  recommendations: unknown[];
  ninety_day_action_plan: ReportActionPlanBucket[];
  twelve_month_roadmap: ReportActionPlanBucket[];
  how_ingage_can_help: { offering: string; recommendation_count: number; pillars: string[] }[];
  evidence_metrics: Record<string, number>;
  /** Document processing when the report was built (and any baseline approved over incomplete processing). */
  processing?: {
    complete: boolean;
    description: string;
    counts: Record<string, number>;
    incomplete: { document_id: string; filename: string; state: string; label: string }[];
    baseline_override: { reason: string; description: string } | null;
  };
  /** The score this report was built from: a fresh ScoringRun, compared with the approved baseline. */
  cri_source?: {
    scoring_run_id: string;
    calculation_version: string;
    calculated_at: string;
    recalculated: boolean;
    baseline_status: 'approved' | 'provisional' | null;
    baseline_scoring_run_id: string | null;
    baseline_cri: number | null;
    differs_from_baseline: boolean;
    note: string;
  };
}

export interface Report {
  id: string;
  sprint_id: string;
  version: number;
  status: ReportStatus;
  executive_summary: string;
  overall_cri: number;
  confidence_score: number;
  generated_at: string | null;
  generated_by: string | null;
  /** The ScoringRun calculated for this report (its own CRI snapshot). */
  scoring_run_id: string | null;
  pdf_available: boolean;
  docx_available: boolean;
  created_at: string;
  updated_at: string;
  report_data?: ReportData;
}
