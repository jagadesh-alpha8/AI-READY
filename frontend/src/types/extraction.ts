export type ExtractionJobStatus = 'pending' | 'running' | 'retrying' | 'completed' | 'failed' | 'cancelled';

export const ACTIVE_EXTRACTION_STATUSES: ExtractionJobStatus[] = ['pending', 'running', 'retrying'];

export interface ExtractionJob {
  id: string;
  sprint_id: string;
  document_id: string;
  document_filename: string;
  status: ExtractionJobStatus;
  current_step: string;
  current_step_label: string;
  progress_percentage: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
}
