export type FactStatus = 'extracted' | 'confirmed' | 'corrected' | 'rejected' | 'evidence_requested';

export interface FactReviewHistoryEntry {
  id: string;
  action: string;
  original_value: unknown;
  new_value: unknown;
  user: string | null;
  user_name: string;
  reason: string;
  created_at: string;
}

export interface Fact {
  id: string;
  sprint_id: string;
  document_id: string | null;
  field_name: string;
  field_key: string;
  audit_field_id: string;
  value: unknown;
  value_json: unknown;
  normalized_value: unknown;
  data_type: string;
  pillar: string;
  pillar_label: string;
  owner_role: string;
  source_document_id: string | null;
  source_document_filename: string;
  source_page: string;
  source_snippet: string;
  confidence_score: number;
  confidence: number;
  confidence_reason: string;
  extraction_method: string;
  status: FactStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  review_history?: FactReviewHistoryEntry[];
}
