export type SprintMode = 'quick_cri' | 'verified_cri' | 'full_digital_twin';

export type SprintStatus =
  | 'draft'
  | 'collecting'
  | 'processing'
  | 'reviewing'
  | 'scoring'
  | 'baseline_pending'
  | 'baseline_approved'
  | 'report_ready'
  | 'completed'
  | 'archived';

export interface Sprint {
  id: string;
  institution_id: string;
  name: string;
  sprint_code: string;
  mode: SprintMode;
  sprint_mode: SprintMode;
  status: SprintStatus;
  academic_year: string;
  description: string;
  start_date: string | null;
  target_completion_date: string | null;
  completion_percentage: number;
  overall_cri: number | null;
  confidence_score: number | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateSprintPayload {
  institution_id: string;
  /** Optional — the backend falls back to Sprint.mode's model default. The
   * setup screen no longer sends it, since the platform runs one method. */
  sprint_mode?: SprintMode;
  academic_year?: string;
  name?: string;
}

export interface SprintOverview {
  sprint: Sprint;
  institution: unknown;
  documents: { total: number; pending: number; uploaded: number; processing: number; processed: number; failed: number; rejected: number; items: unknown[] };
  facts: { total: number; extracted: number; confirmed: number; corrected: number; rejected: number; evidence_requested: number };
  gaps: { total: number; open: number; in_progress: number; resolved: number; blocking_open: number };
  scorecard: unknown | null;
  recommendations: { total: number; accepted: number; draft: number; items: unknown[] };
  reports: { total: number; latest: unknown | null };
  latest_extraction_job: unknown | null;
}
