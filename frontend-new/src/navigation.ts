import type { PageKey } from './utils/access';

/** Sidebar groups and page headings, as in the handoff prototype (app.js navGroups / pageMeta). */
export interface NavItem {
  key: PageKey;
  icon: string;
  label: string;
}

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  { label: 'Start', items: [
    { key: 'overview', icon: '⌂', label: 'Executive overview' },
    { key: 'guide', icon: '☰', label: 'Setup guide' },
    { key: 'onboarding', icon: '◎', label: 'Institution onboarding' },
    { key: 'profile', icon: '▦', label: 'Institution profile' },
  ] },
  // The product flow agreed 12 Nov 2026: initial evidence -> assessment (provisional score, questionnaire,
  // optional additional evidence) -> report and recommendations.
  { label: '1 · Initial evidence', items: [
    { key: 'sprint', icon: '◷', label: 'Sprint setup' },
    { key: 'requests', icon: '↗', label: 'Data requests' },
    { key: 'uploads', icon: '⇧', label: 'Upload & processing' },
    { key: 'processing', icon: '⟳', label: 'Processing control' },
    { key: 'evidence', icon: '◇', label: 'Evidence intelligence' },
    { key: 'review', icon: '✓', label: 'Evidence review' },
    { key: 'verification', icon: '☑', label: 'Verification & corrections' },
    { key: 'aiqif', icon: '⌗', label: 'AI-QIF tagging' },
    { key: 'copilot', icon: '⌕', label: 'Evidence search' },
  ] },
  { label: '2 · Assessment', items: [
    { key: 'assessment', icon: '◉', label: 'AI readiness assessment' },
    { key: 'questionnaire', icon: '?', label: 'Questionnaire' },
    { key: 'baseline', icon: '⚑', label: 'Baseline approval' },
  ] },
  { label: '3 · Report & recommendations', items: [
    { key: 'reports', icon: '▧', label: 'Reports & exports' },
    { key: 'cri', icon: '◌', label: 'CRI & maturity standing' },
    { key: 'benchmark', icon: '≋', label: 'Benchmark comparison' },
    { key: 'gaps', icon: '△', label: 'Gap analysis' },
    { key: 'pathway', icon: '⇢', label: 'Level pathway' },
    { key: 'actions', icon: '➜', label: 'Recommended actions' },
    { key: 'plan', icon: '▤', label: 'Transformation plan' },
    { key: 'plancompare', icon: '⇄', label: 'Plan comparison' },
    { key: 'goals', icon: '◆', label: 'Goals & tasks' },
    { key: 'compliance', icon: '⌘', label: 'Compliance mapping' },
  ] },
  { label: 'Manage', items: [
    { key: 'team', icon: '◍', label: 'People & roles' },
    { key: 'benchmarkstudio', icon: '▥', label: 'Benchmark Studio' },
    { key: 'institutions', icon: '⌂', label: 'Institutions' },
    { key: 'assessmentsetup', icon: '⚙', label: 'Assessment setup' },
    { key: 'admin', icon: '⚙', label: 'Platform settings' },
    { key: 'apistatus', icon: '◑', label: 'Backend status' },
  ] },
];

