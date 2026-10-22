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

/** Where a fact's AI-QIF category tags stand. 'pending' = extracted before tagging existed. */
export type AIQIFMappingStatus = 'pending' | 'mapped' | 'needs_review' | 'unmapped';

/** One AI-QIF key indicator a fact is evidence for -- a category tag, not a
 * score or maturity level (the Raw CRI scores `Fact.pillar`, not these; reviewer-confirmed
 * tags count toward AI-QIF evidence coverage). */
export interface AIQIFMapping {
  criterion: string;          // 'aiqif_c4'
  criterion_code: string;     // 'AIQIF-C4'
  criterion_name: string;
  indicator_code: string;     // 'AIQIF-C4.1'
  indicator_name: string;
  reason: string;
  confidence: number;
  status: 'mapped' | 'needs_review';
  /** A person's decision. Only `confirmed` tags on confirmed/corrected facts count toward AI-QIF evidence coverage. */
  review_status: 'unreviewed' | 'confirmed' | 'rejected';
  reviewed_by: string | null;
  reviewed_by_name: string;
  reviewed_at: string | null;
  review_note: string;
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
  aiqif_mapping_status: AIQIFMappingStatus;
  aiqif_mappings: AIQIFMapping[];
  /** The fact's unresolved evidence request, or null. */
  open_evidence_request: import('./evidenceRequests').OpenEvidenceRequest | null;
  /** Confirmed by the system (AI confidence above the auto-confirm threshold), not by a person. */
  auto_confirmed?: boolean;
  /** Responsibility (backend apps/facts/ownership.py): the owner role in words, the assigned person and by when. */
  owner_role_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  assigned_at: string | null;
  due_date: string | null;
  /** Whether the current user may confirm / correct / reject it; when not, who may. The server decides. */
  can_act: boolean | null;
  act_blocked_reason: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  review_history?: FactReviewHistoryEntry[];
}
