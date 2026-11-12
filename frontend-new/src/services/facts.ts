import { http } from './http';
import type { Fact, FactDetail, FactFacets, Page } from '../types/api';
import type {
  AIQIFExpertQueue, AIQIFSummary, BulkConfirmResult, CorrectionProposal, FactVerificationDetail, ProfileSuggestion,
  ProfileValues, ReviewAction, ReviewBatch, VerificationSummary,
} from '../types/workflow';
import { cleanParams } from '../utils/params';

export interface FactQuery {
  page?: number;
  page_size?: number;
  q?: string;
  status?: string;
  pillar?: string;
  ordering?: string;
  verification_status?: string;
  aiqif_mapping_status?: string;
}

export const listSprintFactsPage = (sprintId: string, query: FactQuery = {}) =>
  http.get<Page<Fact>>(`/sprints/${sprintId}/facts`, { params: cleanParams({ page: 1, ...query }) });
export const getSprintFactFacets = (sprintId: string) => http.get<FactFacets>(`/sprints/${sprintId}/facts/facets`);
/** One fact in full, with its review history. */
export const getFact = (id: string) => http.get<FactDetail>(`/facts/${id}`);

// --- decisions ---
export const confirmFact = (id: string, reason: string) => http.post<Fact>(`/facts/${id}/confirm`, { reason });
export const rejectFact = (id: string, reason: string) => http.post<Fact>(`/facts/${id}/reject`, { reason });
export const correctFact = (id: string, newValue: unknown, reason: string) =>
  http.post<Fact>(`/facts/${id}/correct`, { new_value: newValue, reason });
/** Creates an evidence request behind the fact ("evidence insufficient"). */
export const requestFactEvidence = (id: string, evidenceNeeded: string, reason: string, assignedTo?: string | null, dueDate?: string | null) =>
  http.post<Fact>(`/facts/${id}/request-evidence`, { evidence_needed: evidenceNeeded, reason, assigned_to: assignedTo || undefined, due_date: dueDate || undefined });
/** Confirm up to 100 facts at once; per-fact ownership checks and history still apply. */
export const bulkConfirmFacts = (sprintId: string, factIds: string[], comment: string, onlyVerified = true) =>
  http.post<BulkConfirmResult>(`/sprints/${sprintId}/facts/bulk-confirm`, { fact_ids: factIds, comment, only_verified: onlyVerified });
/** Coordinators assign (or unassign with null) a fact to someone who may act on it. */
export const assignFact = (id: string, assignedTo: string | null, dueDate?: string | null, note = '') =>
  http.post<Fact>(`/facts/${id}/assign`, { assigned_to: assignedTo, due_date: dueDate || null, note });

// --- verification ---
export const getFactVerification = (id: string) => http.get<FactVerificationDetail>(`/facts/${id}/verification`);
export const getVerificationSummary = (sprintId: string) => http.get<VerificationSummary>(`/sprints/${sprintId}/verification/summary`);
export const getShadowReport = (sprintId: string) => http.get<Record<string, unknown>>(`/sprints/${sprintId}/verification/shadow-report`);
export const reverifySprint = (sprintId: string) =>
  http.post<{ checked: number; outcomes: Record<string, number>; mode: string }>(`/sprints/${sprintId}/verification/reverify`, {});

// --- correction proposals (a proposed value waits for a different reviewer) ---
export const listFactCorrections = (id: string) => http.get<CorrectionProposal[]>(`/facts/${id}/corrections`);
export const proposeCorrection = (id: string, body: { value: unknown; reason: string; source_document_id: string | null; source_page: string; source_snippet: string }) =>
  http.post<CorrectionProposal>(`/facts/${id}/corrections`, body);
export const listSprintCorrections = (sprintId: string, status = 'pending') =>
  http.get<CorrectionProposal[]>(`/sprints/${sprintId}/fact-corrections`, { params: cleanParams({ status }) });
export const decideCorrection = (id: string, decision: 'approve' | 'reject' | 'withdraw', reason = '') =>
  http.post<CorrectionProposal>(`/fact-corrections/${id}/${decision}`, { reason });

// --- AI-QIF indicator tags ---
/** A reviewer confirms or rejects one AI tag (counts toward evidence coverage at the next recalculation). */
export const reviewFactMapping = (id: string, indicatorCode: string, decision: 'confirm' | 'reject', note = '') =>
  http.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/review`, { decision, note });
export const addFactMapping = (id: string, indicatorCode: string, relationship: 'direct' | 'supporting' | 'contextual', note = '') =>
  http.post<Fact>(`/facts/${id}/aiqif-mappings`, { indicator_code: indicatorCode, relationship, note });
export const editFactMapping = (id: string, indicatorCode: string, body: { indicator_code?: string; relationship?: string; note?: string; decision?: 'confirm' | 'reject' }) =>
  http.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/edit`, body);
export const reopenFactMapping = (id: string, indicatorCode: string, reason: string) =>
  http.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/reopen`, { reason });
export const decideFactKind = (id: string, factKind: 'ai_evidence' | 'context' | 'profile', note = '') =>
  http.post<Fact>(`/facts/${id}/fact-kind`, { fact_kind: factKind, note });
export const getAIQIFSummary = (sprintId: string) => http.get<AIQIFSummary>(`/sprints/${sprintId}/aiqif-summary`);
/** Super Admin: facts and tags waiting for the AI-QIF expert. */
export const getAIQIFExpertQueue = (sprintId: string) => http.get<AIQIFExpertQueue>(`/sprints/${sprintId}/aiqif-expert-queue`);
export const autoCheckAIQIFQueue = (sprintId: string) =>
  http.post<{ precedent_decisions: number; ai_check: string; expert_queue: { tags: number; facts: number; total: number } }>(
    `/sprints/${sprintId}/aiqif-expert-queue/auto-check`);

// --- benchmark profile read from the documents (InGage staff confirm it) ---
export const getProfileSuggestion = (sprintId: string) => http.get<ProfileSuggestion>(`/sprints/${sprintId}/profile-suggestion`);
export const confirmProfileSuggestion = (sprintId: string, values: ProfileValues) =>
  http.post<ProfileSuggestion>(`/sprints/${sprintId}/profile-suggestion`, values);

// --- guided review: at most 25 prioritised questions (no work on GET) ---
export const getReviewBatch = (sprintId: string) => http.get<ReviewBatch>(`/sprints/${sprintId}/review-batch`);
/** Starts the initial batch (verifies the extracted facts first); `followUp` adds optional extra questions. */
export const startReviewBatch = (sprintId: string, followUp = false) =>
  http.post<ReviewBatch>(`/sprints/${sprintId}/review-batch`, followUp ? { optional_follow_up: true } : {});
export const decideReviewCase = (sprintId: string, caseId: string, body: {
  action: ReviewAction; fact_id?: string; value?: unknown; reason?: string; source_institution?: string; optional_follow_up?: boolean;
}) => http.post<ReviewBatch>(`/sprints/${sprintId}/review-batch/${caseId}`, body);
