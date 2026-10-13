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
  /** Router that ran the latest attempt, e.g. "router2 (localhost:20229)"; "" in single-router mode. */
  ai_router: string;
  created_at: string;
  updated_at: string;
  /** AI tokens and cost of this job (all attempts); cost is null when the model has no price. */
  ai_input_tokens: number;
  ai_output_tokens: number;
  ai_cost_usd: string | null;
}

export interface AIUsageTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  /** Exact decimal string, sum of priced calls only. */
  cost_usd: string;
}

export interface SprintAIUsage extends AIUsageTotals {
  sprint_id: string;
  first_call: string | null;
  last_call: string | null;
  unpriced_calls: number;
  unpriced_models: string[];
  /** Requests whose figures came from a dashboard import / an estimate, not exact recording. */
  imported_calls: number;
  estimated_calls: number;
  /** Where imported/estimated figures came from. */
  notes: string[];
  documents: number;
  by_stage: (AIUsageTotals & { stage: string })[];
  by_model: (AIUsageTotals & { model: string })[];
  top_documents: (AIUsageTotals & { document_id: string; filename: string })[];
}

export interface AIUsageBillingRow {
  institution_id: string | null;
  institution: string;
  sprint_id: string | null;
  sprint: string;
  /** "2026-10" */
  month: string;
  documents: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  unpriced_calls: number;
  imported_calls: number;
  estimated_calls: number;
}

export interface PlatformAIUsage extends AIUsageTotals {
  first_call: string | null;
  last_call: string | null;
  unpriced_calls: number;
  unpriced_models: string[];
  /** Requests whose figures came from a dashboard import / an estimate, not exact recording. */
  imported_calls: number;
  estimated_calls: number;
  /** Where imported/estimated figures came from. */
  notes: string[];
  documents: number;
  by_stage: (AIUsageTotals & { stage: string })[];
  by_model: (AIUsageTotals & { model: string })[];
  rows: AIUsageBillingRow[];
}
