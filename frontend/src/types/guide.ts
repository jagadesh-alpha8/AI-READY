export type GuideStepStatus =
  | 'completed'
  | 'in_progress'
  | 'needs_attention'
  | 'skipped'
  | 'not_started';

export type GuideStepId =
  | 'institution_dna'
  | 'sprint_setup'
  | 'upload_documents'
  | 'monitor_processing'
  | 'facts_review'
  | 'gaps_evidence'
  | 'live_cri'
  | 'baseline_approval'
  | 'recommendations'
  | 'transformation_plan'
  | 'reports';

export interface GuideStep {
  id: GuideStepId;
  number: number;
  title: string;
  purpose: string;
  status: GuideStepStatus;
  action_label: string;
  target_path: string;
  tour_target?: string;
  tour_location?: string;
  is_authorized: boolean;
  block_reason: string | null;
  details?: Record<string, any>;
}

export interface GuideStatusResponse {
  current_step_id: GuideStepId | null;
  current_step_number: number | null;
  current_step: GuideStep | null;
  steps: GuideStep[];
  is_dismissed: boolean;
  completed_count: number;
  skipped_count: number;
  total_steps: number;
  sprint_id: string | null;
  institution_id: string | null;
  institution_name: string | null;
  sprint_code: string | null;
  menu_tours?: Record<string, { status: MenuTourStatus; updated_at?: string }>;
}

export type MenuTourStatus = 'completed' | 'dismissed' | 'in_progress' | 'reset';

export interface MenuTourStep {
  id: string;
  number?: number;
  title: string;
  purpose: string;
  tour_target?: string;
  tour_location?: string;
  action_label?: string;
  target_path?: string;
  status?: GuideStepStatus;
  is_authorized?: boolean;
  block_reason?: string | null;
  details?: Record<string, any>;
}

export interface MenuTourConfig {
  menuKey: string;
  menuTitle: string;
  menuPurpose: string;
  roles?: readonly string[] | 'all';
  steps: MenuTourStep[];
}

