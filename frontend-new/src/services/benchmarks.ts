import { http } from './http';
import type { ApplicabilityPreview, CataloguePillar, SourceDocument, SourceLibrarySummary } from '../types/api';
import type {
  BenchmarkCandidate, BenchmarkRelease, CatalogueBenchmark, EvidenceTypeInfo, RequirementRow, WatcherEvent,
} from '../types/workflow';
import { cleanParams } from '../utils/params';

/**
 * The benchmark library (InGage staff only, reads included). The backend keeps it read-only in the portal
 * (BENCHMARK_CATALOGUE_READ_ONLY): every add / edit / delete, AI drafting, watcher, candidate and release action
 * is refused on the server and the catalogue changes only through a controlled workbook import. So this module
 * exposes the reads.
 */
export const listSources = (params: { q?: string; category?: string } = {}) =>
  http.get<SourceDocument[]>('/benchmarks/sources', { params: cleanParams(params) });
export const getSourceSummary = () => http.get<SourceLibrarySummary>('/benchmarks/sources/summary');
export const getSource = (code: string) => http.get<SourceDocument>(`/benchmarks/sources/${code}`);
export const getSourceReference = () => http.get<Record<string, unknown>>('/benchmarks/sources/reference');
export const listVersionCandidates = (versionId: string) => http.get<Record<string, unknown>[]>(`/benchmarks/versions/${versionId}/candidates`);
export const compareVersion = (versionId: string) => http.get<Record<string, unknown>>(`/benchmarks/versions/${versionId}/compare`);

export const listPillars = () => http.get<CataloguePillar[]>('/benchmarks/pillars');
export const listCatalogue = (params: { pillar?: string; kind?: string; q?: string } = {}) =>
  http.get<CatalogueBenchmark[]>('/benchmarks/catalogue', { params: cleanParams(params) });
export const getCatalogueBenchmark = (code: string) => http.get<CatalogueBenchmark>(`/benchmarks/catalogue/${code}`);
export const getBenchmarkReadiness = (code: string) => http.get<Record<string, unknown>>(`/benchmarks/catalogue/${code}/readiness`);
export const getBenchmarkHistory = (code: string) =>
  http.get<{ at: string; actor: string; action: string }[]>(`/benchmarks/catalogue/${code}/history`);
export const getBenchmarkProvenance = (code: string, release?: string) =>
  http.get<Record<string, unknown>>(`/benchmarks/catalogue/${code}/provenance`, { params: cleanParams({ release }) });
export const listBenchmarkRequirements = (code: string) => http.get<RequirementRow[]>(`/benchmarks/catalogue/${code}/requirements`);
export const listBenchmarkEvidenceRules = (code: string) => http.get<Record<string, unknown>[]>(`/benchmarks/catalogue/${code}/evidence-rules`);
export const listBenchmarkApplicabilityRules = (code: string) =>
  http.get<Record<string, unknown>[]>(`/benchmarks/catalogue/${code}/applicability-rules`);
export const getApplicabilityValidation = (code: string) =>
  http.get<Record<string, unknown>>(`/benchmarks/catalogue/${code}/applicability-validation`);
export const listRequirements = (params: { q?: string; source?: string } = {}) =>
  http.get<RequirementRow[]>('/benchmarks/requirements', { params: cleanParams(params) });
export const getRequirementSuggestions = (code: string) => http.get<Record<string, unknown>>(`/benchmarks/requirements/${code}/suggestions`);
export const listEvidenceTypes = () => http.get<EvidenceTypeInfo[]>('/benchmarks/evidence-types');

export const getApplicabilityReference = () => http.get<Record<string, unknown>>('/benchmarks/applicability/reference');
/** Every indicator's applicability for a college, from its saved benchmark profile only. */
export const previewApplicability = (institutionId: string) =>
  http.get<ApplicabilityPreview>('/benchmarks/applicability/preview', { params: { institution: institutionId } });

export const listReleases = () => http.get<BenchmarkRelease[]>('/benchmarks/releases');
/** 404 when nothing has been published yet. */
export const getCurrentRelease = () => http.get<BenchmarkRelease & Record<string, unknown>>('/benchmarks/releases/current');
export const getRelease = (label: string) => http.get<BenchmarkRelease & Record<string, unknown>>(`/benchmarks/releases/${label}`);
export const getReleaseDiff = (label: string) => http.get<Record<string, unknown>>(`/benchmarks/releases/${label}/diff`);

export const getWatcherSummary = () => http.get<Record<string, unknown>>('/benchmarks/watcher/summary');
export const listWatcherFeeds = () => http.get<Record<string, unknown>[]>('/benchmarks/watcher/feeds');
export const listWatcherRuns = () => http.get<Record<string, unknown>[]>('/benchmarks/watcher/runs');
export const listWatcherEvents = () => http.get<WatcherEvent[]>('/benchmarks/watcher/events');
export const listBenchmarkCandidates = (status = 'open') =>
  http.get<BenchmarkCandidate[]>('/benchmarks/benchmark-candidates', { params: { status } });
export const listStudioAIJobs = () => http.get<Record<string, unknown>[]>('/benchmarks/ai-jobs');
