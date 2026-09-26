import api from './client';

export interface PillarCriterionConfig {
  key: string;
  name: string;
  description: string;
  weight: number;
  fact_field_keys: string[];
  is_active: boolean;
}

export interface PillarConfig {
  key: string;
  name: string;
  description: string;
  weight: number;
  display_order: number;
  is_active: boolean;
  criteria: PillarCriterionConfig[];
}

/**
 * The live scoring rubric — every pillar and criterion, with the weights the
 * engine is actually using. Database-backed, not a hardcoded snapshot, which
 * is what makes it worth showing an administrator at all.
 */
export function getScoringConfig() {
  return api.get<PillarConfig[]>('/scoring/config');
}
