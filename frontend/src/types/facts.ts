export type FactStatus = 'extracted' | 'confirmed' | 'corrected' | 'rejected' | 'evidence_requested';

export interface FactReviewHistoryEntry {
  id: string;
  action: string;
  original_value: unknown;
  new_value: unknown;
  user: string | null;
  user_name: string;
  reason: string;
  /** Who decided: 'person' (or '' on older rows), 'rule' (verification rules) or 'precedent'. */
  decision_source?: '' | 'person' | 'rule' | 'precedent';
  /** The verification behind an automatic decision, the precedent it reused, a proposal id, overrides_auto. */
  details?: Record<string, unknown>;
  created_at: string;
}

export type VerificationStatus = 'verified' | 'needs_review' | 'invalid' | 'conflicting';

/** The latest verification of a fact (backend apps/facts/verification/): four results kept apart. */
export interface FactVerificationSummary {
  status: VerificationStatus;
  status_label: string;
  /** The model's own estimate that it read the value correctly -- never a confirmation. */
  extraction_confidence: number | null;
  /** Citation + quote check (deterministic): exact, ocr_variant, not_found, unavailable, page_missing, ... */
  grounding: string;
  /** Deterministic checks: pass, warn, fail, not_applicable. */
  validation: string;
  /** Comparable sources: agrees, disagrees, in_open_conflict, not_comparable, no_other_source. */
  cross_source: string;
  risk_level: '' | 'low' | 'medium' | 'high';
  /** auto_verified, precedent, would_auto_verify, would_precedent, review, not_applicable. */
  automation_decision: string;
  automation_reason: string;
  verified_at: string | null;
}

export interface VerificationCheck {
  code: string;
  label: string;
  status: 'pass' | 'fail' | 'warn';
  detail: string;
  kind: 'deterministic';
  formula?: string;
  inputs?: DerivationInput[];
}

export interface DerivationInput {
  label: string;
  value: string;
  number: string | null;
  document_id: string | null;
  document_name?: string | null;
  document_version: number | null;
  source_page: string;
  source_snippet: string;
  grounding: { status: string; quote: string; value_support: string; detail: string[] };
}

/** One full verification run (GET /facts/<id>/verification). */
export interface FactVerificationRun {
  id: string;
  source: string;
  mode: 'shadow' | 'enforce';
  outcome: VerificationStatus;
  reason: string;
  value: unknown;
  citation: { document_name: string | null; document_version: number | null; source_page: string; source_snippet: string };
  extraction_confidence: number | null;
  grounding: { status: string; citation: string; quote: string; value_support: string; score: number | null;
    detail: string[]; quote_numbers: string[]; kind: 'deterministic' };
  validation: { status: string; checks: VerificationCheck[]; kind: 'deterministic' };
  derivation: { status?: string; formula?: string; computed?: string | null; stated?: string | null;
    inputs?: DerivationInput[]; includes?: string[]; excludes?: string[]; detail?: string[] };
  cross_source: { status: string; compared: { fact_id: string; value: unknown; document: string | null;
    document_version: number | null; page: string; period: string | null; agrees: boolean }[];
    not_comparable: { fact_id: string; value: unknown; document: string | null; why: string }[] };
  scope: { period: string; population: string[]; unit: string; includes: string[]; excludes: string[] };
  /** The number checked against the cited page text (backend verification/numeric.py). */
  numeric?: { status: string; source_text: string; parsed: string | null; unit: string; unit_source: string;
    pages: number[]; page_shows?: string; detail: string; kind: 'deterministic' };
  ai_assessments: { label: string; detail: string }[];
  risk_level: string;
  precedent: { match: 'exact' | 'partial' | 'rejected'; action: string; value: unknown; decided_by_name: string;
    decided_at: string | null; document_version: number | null; source_page: string; differences: string[] } | null;
  automation_decision: string;
  automation_reason: string;
  blockers: string[];
  created_at: string;
}

export interface PendingCorrection {
  id: string;
  proposed_value: unknown;
  reason: string;
  source_page: string;
  submitted_by: string | null;
  submitted_by_name: string;
  verification_outcome: VerificationStatus | null;
  /** The current user proposed it (so may withdraw, never approve). */
  mine: boolean;
  created_at: string;
}

