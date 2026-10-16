import type { Gap } from './gaps';
import type { Scorecard } from './scoring';

export type BaselineStatus = 'pending' | 'approved' | 'provisional' | 'returned';

export interface BaselineDecision {
  id: string;
  action: 'submitted' | 'approved' | 'approved_provisional' | 'returned';
  user: string | null;
  user_name: string;
  comments: string;
  created_at: string;
}

export interface Baseline {
  id: string;
  sprint_id: string;
  scoring_run_id: string;
  status: BaselineStatus;
  overall_cri: number;
  overall_confidence: number;
  calculation_version: string;
  /** Pillar scores of the run this baseline is pinned to (frozen). */
  pillar_snapshot: { pillar: string; label: string; raw_score: number; status: string }[];
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
  score: Scorecard | null;
  high_priority_gaps: Gap[];
  can_approve: boolean;
}
