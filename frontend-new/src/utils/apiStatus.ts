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

/**
 * Open items after Siddharth's answers of 12 Nov 2026. Closed and removed from the UI: R-02, R-03 (renamed "Evidence
 * search"), R-06, R-08, R-09 (samples removed), D-03 (only the foundation plan's own routes), D-04.
 */
export const PENDING: Record<string, string> = {
  'R-01': 'Investment appetite and constraints: later, if the plan evaluator uses budget constraints',
  'R-04': 'Progression timeline: exists only after a recommendation (recommendations are being reworked)',
  'R-05': 'Saving the chosen route and sponsor approval: later (waits for the recommendations rework)',
  'R-07': 'Roadmap PDF and board presentation: later (build on recommendations and the plan)',
  'R-10': 'Second layer: answering works; starting question generation, the depth judgment and the depth report are still to build',
  'R-11': 'Benchmark Studio stays read-only for now (Harsha to confirm)',
  'R-12': 'How each score was reached (found and credited, where we looked, next step): coming with the report step',
  'D-01': 'Silver / Gold / Platinum tiers: rubric not calibrated; waiting for Harsha to check with Vijay',
  'D-02': 'Level pathway: rename to a requirements pathway or fold into the report, after D-01',
};

const p = (...codes: string[]): Pending[] => codes.map((code) => ({ code, text: PENDING[code] }));

/** Every screen's status. A screen with nothing pending is live. */
export const PAGE_API_STATUS: Record<PageKey, { status: ApiStatus; pending: Pending[] }> = {
  overview: { status: 'decision', pending: p('D-01') },
  guide: { status: 'live', pending: [] },
  onboarding: { status: 'live', pending: [] },
  profile: { status: 'partial', pending: p('R-01') },
  sprint: { status: 'live', pending: [] },
  requests: { status: 'live', pending: [] },
  uploads: { status: 'live', pending: [] },
  processing: { status: 'live', pending: [] },
  evidence: { status: 'live', pending: [] },
  review: { status: 'live', pending: [] },
  verification: { status: 'live', pending: [] },
  aiqif: { status: 'live', pending: [] },
  copilot: { status: 'live', pending: [] },
  assessment: { status: 'partial', pending: p('R-12') },
  questionnaire: { status: 'partial', pending: p('R-10') },
  baseline: { status: 'live', pending: [] },
  reports: { status: 'partial', pending: p('R-07') },
  cri: { status: 'decision', pending: p('D-01', 'R-12') },
  benchmark: { status: 'decision', pending: p('D-01') },
  gaps: { status: 'partial', pending: p('D-01') },
  pathway: { status: 'decision', pending: p('D-02', 'D-01', 'R-04') },
  actions: { status: 'live', pending: [] },
  plan: { status: 'partial', pending: p('R-05') },
  plancompare: { status: 'live', pending: [] },
  goals: { status: 'live', pending: [] },
  compliance: { status: 'live', pending: [] },
  team: { status: 'live', pending: [] },
  benchmarkstudio: { status: 'partial', pending: p('R-11') },
  institutions: { status: 'live', pending: [] },
  assessmentsetup: { status: 'live', pending: [] },
  admin: { status: 'live', pending: [] },
  help: { status: 'live', pending: [] },
  apistatus: { status: 'live', pending: [] },
};
