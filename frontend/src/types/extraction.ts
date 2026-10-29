export type ExtractionJobStatus = 'pending' | 'running' | 'retrying' | 'completed' | 'failed' | 'cancelled';

export const ACTIVE_EXTRACTION_STATUSES: ExtractionJobStatus[] = ['pending', 'running', 'retrying'];

export type JobPhase =
  | 'queued' | 'reading_pages' | 'classifying' | 'extracting_facts' | 'finishing' | 'continuing' | 'retrying'
  | 'waiting_for_router' | 'completed' | 'partial' | 'failed' | 'stopped';

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
  /** Every attempt at this job (backend tasks.py): which router, and why it ended -- e.g. out_of_credit when
   * the router's provider ran out of quota and the document moved to the next router. */
  attempts?: { at: string; router: string; outcome: string; detail: string; ended?: string }[];
  /** How much the latest completed attempt read: '' = not recorded (older run). */
  completeness: '' | 'complete' | 'partial';
  extraction_warnings: ExtractionWarning[];
  chunks_total: number;
  chunks_completed: number;
  /** Live reading progress (backend DocumentPage rows); 0 on runs from before it existed. */
  pages_total?: number;
  pages_done?: number;
  ocr_pages?: number;
  unreadable_pages?: number;
  /** A large document finished over several bounded attempts: how many follow-ups this run took. */
  continuations?: number;
  heartbeat_at?: string | null;
  /** When a scheduled retry is due (status retrying). */
  next_retry_at?: string | null;
  /** What it is doing right now (backend services/job_phase.py) and its label, e.g. "Reading pages 12 of 40". */
  phase?: JobPhase;
  phase_label?: string;
  /** 'single' (one AI provider) or 'multi_router'. */
  processing_mode?: string;
  /** Where its AI calls go, without any key: "single provider: api.openai.com, gpt-4o" or "router2 (...), qwen". */
  ai_provider?: string;
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
  /** Distinct documents with recorded usage, including earlier versions and rejected files. */
  documents: number;
  /** Of those, the current documents (not rejected, not superseded) -- the processing summary's rule. */
  current_documents?: number;
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

export interface ExtractionWarning {
  kind: 'chunk_failed' | 'chunks_skipped' | 'unreadable_pages' | 'unsupported_format' | 'no_text' | string;
  detail: string;
  chunk?: number;
  chunks?: number[];
  pages?: string[];
}

export type DocumentProcessingState = 'complete' | 'partial' | 'failed' | 'active' | 'not_processed';

export interface DocumentProcessingRow {
  document_id: string;
  filename: string;
  state: DocumentProcessingState;
  label: string;
  job_id: string | null;
  job_status: string | null;
  /** False for a completion recorded before chunk checks existed. */
  checked: boolean;
  chunks_total: number;
  chunks_completed: number;
  warnings: ExtractionWarning[];
  error: string;
}

/** backend apps/extraction/services/completeness.py */
export interface ProcessingSummary {
  complete: boolean;
  description: string;
  counts: Record<DocumentProcessingState, number> & { total: number };
  documents: DocumentProcessingRow[];
  incomplete: DocumentProcessingRow[];
  /** The sprint's documents that are not current, never part of `counts`. */
  excluded?: { earlier_version: number; rejected: number; total: number };
  excluded_documents?: ExcludedDocumentRow[];
}

export interface ExcludedDocumentRow {
  document_id: string;
  filename: string;
  state: 'earlier_version' | 'rejected';
  /** "Earlier version — replaced by version 2; excluded from current-document counts." */
  label: string;
  version_number: number;
  replaced_by_version: number | null;
}
