import type { PageKey } from '../utils/access';

/**
 * The website's sections (merged design of 27 Nov 2026: Harsha's consolidated workspaces holding our result
 * screens). Each tab is one of the existing screens.
 * - `staff`: a tab, or a whole section, for InGage staff only.
 * - `hidden`: a screen that belongs to the section (its heading and menu item) but has no tab, such as the search
 *   that the top bar opens.
 * - `title`/`text`: the heading for that tab, when it differs from the section's.
 * - `beta`: marked Beta on the tab and in the heading.
 */
export interface Tab { page: PageKey; label: string; staff?: boolean; hidden?: boolean; beta?: boolean; title?: string; text?: string }
export interface Section { key: string; icon: string; label: string; eyebrow: string; title: string; text: string; tabs: Tab[]; staff?: boolean }

export const SECTIONS: Section[] = [
  { key: 'overview', icon: 'grid', label: 'Overview', eyebrow: 'Your workspace', title: 'Your AI readiness',
    text: 'Where you stand, and the one thing to do next.', tabs: [{ page: 'overview', label: 'Overview' }] },
  { key: 'institution', icon: 'building', label: 'Institution', eyebrow: 'Your institution', title: 'Your institution',
    text: 'One profile of your institution, and the people taking part.',
    tabs: [{ page: 'profile', label: 'Profile' }, { page: 'team', label: 'People' },
      { page: 'sprint', label: 'Assessment setup', staff: true }, { page: 'guide', label: 'Setup checklist', staff: true }] },
  { key: 'documents', icon: 'folder', label: 'Documents', eyebrow: 'Your documents', title: 'Your documents',
    text: 'Send your documents, check what we read from them, and settle anything that disagrees.',
    tabs: [{ page: 'uploads', label: 'Documents' }, { page: 'requests', label: 'Requests' },
      { page: 'review', label: 'Facts to check' }, { page: 'gaps', label: 'Conflicts and gaps' },
      { page: 'processing', label: 'Processing', staff: true }, { page: 'verification', label: 'Verification', staff: true },
      { page: 'aiqif', label: 'AI-QIF mapping', staff: true }, { page: 'evidence', label: 'Catalogue', staff: true },
      { page: 'copilot', label: 'Search your documents', hidden: true, title: 'Search your documents',
        text: 'Find passages in the documents you sent. Every passage names its document and page.' }] },
  { key: 'assessment', icon: 'assessment', label: 'Assessment', eyebrow: 'Your assessment', title: 'Follow-up questions',
    text: 'Each question asks about something your documents did not show clearly. An answer counts when a document supports it.',
    tabs: [{ page: 'questionnaire', label: 'Follow-up questions' },
      { page: 'answers', label: 'Your answers', title: 'Your answers', text: 'Every follow-up question you have answered, and what came of each answer.' },
      { page: 'assessment', label: 'Run and publish', staff: true, title: 'Run and publish', text: 'Run the assessment, and choose which result the college sees.' },
      { page: 'baseline', label: 'Baseline approval', staff: true }] },
  { key: 'results', icon: 'chart', label: 'Results', eyebrow: 'Your result', title: 'Your nine AI readiness areas',
    text: 'Strongest first. Open an area for its four topics, and a topic for its six practices.',
    tabs: [{ page: 'areas', label: 'Readiness areas' },
      { page: 'reports', label: 'Reports', title: 'Your reports', text: 'The leadership report and the detailed report, as PDF files.' },
      // The old Summary repeated the Overview (merged design, 27 Nov); its address still works.
      { page: 'cri', label: 'Summary', hidden: true }] },
  { key: 'plan', icon: 'route', label: 'Plan', eyebrow: 'Your plan', title: 'Your plan',
    text: 'One step for each area. The three to start with come first.',
    tabs: [{ page: 'actions', label: 'Steps' },
      { page: 'plan', label: 'Choose a pace', text: 'How quickly to move to the next level, and what each pace asks of you.' },
      { page: 'plancompare', label: 'Check your own plan', beta: true, title: 'Check your own plan',
        text: 'Paste your own AI plan: what in it would count, what would not yet, and what we would change. A limited number of checks per assessment.' },
      { page: 'pathway', label: 'Your pathway', hidden: true },
      { page: 'goals', label: 'Goals and tasks', staff: true }] },
  { key: 'benchmarks', icon: 'target', label: 'Benchmarks', eyebrow: 'InGage staff', title: 'Benchmarks', staff: true,
    text: 'How the institution compares, the mapping to regulators, and the benchmark library.',
    tabs: [{ page: 'benchmark', label: 'Benchmark comparison' }, { page: 'compliance', label: 'Compliance' },
      { page: 'benchmarkstudio', label: 'Benchmark Studio' }] },
  { key: 'manage', icon: 'settings', label: 'Manage', eyebrow: 'InGage staff', title: 'Manage the platform', staff: true,
    text: 'Institutions, assessment standards and platform settings.',
    tabs: [{ page: 'institutions', label: 'Institutions' }, { page: 'onboarding', label: 'New institution' },
      { page: 'assessmentsetup', label: 'Assessment standards' }, { page: 'admin', label: 'Platform settings' },
      { page: 'apistatus', label: 'System status' }] },
  { key: 'help', icon: 'help', label: 'Help', eyebrow: 'Support', title: 'Help and guidance',
    text: 'How the assessment works and who to ask.', tabs: [{ page: 'help', label: 'Help' }] },
];

/** The tabs a person sees: staff tabs only for staff, never the hidden ones. */
export const visibleTabs = (section: Section, staff: boolean) => section.tabs.filter((t) => !t.hidden && (staff || !t.staff));

export function sectionOf(page: PageKey): Section {
  return SECTIONS.find((s) => s.tabs.some((t) => t.page === page)) ?? SECTIONS[0];
}

export const tabOf = (page: PageKey) => sectionOf(page).tabs.find((t) => t.page === page);