export const PAGE_META: Record<PageKey, [eyebrow: string, title: string, text: string]> = {
  overview: ['Leadership view', 'AI readiness at a glance', "See the institution's current standing, urgent decisions and next best actions."],
  onboarding: ['Getting started', 'Institution onboarding', 'Create the customer workspace, confirm scope and assign the people who will participate.'],
  profile: ['Foundation', 'Institution profile', 'Define institution type, regulatory context, programmes and applicability before assessment.'],
  sprint: ['Audit sprint', 'Sprint setup', 'Confirm scope, dates, coordinators, response owners and the evidence collection plan.'],
  requests: ['Audit sprint', 'Data requests', 'Track every requested input, responsible owner, due date and response status.'],
  uploads: ['Audit sprint', 'Upload and processing', 'Submit institutional documents and data for secure extraction and classification.'],
  evidence: ['Evidence intelligence', 'Evidence catalogue', 'See what the platform extracted, where it came from and which requirements it may support.'],
  review: ['Evidence intelligence', 'Evidence review', 'Verify extracted facts, resolve contradictions and approve evidence for assessment.'],
  assessment: ['Assessment', 'AI readiness assessment', 'Compare verified evidence with the versioned capability rubric and calculate the current standing.'],
  benchmark: ['Report', 'Benchmark comparison', 'Compare the institution with mandatory requirements, good practice and AI-readiness targets.'],
  gaps: ['Report', 'Gap analysis', 'Understand what is missing, why it matters and what prevents movement to the next level.'],
  cri: ['Report', 'CRI and maturity standing', 'Explain the score, evidence confidence, outcomes and current Silver, Gold or Platinum eligibility.'],
  pathway: ['Report', 'Silver to Platinum pathway', 'See the complete progression route, stage requirements and estimated achievement periods.'],
  plan: ['Recommendations', 'Choose a transformation pace', 'Select an immediate, progressive or gradual route based on ambition, capacity and investment.'],
  goals: ['Recommendations', 'Goals and tasks', 'Turn the approved transformation plan into owned, time-bound work with closure evidence.'],
  reports: ['Report', 'Reports and exports', 'Present the audit, score, evidence, gaps and transformation roadmap in customer-ready formats.'],
  copilot: ['Initial evidence', 'Evidence search', "Search this institution's own documents; every passage cites its document and page."],
  compliance: ['Report', 'Compliance mapping', 'Trace each benchmark to NAAC, UGC, AICTE, NBA, DGT and other relevant sources.'],
  team: ['Administration', 'People and roles', 'Manage customer, assessor, reviewer, owner and leadership access.'],
  benchmarkstudio: ['Benchmark governance', 'Benchmark Studio', 'Read the catalogue, requirements, sources, releases, watcher and candidates (changes go through the workbook import).'],
  admin: ['Administration', 'Platform settings', 'Configure organisations, security, integrations, terminology and audit controls.'],
  help: ['Support', 'Help and support', 'Get assistance with onboarding, evidence, assessment and transformation delivery.'],
  guide: ['Getting started', 'Setup guide', 'Follow the steps from institution set-up to reports; each step reads its state from the real records.'],
  processing: ['Audit sprint', 'Processing control', 'Import from Google Drive, watch processing, keep the search index current and see what the AI work cost.'],
  verification: ['Evidence intelligence', 'Verification and corrections', 'See what the rules verified, answer the guided review questions and decide proposed corrections.'],
  aiqif: ['Evidence intelligence', 'AI-QIF tagging', 'Confirm which AI-QIF indicators each fact supports, and settle the expert queue.'],
  baseline: ['Assessment', 'Baseline approval', 'Approve, provisionally approve or return the baseline score that the transformation is measured from.'],
  questionnaire: ['Assessment', 'Questionnaire', 'One item at a time: first the review items on the evidence, then, after the provisional score, follow-up questions and any evidence we may have missed.'],
  actions: ['Recommendations', 'Recommended actions', 'Grounded advice for the latest assessment, with an owner, feasibility and status for every action.'],
  plancompare: ['Recommendations', 'Plan comparison', "Compare the institution's own written plan with what the assessment found, and see what to change."],
  apistatus: ['Review', 'Backend status', 'Which screens are fully live, which show sample data waiting for an API, and which wait for a backend decision.'],
  institutions: ['Administration', 'Institutions', 'Manage colleges, their coordinators, departments, systems and leaders, and archive or delete them.'],
  assessmentsetup: ['Benchmark governance', 'Assessment setup', 'Plan templates, benchmark score weights and the college profiles that decide which benchmarks apply.'],
};

export const pathOf = (key: PageKey) => (key === 'overview' ? '/' : `/${key}`);

/** Journey step a page belongs to (prototype renderJourney.pageStep); management pages sit on the last step. */
export const PAGE_STEP: Partial<Record<PageKey, number>> = {
  overview: 0, guide: 0, onboarding: 0, profile: 0,
  sprint: 1, requests: 1, uploads: 1, processing: 1, evidence: 1, review: 1, verification: 1, aiqif: 1, copilot: 1,
  assessment: 2, questionnaire: 2, baseline: 2,
  reports: 3, cri: 3, benchmark: 3, gaps: 3, pathway: 3, actions: 3, plan: 3, plancompare: 3, goals: 3, compliance: 3,
};

/** The next best screen for a sprint in a given pipeline status (the header's primary action). */
export function nextActionFor(status: string | undefined): PageKey {
  switch (status) {
    case undefined:
      return 'onboarding';
    case 'draft':
    case 'collecting':
    case 'processing':
      return 'uploads';
    case 'reviewing':
      return 'questionnaire';
    case 'scoring':
    case 'baseline_pending':
      return 'assessment';
    case 'baseline_approved':
    case 'report_ready':
      return 'reports';
    default:
      return 'cri';
  }
}
