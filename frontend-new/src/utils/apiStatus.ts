/**
 * How complete each screen is against the A2 backend, for reviewers (Review mode and the Backend status screen).
 * Codes match frontend-new/docs/Backend_API_Requests_A2.pdf: R-xx = an API requested from the backend,
 * D-xx = a backend decision about a concept A2 does not model. Update this file when an item lands.
 */
import type { PageKey } from './access';

export type ApiStatus = 'live' | 'partial' | 'decision';

export interface Pending { code: string; text: string }

export const STATUS_LABEL: Record<ApiStatus, string> = {
  live: 'Live',
  partial: 'Partly sample',
  decision: 'Needs backend decision',
};
export const STATUS_TONE: Record<ApiStatus, 'good' | 'warn' | 'bad'> = { live: 'good', partial: 'warn', decision: 'bad' };
export const STATUS_MARK: Record<ApiStatus, string> = { live: '✓', partial: '◐', decision: '!' };
export const STATUS_MEANING: Record<ApiStatus, string> = {
  live: 'Everything on the screen comes from the backend.',
  partial: 'Works with real data; one part is sample data or a disabled button waiting for a backend API (R-xx).',
  decision: 'Shows a concept the A2 backend does not model; waiting for a backend decision (D-xx).',
};

/** Requests and decisions as listed in the PDF. */
export const PENDING: Record<string, string> = {
  'R-01': 'Investment appetite and constraints: no institution fields',
  'R-02': 'Reminder and escalation records for evidence requests',
  'R-03': 'Written, grounded advisor answers (only evidence search exists)',
  'R-04': 'Progression timeline without a recommendation',
  'R-05': 'Saving the chosen route and sponsor approval',
  'R-06': 'Reassessment schedule, stage gates and outcome measures',
  'R-07': 'Transformation roadmap PDF and board presentation PPTX exports',
  'R-08': 'Notification preferences and scheduled reminders',
  'R-09': 'Organisation, integration, governance and audit settings',
  'R-10': 'HTTP API for the depth follow-up stage',
  'R-11': 'Editing the benchmark catalogue in the portal (read-only today)',
  'D-01': 'Silver / Gold / Platinum tiers (A2 rubric is not calibrated)',
  'D-02': 'Level pathway menu, built on tiers',
  'D-03': 'Immediate / Progressive / Gradual pace',
  'D-04': 'Menu kept only if its API lands',
};

const p = (...codes: string[]): Pending[] => codes.map((code) => ({ code, text: PENDING[code] }));

/** Every screen's status. A screen with nothing pending is live. */
export const PAGE_API_STATUS: Record<PageKey, { status: ApiStatus; pending: Pending[] }> = {
  overview: { status: 'decision', pending: p('D-01', 'D-03') },
  onboarding: { status: 'live', pending: [] },
  profile: { status: 'partial', pending: p('R-01') },
  guide: { status: 'live', pending: [] },
  sprint: { status: 'live', pending: [] },
  requests: { status: 'partial', pending: p('R-02') },
  uploads: { status: 'live', pending: [] },
  evidence: { status: 'live', pending: [] },
  review: { status: 'live', pending: [] },
  processing: { status: 'live', pending: [] },
  verification: { status: 'live', pending: [] },
  aiqif: { status: 'live', pending: [] },
  assessment: { status: 'live', pending: [] },
  benchmark: { status: 'decision', pending: p('D-01') },
  gaps: { status: 'partial', pending: p('D-01') },
  cri: { status: 'decision', pending: p('D-01') },
  baseline: { status: 'live', pending: [] },
  depth: { status: 'partial', pending: p('R-10') },
  pathway: { status: 'decision', pending: p('D-02', 'D-01', 'R-04') },
  plan: { status: 'decision', pending: p('D-03', 'R-05') },
  goals: { status: 'live', pending: [] },
  progress: { status: 'partial', pending: p('R-06', 'D-04') },
  actions: { status: 'live', pending: [] },
  plancompare: { status: 'live', pending: [] },
  reports: { status: 'partial', pending: p('R-07') },
  copilot: { status: 'partial', pending: p('R-03', 'D-04') },
  compliance: { status: 'live', pending: [] },
  team: { status: 'live', pending: [] },
  notifications: { status: 'partial', pending: p('R-08', 'D-04') },
  benchmarkstudio: { status: 'partial', pending: p('R-11') },
  institutions: { status: 'live', pending: [] },
  assessmentsetup: { status: 'live', pending: [] },
  admin: { status: 'partial', pending: p('R-09', 'D-04') },
  help: { status: 'live', pending: [] },
  apistatus: { status: 'live', pending: [] },
};
