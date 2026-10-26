import type { Gap } from './gaps';
import type { Scorecard } from './scoring';

export type BaselineStatus = 'pending' | 'approved' | 'provisional' | 'returned';

export interface BaselineDecision {
  id: string;
  /** refreshed: a pending baseline's preview moved to a calculation of the current data. */
  action: 'submitted' | 'approved' | 'approved_provisional' | 'returned' | 'refreshed';
  user: string | null;
  user_name: string;
  comments: string;
  created_at: string;
}

export interface Baseline {
  id: string;
  sprint_id: string;
  /** The calculation this baseline previews (pending) or was decided on; approval must name it. */
  scoring_run_id: string;
  scoring_run_calculated_at: string;
  status: BaselineStatus;
  /** Set on a revision: the decided baseline it may replace (that decision stays unchanged). */
  revises: string | null;
  overall_cri: number;
  overall_confidence: number;
  calculation_version: string;
  /** Pillar scores of the run this baseline is pinned to (frozen). */
  pillar_snapshot: { pillar: string; label: string; raw_score: number; status: string }[];
  /** Frozen with the run; null / {} for runs made before coverage existed. */
  coverage_adjusted_cri: number | null;
  evidence_coverage: import('./scoring').EvidenceCoverage | Record<string, never>;
  /** Processing when the decision was made; processing_incomplete = decided over incomplete processing. */
  processing_snapshot?: { complete?: boolean; description?: string; counts?: Record<string, number> };
  processing_incomplete?: boolean;
  processing_override_reason?: string;
  approved_by: string | null;
  approved_by_name: string;
  approved_at: string | null;
  comments: string;
  created_at: string;
  updated_at: string;
  history: BaselineDecision[];
}

export interface SprintBaseline {
  baseline: Baseline;
  /** Live document processing (deciding is refused while incomplete, unless a reason is given). */
  processing?: import('./extraction').ProcessingSummary;
  score: Scorecard | null;
  high_priority_gaps: Gap[];
  can_approve: boolean;
  /** Every decision-cycle of the sprint, newest first, each with its own history (the latest = `baseline`). */
  cycles?: Baseline[];
  /** Pending: the preview was just recalculated because the sprint data changed. */
  refreshed?: boolean;
  /** Pending: true. Decided: false once the Live CRI has moved on since the decision. */
  baseline_is_current?: boolean;
}

/** 409 from approve: nothing was decided; the baseline now previews a newer calculation to review. */
export interface BaselineChangedResponse extends SprintBaseline {
  detail: string;
  code: 'baseline_changed';
}
