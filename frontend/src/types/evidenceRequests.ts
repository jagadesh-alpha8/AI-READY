/** A reviewer's request for evidence behind one fact (backend apps/facts/evidence_requests.py). */
export type EvidenceRequestStatus = 'open' | 'submitted' | 'processing' | 'ready_for_review' | 'returned' | 'accepted' | 'accepted_corrected' | 'withdrawn';

export interface EvidenceRequest {
  id: string;
  sprint: string;
  sprint_code: string;
  sprint_name: string;
  institution_name: string;
  fact: string;
  fact_field_name: string;
  fact_field_key: string;
  fact_value: unknown;
  fact_status: string;
  description: string;
  evidence_needed: string;
  reason: string;
  suggested_owner_role: string;
  responsible_role: string;
  requested_by: string | null;
  requested_by_name: string;
  assigned_to: string | null;
  assigned_to_name: string;
  due_date: string | null;
  overdue: boolean;
  status: EvidenceRequestStatus;
  status_label: string;
  evidence_count: number;
  resolution_note: string;
  resolved_by: string | null;
  resolved_by_name: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceLink {
  id: string;
  document: string | null;
  document_filename: string;
  document_status: string;
  page_count: number | null;
  uploaded_for_request: boolean;
  source_page: string;
  source_snippet: string;
  submitted_text: string;
  source_context: string;
  note: string;
  submitted_by: string | null;
  submitted_by_name: string;
  analysis_status: 'pending' | 'processing' | 'ready' | 'failed';
  analysis_outcome: 'supports' | 'contradicts' | 'does_not_address' | '';
  analysis_summary: string;
  analysis_quote: string;
  analysis_page_number: number | null;
  analysis_document_reference: string;
  analysis_suggested_value: unknown;
  analysis_confidence: number | null;
  /** The latest error (kept while a retry runs, cleared by a success). */
  analysis_error: string;
  /** AI assessment runs started, and reviewer-requested retries of a failed one. */
  analysis_attempts: number;
  analysis_retry_count: number;
  analysis_started_at: string | null;
  analysis_finished_at: string | null;
  analysis_retry_requested_at: string | null;
  status: 'submitted' | 'accepted' | 'returned' | 'rejected';
  review_reason: string;
  reviewed_by: string | null;
  reviewed_by_name: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface EvidenceEvent {
  id: string;
  action: string;
  action_label: string;
  user: string | null;
  user_name: string;
  note: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface SuggestedFact {
  why: string;
  id: string;
  field_name: string;
  field_key: string;
  value: unknown;
  status: string;
  document: string | null;
  source_page: string;
  source_snippet: string;
  confidence_score: number;
}

export interface EvidenceRequestDetail extends EvidenceRequest {
  fact_source_page: string;
  fact_source_snippet: string;
  fact_source_document: string | null;
  evidence: EvidenceLink[];
  events: EvidenceEvent[];
  suggested_facts: SuggestedFact[];
  /** The fact's gaps; an open low-confidence one closes when evidence here is accepted. */
  fact_gaps: { id: string; gap_type: string; gap_type_label: string; title: string; status: string; resolution: string }[];
}

export interface EvidenceAssignee {
  id: string;
  name: string;
  email: string;
  role: string;
}

/** On a fact: its unresolved request, if any. */
export interface OpenEvidenceRequest {
  id: string;
  status: EvidenceRequestStatus;
  status_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  due_date: string | null;
  overdue: boolean;
}
