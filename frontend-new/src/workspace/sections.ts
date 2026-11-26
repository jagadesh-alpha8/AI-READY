import { DEMO_MODE } from '../config/env';
import type { PageKey } from '../utils/access';

/**
 * The seven sections of Harsha's workspace design (the design preview's modules, titles and tabs), each tab one of
 * the existing screens. `internal`: a tab for InGage staff and reviews, left out of a college's (demo-mode) menu.
 */
export interface Tab { page: PageKey; label: string; internal?: boolean }
export interface Section { key: string; icon: string; label: string; eyebrow: string; title: string; text: string; tabs: Tab[]; staff?: boolean }

export const SECTIONS: Section[] = [
  { key: 'overview', icon: 'grid', label: 'Overview', eyebrow: 'Campus workspace', title: 'Your AI readiness',
    text: 'Where you stand, what you do well, and what to do next.', tabs: [{ page: 'overview', label: 'Overview' }] },
  { key: 'institution', icon: 'building', label: 'Institution', eyebrow: 'Foundation', title: 'Institution workspace',
    text: 'One institutional profile, a shared scope and the right people.',
    tabs: [{ page: 'profile', label: 'Profile' }, { page: 'sprint', label: 'Assessment setup', internal: true },
      { page: 'team', label: 'People & roles' }, { page: 'guide', label: 'Setup checklist', internal: true }] },
  { key: 'evidence', icon: 'folder', label: 'Evidence', eyebrow: 'Your documents', title: 'Your evidence workspace',
    text: 'Send your documents, check what we read from them, and settle anything that disagrees.',
    tabs: [{ page: 'uploads', label: 'Documents' }, { page: 'processing', label: 'Import & processing' },
      { page: 'requests', label: 'Requests' }, { page: 'review', label: 'Facts to check' },
      { page: 'gaps', label: 'Conflicts & gaps' }, { page: 'evidence', label: 'Evidence catalogue' },
      { page: 'verification', label: 'Verification', internal: true }, { page: 'aiqif', label: 'AI-QIF mapping', internal: true },
      { page: 'copilot', label: 'Search' }] },
  { key: 'assessment', icon: 'assessment', label: 'Assessment', eyebrow: 'AI readiness assessment', title: 'Understand your current standing',
    text: 'Run the assessment on your documents, then answer the follow-up questions to complete your result.',
    tabs: [{ page: 'assessment', label: 'Assessment' }, { page: 'questionnaire', label: 'Follow-up questions' },
      { page: 'baseline', label: 'Baseline approval', internal: true }] },
  { key: 'results', icon: 'chart', label: 'Results', eyebrow: 'Your result', title: 'Where you stand, and what to do next.',
    text: 'Your readiness level, your strongest areas, and where to focus.',
    tabs: [{ page: 'cri', label: 'Summary' }, { page: 'areas', label: 'Readiness areas' }, { page: 'reports', label: 'Reports' },
      { page: 'actions', label: 'Recommended actions' }, { page: 'benchmark', label: 'Benchmark comparison', internal: true },
      { page: 'compliance', label: 'Compliance', internal: true }] },
  { key: 'transformation', icon: 'route', label: 'Transformation', eyebrow: 'Campus transformation', title: 'Turn your result into progress',
    text: 'Where the next level is, the pace that suits you, and the plan to get there.',
    tabs: [{ page: 'pathway', label: 'Your pathway' }, { page: 'plan', label: 'Choose a pace' }, { page: 'goals', label: 'Goals & tasks', internal: true },
      { page: 'plancompare', label: 'Check your own plan' }] },
  { key: 'admin', icon: 'settings', label: 'Administration', eyebrow: 'InGage workspace', title: 'Platform administration', staff: true,
    text: 'Manage institutions, the benchmark library and assessment standards.',
    tabs: [{ page: 'institutions', label: 'Institutions' }, { page: 'onboarding', label: 'New institution' },
      { page: 'benchmarkstudio', label: 'Benchmark Studio' }, { page: 'assessmentsetup', label: 'Assessment standards' },
      { page: 'admin', label: 'Platform settings' }, { page: 'apistatus', label: 'System status', internal: true }] },
  { key: 'help', icon: 'help', label: 'Help & guidance', eyebrow: 'Support', title: 'Help & guidance',
    text: 'How the assessment works and who to ask.', tabs: [{ page: 'help', label: 'Help' }] },
];

export const visibleTabs = (section: Section) => section.tabs.filter((t) => !(DEMO_MODE && t.internal));

export function sectionOf(page: PageKey): Section {
  return SECTIONS.find((s) => s.tabs.some((t) => t.page === page)) ?? SECTIONS[0];
}

/** The five steps of the design's progress bar, and the sections that belong to each. */
export const JOURNEY_STEPS: { key: string; label: string }[] = [
  { key: 'institution', label: 'Institution' }, { key: 'evidence', label: 'Evidence' }, { key: 'assessment', label: 'Assessment' },
  { key: 'results', label: 'Results' }, { key: 'transformation', label: 'Transformation' },
];
