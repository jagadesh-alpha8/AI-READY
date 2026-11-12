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
    { key: 'onboarding', icon: '◎', label: 'Institution onboarding' },
    { key: 'profile', icon: '▦', label: 'Institution profile' },
    { key: 'guide', icon: '☰', label: 'Setup guide' },
  ] },
  { label: 'Audit sprint', items: [
    { key: 'sprint', icon: '◷', label: 'Sprint setup' },
    { key: 'requests', icon: '↗', label: 'Data requests' },
    { key: 'uploads', icon: '⇧', label: 'Upload & processing' },
    { key: 'evidence', icon: '◇', label: 'Evidence intelligence' },
    { key: 'review', icon: '✓', label: 'Evidence review' },
    { key: 'processing', icon: '⟳', label: 'Processing control' },
    { key: 'verification', icon: '☑', label: 'Verification & corrections' },
    { key: 'aiqif', icon: '⌗', label: 'AI-QIF tagging' },
  ] },
  { label: 'Readiness', items: [
    { key: 'assessment', icon: '◉', label: 'AI readiness assessment' },
    { key: 'benchmark', icon: '≋', label: 'Benchmark comparison' },
    { key: 'gaps', icon: '△', label: 'Gap analysis' },
    { key: 'cri', icon: '◌', label: 'CRI & maturity standing' },
    { key: 'baseline', icon: '⚑', label: 'Baseline approval' },
    { key: 'depth', icon: '⊕', label: 'Depth follow-up' },
  ] },
  { label: 'Transformation', items: [
    { key: 'pathway', icon: '⇢', label: 'Level pathway' },
    { key: 'plan', icon: '▤', label: 'Transformation plan' },
    { key: 'goals', icon: '◆', label: 'Goals & tasks' },
    { key: 'progress', icon: '↗', label: 'Progress & reassessment' },
    { key: 'actions', icon: '➜', label: 'Recommended actions' },
    { key: 'plancompare', icon: '⇄', label: 'Plan comparison' },
  ] },
  { label: 'Outputs', items: [
    { key: 'reports', icon: '▧', label: 'Reports & exports' },
    { key: 'copilot', icon: '✦', label: 'AI advisor' },
    { key: 'compliance', icon: '⌘', label: 'Compliance mapping' },
  ] },
  { label: 'Manage', items: [
    { key: 'team', icon: '◍', label: 'People & roles' },
    { key: 'notifications', icon: '◔', label: 'Notifications' },
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
  assessment: ['Readiness', 'AI readiness assessment', 'Compare verified evidence with the versioned capability rubric and calculate the current standing.'],
  benchmark: ['Readiness', 'Benchmark comparison', 'Compare the institution with mandatory requirements, good practice and AI-readiness targets.'],
  gaps: ['Readiness', 'Gap analysis', 'Understand what is missing, why it matters and what prevents movement to the next level.'],
  cri: ['Readiness', 'CRI and maturity standing', 'Explain the score, evidence confidence, outcomes and current Silver, Gold or Platinum eligibility.'],
  pathway: ['Transformation', 'Silver to Platinum pathway', 'See the complete progression route, stage requirements and estimated achievement periods.'],
  plan: ['Transformation', 'Choose a transformation pace', 'Select an immediate, progressive or gradual route based on ambition, capacity and investment.'],
  goals: ['Execution', 'Goals and tasks', 'Turn the approved transformation plan into owned, time-bound work with closure evidence.'],
  progress: ['Execution', 'Progress and reassessment', 'Track delivery, verify outcomes and reassess readiness when stage requirements are complete.'],
  reports: ['Outputs', 'Reports and exports', 'Present the audit, score, evidence, gaps and transformation roadmap in customer-ready formats.'],
  copilot: ['Guidance', 'AI readiness advisor', "Ask grounded questions about evidence, scores, gaps and the institution's approved plan."],
  compliance: ['Governance', 'Compliance mapping', 'Trace each benchmark to NAAC, UGC, AICTE, NBA, DGT and other relevant sources.'],
  team: ['Administration', 'People and roles', 'Manage customer, assessor, reviewer, owner and leadership access.'],
  notifications: ['Administration', 'Notifications and reminders', 'Control request reminders, overdue alerts, approvals and milestone messages.'],
  benchmarkstudio: ['Benchmark governance', 'Benchmark Studio', 'Read the catalogue, requirements, sources, releases, watcher and candidates (changes go through the workbook import).'],
  admin: ['Administration', 'Platform settings', 'Configure organisations, security, integrations, terminology and audit controls.'],
  help: ['Support', 'Help and support', 'Get assistance with onboarding, evidence, assessment and transformation delivery.'],
  guide: ['Getting started', 'Setup guide', 'Follow the steps from institution set-up to reports; each step reads its state from the real records.'],
  processing: ['Audit sprint', 'Processing control', 'Import from Google Drive, watch processing, keep the search index current and see what the AI work cost.'],
  verification: ['Evidence intelligence', 'Verification and corrections', 'See what the rules verified, answer the guided review questions and decide proposed corrections.'],
  aiqif: ['Evidence intelligence', 'AI-QIF tagging', 'Confirm which AI-QIF indicators each fact supports, and settle the expert queue.'],
  baseline: ['Readiness', 'Baseline approval', 'Approve, provisionally approve or return the baseline score that the transformation is measured from.'],
  depth: ['Readiness', 'Depth of evidence follow-up', 'Follow-up questions that tell a short workshop from an accredited programme, after the provisional assessment.'],
  actions: ['Transformation', 'Recommended actions', 'Grounded advice for the latest assessment, with an owner, feasibility and status for every action.'],
  plancompare: ['Transformation', 'Plan comparison', "Compare the institution's own written plan with what the assessment found, and see what to change."],
  apistatus: ['Review', 'Backend status', 'Which screens are fully live, which show sample data waiting for an API, and which wait for a backend decision.'],
  institutions: ['Administration', 'Institutions', 'Manage colleges, their coordinators, departments, systems and leaders, and archive or delete them.'],
  assessmentsetup: ['Benchmark governance', 'Assessment setup', 'Plan templates, benchmark score weights and the college profiles that decide which benchmarks apply.'],
};

export const pathOf = (key: PageKey) => (key === 'overview' ? '/' : `/${key}`);

/** Journey step a page belongs to (prototype renderJourney.pageStep); management pages sit on the last step. */
export const PAGE_STEP: Partial<Record<PageKey, number>> = {
  overview: 0, onboarding: 0, profile: 0, sprint: 0, requests: 1, uploads: 1, evidence: 2, review: 2,
  assessment: 3, benchmark: 3, gaps: 3, cri: 3, pathway: 4, plan: 4, goals: 4, progress: 5, reports: 5, copilot: 5, compliance: 5,
  guide: 0, processing: 1, verification: 2, aiqif: 2, baseline: 3, depth: 3, actions: 4, plancompare: 4,
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
      return 'review';
    case 'scoring':
    case 'baseline_pending':
      return 'cri';
    case 'baseline_approved':
    case 'report_ready':
      return 'plan';
    default:
      return 'progress';
  }
}
