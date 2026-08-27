export type RecommendationPriority = 'blocking' | 'high' | 'medium' | 'optional';
export type RecommendationStatus = 'draft' | 'accepted' | 'edited' | 'hidden' | 'completed';

export interface Recommendation {
  id: string;
  sprint_id: string;
  title: string;
  description: string;
  trigger_gap: string;
  source_gap: string | null;
  supporting_facts: unknown[];
  pillar: string;
  pillar_label: string;
  owner_role: string;
  priority: RecommendationPriority;
  timeline: string;
  expected_cri_lift: number;
  support_offering: string;
  consultant_notes: string;
  status: RecommendationStatus;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  recommendation_text: string;
  edited_text: string;
  expected_score_lift: number;
}

export interface UpdateRecommendationPayload {
  title?: string;
  description?: string;
  priority?: RecommendationPriority;
  timeline?: string;
  expected_cri_lift?: number;
  support_offering?: string;
  consultant_notes?: string;
  status?: RecommendationStatus;
}
