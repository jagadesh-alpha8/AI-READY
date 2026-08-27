export type GapType = 'missing_document' | 'unconfirmed_fact' | 'conflict' | 'stale_data' | 'low_confidence';
export type GapPriority = 'blocking' | 'high' | 'medium' | 'optional';
export type GapStatus = 'open' | 'in_progress' | 'resolved' | 'unavailable' | 'skipped';

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
  owner_role: string;
  status: GapStatus;
  resolution: string;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}
