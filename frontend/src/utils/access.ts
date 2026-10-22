/**
 * Who can see which menu and use which action -- the ONE place this is decided.
 *
 * The action rules mirror the server (apps/accounts/permissions.py and the
 * views that use it); the server stays the authority and refuses anything
 * this file lets through by mistake. This file only stops the UI from
 * offering what a role cannot do: a hidden menu, a hidden button, and a
 * "No access" page for a typed-in address.
 *
 * To change who sees what, edit MENU_ROLES / ACTION_ROLES below -- the
 * sidebar, the route guard and every page read from here.
 */
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types/auth';

type Roles = readonly UserRole[] | 'all';

const STAFF = ['super_admin', 'consultant'] as const;                       // InGage's own people
const SPRINT_MANAGERS = [...STAFF, 'institution_admin'] as const;            // MANAGE_SPRINT_ROLES
const ALL_EXCEPT_VIEWER: UserRole[] = [
  'super_admin', 'consultant', 'institution_admin', 'iqac_coordinator', 'registrar', 'hod', 'hr_officer',
  'lab_admin', 'placement_officer', 'faculty',
];                                                                           // REVIEW_ROLES
const QUALITY_LEADS = [...SPRINT_MANAGERS, 'iqac_coordinator'] as const;     // MANAGE_RECOMMENDATION_ROLES

/** Actions, each matching a server permission. */
export const ACTION_ROLES = {
  /** Create a sprint, calculate the CRI, approve/return the baseline, generate reports (CanManageSprint). */
  'sprint.manage': SPRINT_MANAGERS,
  /** Upload documents, import from Drive, start/stop AI processing, confirm a document's category
   * (server: anyone but a viewer -- CanContribute). */
  'documents.contribute': ALL_EXCEPT_VIEWER,
  /** Delete someone else's document (DOCUMENT_MANAGE_ROLES); anyone but a viewer may delete their own. */
  'documents.manageAll': QUALITY_LEADS,
  /** Confirm / correct / reject facts (CanReviewFacts). */
  'facts.review': ALL_EXCEPT_VIEWER,
  /** Resolve / skip gaps (CanResolveGaps). Which ones a role may settle is decided per item by the
   * server (apps/facts/ownership.py) and sent as each fact's / gap's `can_act`. */
  'gaps.resolve': ALL_EXCEPT_VIEWER,
  /** Assign facts and gaps to people, and see every task of the sprint (ownership.COORDINATOR_ROLES). */
  'work.assign': QUALITY_LEADS,
  /** Generate recommendations (CanManageRecommendations). */
  'recommendations.generate': QUALITY_LEADS,
  /** Edit, accept or hide a recommendation (CanEditRecommendation). */
  'recommendations.edit': STAFF,
  /** Create a college or edit its Institution DNA (WRITE_INSTITUTION_ROLES). */
  'institution.edit': SPRINT_MANAGERS,
  /** Delete a college (DELETE_INSTITUTION_ROLES); creating one is 'institution.edit'. */
  'institution.delete': STAFF,
  /** Manage user accounts (USER_ADMIN_ROLES; institution admins only for their own college). */
  'users.manage': ['super_admin', 'institution_admin'],
  /** AI usage and billing (IsSuperAdmin | IsConsultant). */
  'ai.usage': STAFF,
  /** The benchmark library (IsInGageStaff). */
  'benchmarks.studio': STAFF,
} as const satisfies Record<string, Roles>;

export type Action = keyof typeof ACTION_ROLES;

/**
 * Menus. A key is a sidebar entry (and its route). Read-only pages are open to
 * every role; working screens are hidden from the viewer (trustee board), who
 * sees results, not the work in progress.
 */
export const MENU_ROLES = {
  dashboard: 'all',
  'institution-dna': 'all',
  // AI Readiness Audit steps
  'sprint-setup': SPRINT_MANAGERS,
  'sprint-upload': ALL_EXCEPT_VIEWER,
  'sprint-monitor': ALL_EXCEPT_VIEWER,
  'sprint-facts': ALL_EXCEPT_VIEWER,
  'sprint-gaps': ALL_EXCEPT_VIEWER,
  // College staff confirm the facts assigned to their role; a super admin has none.
  'sprint-confirmation': ALL_EXCEPT_VIEWER.filter((r) => r !== 'super_admin'),
  'sprint-score': 'all',
  'sprint-approval': QUALITY_LEADS,
  'sprint-recommendations': 'all',
  'sprint-report': 'all',
  // Modules
  'evidence-intelligence': ALL_EXCEPT_VIEWER,
  // Evidence asked for behind facts: the assignee's task list and the reviewer's decisions.
  'evidence-requests': ALL_EXCEPT_VIEWER,
  'cri-benchmark-intelligence': 'all',
  'benchmark-studio': STAFF,
  'benchmark-assessment': 'all',
  'transformation-plan': 'all',
  'goals-tasks': ALL_EXCEPT_VIEWER,
  'ai-copilot': 'all',
  reminders: ALL_EXCEPT_VIEWER,
  'compliance-mapping': [...QUALITY_LEADS, 'registrar'],
  'uat-readiness': SPRINT_MANAGERS,
  'admin-settings': 'all', // everyone has "My account"; the other tabs are per role
} as const satisfies Record<string, Roles>;

export type MenuKey = keyof typeof MENU_ROLES;

/** Settings tabs (the rubric is read-only for everyone who sees it). */
export const SETTINGS_TAB_ROLES = {
  rubric: QUALITY_LEADS,
  account: 'all',
  users: ACTION_ROLES['users.manage'],
  usage: ACTION_ROLES['ai.usage'],
} as const satisfies Record<string, Roles>;

function allowed(roles: Roles, role: UserRole | undefined): boolean {
  if (!role) return false;
  return roles === 'all' || (roles as readonly string[]).includes(role);
}

export function canDo(role: UserRole | undefined, action: Action): boolean {
  return allowed(ACTION_ROLES[action], role);
}

export function canSeeMenu(role: UserRole | undefined, key: MenuKey): boolean {
  return allowed(MENU_ROLES[key], role);
}

export function canSeeSettingsTab(role: UserRole | undefined, tab: keyof typeof SETTINGS_TAB_ROLES): boolean {
  return allowed(SETTINGS_TAB_ROLES[tab], role);
}

/** The AI Readiness Audit steps, in order. Numbered per role from the ones it can see. */
export const AUDIT_STEPS: MenuKey[] = [
  'sprint-setup', 'sprint-upload', 'sprint-monitor', 'sprint-facts', 'sprint-gaps', 'sprint-confirmation',
  'sprint-score', 'sprint-approval', 'sprint-recommendations', 'sprint-report',
];

/** 1-based position of `key` among the audit steps this role can see (null if hidden). */
export function stepNumber(role: UserRole | undefined, key: MenuKey): number | null {
  const visible = AUDIT_STEPS.filter((k) => canSeeMenu(role, k));
  const i = visible.indexOf(key);
  return i === -1 ? null : i + 1;
}

/** The current user's checks, for pages: `const { can } = useAccess(); can('facts.review')`. */
export function useAccess() {
  const { user } = useAuth();
  const role = user?.role;
  return {
    role,
    userId: user?.id,
    can: (action: Action) => canDo(role, action),
    canSee: (key: MenuKey) => canSeeMenu(role, key),
    step: (key: MenuKey) => stepNumber(role, key),
  };
}
