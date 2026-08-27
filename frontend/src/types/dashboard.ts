export interface DashboardSprint {
  id: string;
  institution: string;
  name: string;
  status: string;
  completion: number;
  cri: number | null;
  confidence: number | null;
  pending_gaps: number;
  report_status: string | null;
  updated_at: string;
}

export interface DashboardData {
  active_sprints: number;
  completion_percentage: number;
  reports_ready: number;
  pending_confirmations: number;
  high_priority_gaps: number;
  sprint_count: number;
  institution_count: number;
  sprints: DashboardSprint[] | { count: number; next: string | null; previous: string | null; results: DashboardSprint[] };
}
