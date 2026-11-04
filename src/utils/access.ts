/**
 * Who sees which screen and action in this frontend.
 *
 * Copied, not imported, from frontend/src/utils/access.ts (MENU_ROLES / ACTION_ROLES) so this app stays
 * isolated; keep the two in step when a rule changes. The server stays the authority and refuses anything
 * this file lets through by mistake: this only stops the UI offering what a role cannot do.
 */
import type { UserRole } from '../types/api';

type Roles = readonly UserRole[] | 'all';

const STAFF = ['super_admin', 'consultant'] as const;
const ALL_ROLES: readonly UserRole[] = ['super_admin', 'consultant', 'iqac_coordinator'];

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Super Admin',
  consultant: 'InGage Consultant',
  iqac_coordinator: 'IQAC Coordinator',
};

export const roleLabel = (role: string | null | undefined): string =>
  (role && ROLE_LABELS[role as UserRole]) || (role || '').replace(/_/g, ' ');

/** Same keys and roles as the existing frontend's ACTION_ROLES. */
export const ACTION_ROLES = {
  'sprint.manage': ALL_ROLES,
  'documents.contribute': ALL_ROLES,
  'facts.review': ALL_ROLES,
  'gaps.resolve': ALL_ROLES,
  'recommendations.generate': ALL_ROLES,
  'institution.edit': ALL_ROLES,
  'institution.create': STAFF,
  'users.manage': ['super_admin', 'iqac_coordinator'],
  'ai.usage': STAFF,
  'benchmarks.studio': STAFF,
  /** Creating assessment cycles and generating the improvement plan (apps/assessments: staff). */
  'assessments.manage': STAFF,
} as const satisfies Record<string, Roles>;

export type Action = keyof typeof ACTION_ROLES;

/**
 * Screens of the Maturity Roadmap, each tied to the existing menu rule it corresponds to
 * (comment = the existing MENU_ROLES key).
 */
export const PAGE_ROLES = {
  overview: 'all', // dashboard
  onboarding: 'all', // institution-dna (+ sprint-setup actions)
  profile: 'all', // institution-dna
  sprint: ALL_ROLES, // sprint-setup
  requests: ALL_ROLES, // evidence-requests
  uploads: ALL_ROLES, // sprint-upload / sprint-monitor
  evidence: ALL_ROLES, // evidence-intelligence
  review: ALL_ROLES, // sprint-facts
  assessment: 'all', // sprint-score
  benchmark: 'all', // benchmark-assessment
  gaps: ALL_ROLES, // sprint-gaps
  cri: 'all', // cri-benchmark-intelligence / sprint-score
  pathway: 'all', // benchmark-assessment
  plan: 'all', // transformation-plan
  goals: ALL_ROLES, // goals-tasks
  progress: 'all', // sprint-score
  reports: 'all', // sprint-report
  copilot: 'all', // ai-copilot
  compliance: ALL_ROLES, // compliance-mapping
  team: 'all', // admin-settings (role matrix for all; user list for users.manage)
  notifications: ALL_ROLES, // reminders
  benchmarkstudio: STAFF, // benchmark-studio
  admin: 'all', // admin-settings
  help: 'all',
} as const satisfies Record<string, Roles>;

export type PageKey = keyof typeof PAGE_ROLES;

function allowed(roles: Roles, role: UserRole | undefined): boolean {
  if (!role) return false;
  return roles === 'all' || (roles as readonly string[]).includes(role);
}

export const canDo = (role: UserRole | undefined, action: Action) => allowed(ACTION_ROLES[action], role);
export const canSeePage = (role: UserRole | undefined, page: PageKey) => allowed(PAGE_ROLES[page], role);
export const isStaff = (role: UserRole | undefined) => !!role && (STAFF as readonly string[]).includes(role);
