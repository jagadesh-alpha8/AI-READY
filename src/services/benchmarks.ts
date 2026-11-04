import { http } from './http';
import type { ApplicabilityPreview, CataloguePillar, SourceDocument, SourceLibrarySummary } from '../types/api';

/** The benchmark library: InGage staff only, reads included (backend apps/benchmarks/permissions.py). */
export const listSources = (params: { q?: string; category?: string } = {}) =>
  http.get<SourceDocument[]>('/benchmarks/sources', { params });
export const getSourceSummary = () => http.get<SourceLibrarySummary>('/benchmarks/sources/summary');
export const listPillars = () => http.get<CataloguePillar[]>('/benchmarks/pillars');
/** Every indicator's applicability for a college, from its saved benchmark profile only. */
export const previewApplicability = (institutionId: string) =>
  http.get<ApplicabilityPreview>('/benchmarks/applicability/preview', { params: { institution: institutionId } });