export interface CorrectionProposal {
  id: string;
  fact: string;
  field_name: string;
  value_before: unknown;
  proposed_value: unknown;
  reason: string;
  source_document: string | null;
  source_document_name: string | null;
  source_page: string;
  source_snippet: string;
  verification: { outcome?: VerificationStatus; reason?: string };
  status: 'pending' | 'approved' | 'rejected' | 'withdrawn' | 'stale';
  submitted_by_name: string;
  reviewed_by_name: string;
  review_reason: string;
  created_at: string;
  can_decide: boolean;
}

/** Where a fact's AI-QIF category tags stand. 'pending' = not classified yet; 'context' / 'profile' = not AI
 * evidence, so no indicator to review (backend apps/facts/aiqif_tagging.py). */
export type AIQIFMappingStatus = 'pending' | 'mapped' | 'needs_review' | 'unmapped' | 'context' | 'profile';

/** What a fact is for: only AI evidence can cover an AI-QIF indicator. '' = not classified yet. */
export type FactKind = 'ai_evidence' | 'context' | 'profile' | '';

/** One AI-QIF key indicator a fact is evidence for -- a category tag, not a
 * score or maturity level (the Raw CRI scores `Fact.pillar`, not these; reviewer-confirmed
 * tags count toward AI-QIF evidence coverage). */
export interface AIQIFMapping {
  id: string;
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
  /** How the fact supports the indicator; Contextual never counts toward coverage. */
  relationship: 'direct' | 'supporting' | 'contextual';
  /** crosswalk = the approved NAAC -> AI-QIF crosswalk; ai = an AI suggestion; expert = added by a Super Admin. */
  source: 'crosswalk' | 'ai' | 'expert';
  /** Accepted by the rules without a person (a rejection still wins). */
  auto_accepted: boolean;
  framework_version: string;
  /** Counts toward AI-QIF coverage right now (backend aiqif_tagging.counting_q), and why or why not. */
  counts: boolean;
  counts_reason: string;
  /** Waiting for an expert decision (in the sprint's AI-QIF expert queue). */
  pending: boolean;
  /** Set when a Super Admin reopened the review or edited the mapping without deciding it. */
  pending_since: string | null;
  pending_by_name: string;
  pending_reason: string;
  /** How the rules decided it without a person: accepted_rules / accepted_crosswalk / accepted_precedent /
   * accepted_ai_check / rejected_precedent, or '' (backend aiqif_tagging.py rule 4). */
  auto_decision: string;
  /** Why, in words -- e.g. the earlier expert decision, or what the AI second opinion said. */
  auto_reason: string;
}

export interface Fact {
  id: string;
  sprint_id: string;
  document_id: string | null;
  field_name: string;
  field_key: string;
  audit_field_id: string;
  value: unknown;
  /** The value exactly as the extractor returned it ('' on older facts). */
  value_text?: string;
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
  fact_kind: FactKind;
  /** The NAAC metric the fact reports ("2.1.2"), only when it is printed in the text it came from. */
  naac_metric: string;
  profile_field: string;
  profile_code: string;
  /** Waiting for a Super Admin decision (the AI-QIF expert queue). */
  kind_needs_check: boolean;
  kind_reviewed_at: string | null;
  tagging_notes: { kind: string; detail: string }[];
  /** The fact's unresolved evidence request, or null. */
  open_evidence_request: import('./evidenceRequests').OpenEvidenceRequest | null;
  /** Confirmed by the system (AI confidence above the auto-confirm threshold), not by a person. */
  auto_confirmed?: boolean;
  /** The gaps whose "Upload Evidence" supplied this fact's document (the original gap). */
  evidence_for_gaps?: { id: string; title: string; gap_type: string; status: string }[];
  /** Responsibility (backend apps/facts/ownership.py): the owner role in words, the assigned person and by when. */
  owner_role_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  assigned_at: string | null;
  due_date: string | null;
  /** Whether the current user may confirm / correct / reject it; when not, who may. The server decides. */
  can_act: boolean | null;
  act_blocked_reason: string;
  /** How the value came to be, and the value + citation as first recorded (never overwritten). */
  value_origin?: '' | 'extracted' | 'calculated' | 'submitted' | 'corrected';
  original_value?: unknown;
  original_source_page?: string;
  original_source_snippet?: string;
  derivation?: Record<string, unknown>;
  /** The latest verification, or null when never verified. */
  verification?: FactVerificationSummary | null;
  pending_correction?: PendingCorrection | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  review_history?: FactReviewHistoryEntry[];
}
