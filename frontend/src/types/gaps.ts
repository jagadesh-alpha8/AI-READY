export type GapType = 'missing_document' | 'unconfirmed_fact' | 'conflict' | 'stale_data' | 'low_confidence';
export type GapPriority = 'blocking' | 'high' | 'medium' | 'optional';
export type GapStatus = 'open' | 'in_progress' | 'resolved' | 'unavailable' | 'skipped' | 'needs_replacement';

/** Statuses of a gap that is still open work (backend GapItem.ACTIVE_STATUSES). */
export const ACTIVE_GAP_STATUSES: GapStatus[] = ['open', 'in_progress', 'needs_replacement'];

export interface Gap {
  id: string;
  sprint_id: string;
  gap_type: GapType;
  title: string;
  description: string;
  pillar: string;
  pillar_label: string;
  priority: GapPriority;
  audit_field_id: string;
  score_impact: number;
  source_fact_id: string | null;
  related_document_id: string | null;
  source_document_filename: string;
  owner_role: string;
  status: GapStatus;
  resolution: string;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  /** The linked fact's review status ('' when the gap has no fact). */
  fact_status: string;
  /** The linked fact's most recent evidence request (open or decided), with its actual assignee. */
  evidence_request: GapEvidenceRequest | null;
  /** Why Resolve is refused right now ('' = allowed); only ever set for low-confidence gaps. */
  resolve_blocked_reason: string;
  /** Why Skip / Mark unavailable are refused right now ('' = allowed). */
  close_blocked_reason: string;
  /** Conflict gaps only: how sure the conflict check was that the values genuinely disagree. */
  conflict_confidence: number | null;
  /** Conflict gaps only: side A (source_fact) and side B (conflict_fact_b); null for other gap types. */
  conflict_sides: ConflictSide[] | null;
  /** The linked fact's snippet and page as stored; null when there is no fact or none was recorded. */
  source_snippet: string | null;
  source_page: string | null;
  /** Responsibility (backend apps/facts/ownership.py): owner role in words, assignee and due date. */
  owner_role_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  assigned_at: string | null;
  due_date: string | null;
  /** Whether the current user may resolve / close it; when not, who may. The server decides. */
  can_act: boolean | null;
  act_blocked_reason: string;
  /** Only on GET /gaps/<id>: what happened to it. */
  events?: GapEvent[];
}

/** One side of a conflict, exactly as recorded: null means it was not recorded (never inferred). */
export interface ConflictSide {
  side: 'A' | 'B';
  fact_id: string | null;
  field_name: string;
  /** The value stored when the conflict was found (conflict_value_a / _b). */
  value_at_detection: unknown;
  /** The fact's value now (null when there is no fact on this side). */
  current_value: unknown;
  fact_status: string;
  document_id: string | null;
  document_name: string | null;
  page: string | null;
  snippet: string | null;
  confidence_score: number | null;
}

export interface GapEvidenceRequest {
  id: string;
  status: import('./evidenceRequests').EvidenceRequestStatus;
  status_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  due_date: string | null;
  overdue: boolean;
}

export interface GapEvent {
  id: string;
  action: 'assigned' | 'resolved' | 'unavailable' | 'skipped' | 'auto_resolved' | 'needs_replacement';
  action_label: string;
  user: string | null;
  user_name: string;
  note: string;
  data: Record<string, unknown>;
  created_at: string;
}

/** GET /sprints/<id>/work-summary: outstanding work across the whole sprint. */
export interface WorkSummaryRow {
  role?: string;
  label?: string;
  user_id?: string | null;
  name?: string;
  pending_facts: number;
  evidence_requested: number;
  open_gaps: number;
  conflicts: number;
  needs_replacement: number;
  unassigned: number;
  overdue: number;
  total: number;
}

export interface WorkSummary {
  ready_for_baseline_review: boolean;
  blockers: string[];
  totals: { pending_facts: number; open_gaps: number; fact_gaps: number; blocking_gaps: number; unassigned: number; overdue: number };
  by_role: WorkSummaryRow[];
  by_assignee: WorkSummaryRow[];
}
