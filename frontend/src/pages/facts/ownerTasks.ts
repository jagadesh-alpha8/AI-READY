/**
 * The Owner Workspace's task list, as pure functions (`npm test` runs them on Node directly).
 *
 * A task is a fact still waiting for a review (extracted, or evidence requested) or a gap still open.
 * Who may act on each is decided by the server (backend apps/facts/ownership.py) and sent as `can_act`;
 * these functions only decide what to *show*: "My tasks" (assigned to me, or unassigned and owned by my
 * role) versus "All sprint tasks" (coordinators), and the eligible assignees for a task.
 */
import type { Fact } from '../../types/facts.ts';
import type { Gap } from '../../types/gaps.ts';

export const PENDING_FACT_STATUSES = ['extracted', 'evidence_requested'];
export const ACTIVE_GAP_STATUSES = ['open', 'in_progress', 'needs_replacement'];
/** Act on every item of their college (backend ownership.OVERRIDE_ROLES). */
export const OVERRIDE_ROLES = ['super_admin', 'consultant', 'institution_admin'];
/** Assign work and see every task (backend ownership.COORDINATOR_ROLES). */
export const COORDINATOR_ROLES = [...OVERRIDE_ROLES, 'iqac_coordinator'];

export interface OwnerTask {
  key: string;
  kind: 'fact' | 'gap';
  id: string;
  /** The role responsible, normalised ('' = coordinators). */
  ownerRole: string;
  ownerLabel: string;
  assignedTo: string | null;
  assignedName: string;
  dueDate: string | null;
  overdue: boolean;
  status: string;
  canAct: boolean | null;
  blockedReason: string;
  fact?: Fact;
  gap?: Gap;
}

const ROLES = ['super_admin', 'consultant', 'institution_admin', 'iqac_coordinator', 'registrar', 'hod',
  'hr_officer', 'lab_admin', 'placement_officer', 'faculty'];

/** The login role a stored owner role names ('HOD' -> 'hod'); '' when it is none. */
export function normalizeRole(value: string | null | undefined): string {
  const slug = (value || '').trim().toLowerCase();
  return ROLES.includes(slug) ? slug : '';
}

export function isOverdue(dueDate: string | null, today = new Date().toISOString().slice(0, 10)): boolean {
  return !!dueDate && dueDate < today;
}

export function buildTasks(facts: Fact[], gaps: Gap[], today?: string): OwnerTask[] {
  const fromFacts = facts.filter((f) => PENDING_FACT_STATUSES.includes(f.status)).map((f): OwnerTask => ({
    key: `fact:${f.id}`, kind: 'fact', id: f.id, ownerRole: normalizeRole(f.owner_role), ownerLabel: f.owner_role_label,
    assignedTo: f.assigned_to, assignedName: f.assigned_to_name, dueDate: f.due_date,
    overdue: isOverdue(f.due_date, today), status: f.status, canAct: f.can_act, blockedReason: f.act_blocked_reason,
    fact: f,
  }));
  // A fact's own "needs confirmation" gap is the same work as the fact (confirming it closes the gap),
  // so it is listed once, as the fact.
  const pendingFactIds = new Set(fromFacts.map((t) => t.id));
  const sameWork = (g: Gap) => g.gap_type === 'unconfirmed_fact' && g.status !== 'needs_replacement'
    && !!g.source_fact_id && pendingFactIds.has(g.source_fact_id);
  const fromGaps = gaps.filter((g) => ACTIVE_GAP_STATUSES.includes(g.status) && !sameWork(g)).map((g): OwnerTask => ({
    key: `gap:${g.id}`, kind: 'gap', id: g.id, ownerRole: normalizeRole(g.owner_role), ownerLabel: g.owner_role_label,
    assignedTo: g.assigned_to, assignedName: g.assigned_to_name, dueDate: g.due_date,
    overdue: isOverdue(g.due_date, today), status: g.status, canAct: g.can_act, blockedReason: g.act_blocked_reason,
    gap: g,
  }));
  // Overdue first, then dated, then the rest.
  return [...fromFacts, ...fromGaps].sort((a, b) => Number(b.overdue) - Number(a.overdue)
    || (a.dueDate || '9999').localeCompare(b.dueDate || '9999'));
}

/** "My tasks": assigned to me -- or nobody's yet and owned by my role, so unassigned work stays visible. */
export function isMine(task: OwnerTask, user: { id: string; role: string }): boolean {
  if (task.assignedTo) return task.assignedTo === user.id;
  if (task.ownerRole) return task.ownerRole === user.role;
  return COORDINATOR_ROLES.includes(user.role); // no owner role: the coordinators'
}

export function isCoordinator(role: string | undefined): boolean {
  return !!role && COORDINATOR_ROLES.includes(role);
}

/** Users a coordinator can assign this task to: its owner role, or an Institution Admin (as the server). */
export function eligibleAssignees<U extends { role: string }>(task: OwnerTask, users: U[]): U[] {
  const roles = ['institution_admin', task.ownerRole || 'iqac_coordinator'];
  return users.filter((u) => roles.includes(u.role));
}

export interface TaskFilters {
  role?: string;
  unassignedOnly?: boolean;
  overdueOnly?: boolean;
}

export function filterTasks(tasks: OwnerTask[], f: TaskFilters): OwnerTask[] {
  return tasks.filter((t) => (f.role === undefined || f.role === 'all' || t.ownerRole === f.role)
    && (!f.unassignedOnly || !t.assignedTo) && (!f.overdueOnly || t.overdue));
}
