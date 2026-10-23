/**
 * Owner Workspace (`npm test`): which tasks are "mine", who they can be assigned to, and that a card shows
 * the server's "who can act" reason instead of actions it would refuse.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { Fact } from '../../types/facts.ts';
import type { Gap } from '../../types/gaps.ts';
import { buildTasks, eligibleAssignees, filterTasks, isMine, normalizeRole } from './ownerTasks.ts';

const fact = (over: Partial<Fact>): Fact => ({
  id: 'f1', field_name: 'FDP %', field_key: 'fdp', value: 62.5, value_json: 62.5, status: 'extracted', owner_role: 'HOD',
  owner_role_label: 'Head of Department', assigned_to: null, assigned_to_name: '', assigned_at: null, due_date: null,
  can_act: true, act_blocked_reason: '', source_snippet: '120 of 192 completed.', source_page: '45',
  source_document_filename: 'SSR.pdf', confidence: 0.9, pillar: 'aiqif_c4', pillar_label: 'Faculty',
  open_evidence_request: null, ...over,
} as Fact);

const gap = (over: Partial<Gap>): Gap => ({
  id: 'g1', gap_type: 'conflict', title: 'Conflicting values for FDP %', status: 'open', owner_role: 'registrar',
  owner_role_label: 'Registrar', assigned_to: null, assigned_to_name: '', assigned_at: null, due_date: null,
  can_act: true, act_blocked_reason: '', source_fact_id: 'f9', resolve_blocked_reason: '', close_blocked_reason: '',
  conflict_sides: null, source_snippet: null, source_page: null, evidence_request: null, ...over,
} as Gap);

describe('the task list', () => {
  it('holds facts still to review and gaps still open, overdue first', () => {
    const tasks = buildTasks([
      fact({ id: 'a' }), fact({ id: 'done', status: 'confirmed' }), fact({ id: 'b', due_date: '2026-01-01' }),
    ], [gap({ id: 'g' }), gap({ id: 'closed', status: 'resolved' }), gap({ id: 'r', status: 'needs_replacement' })],
    '2026-10-21');
    assert.deepEqual(tasks.map((t) => t.key), ['fact:b', 'fact:a', 'gap:g', 'gap:r']);
    assert.equal(tasks[0].overdue, true);
  });

  it('lists a fact once: its own "needs confirmation" gap is the same work', () => {
    const tasks = buildTasks([fact({ id: 'f1' })], [
      gap({ id: 'u', gap_type: 'unconfirmed_fact', source_fact_id: 'f1' }),
      gap({ id: 'u2', gap_type: 'unconfirmed_fact', source_fact_id: 'f1', status: 'needs_replacement' }),
    ]);
    assert.deepEqual(tasks.map((t) => t.key), ['fact:f1', 'gap:u2']);
  });

  it('normalises owner roles', () => {
    assert.equal(normalizeRole(' HOD '), 'hod');
    assert.equal(normalizeRole('RESEARCH_CELL'), '');
  });
});

describe('My tasks', () => {
  const hod = { id: 'u-hod', role: 'hod' };
  const [mineAssigned, othersAssigned, unassignedMine, unassignedOther, noOwner] = buildTasks([
    fact({ id: '1', assigned_to: 'u-hod' }), fact({ id: '2', assigned_to: 'u-other' }), fact({ id: '3' }),
    fact({ id: '4', owner_role: 'registrar' }), fact({ id: '5', owner_role: '' }),
  ], []);

  it('is what is assigned to me, plus unassigned work my role owns', () => {
    assert.deepEqual([mineAssigned, othersAssigned, unassignedMine, unassignedOther, noOwner].map((t) => isMine(t, hod)),
      [true, false, true, false, false]);
  });

  it('gives unowned, unassigned work to the coordinators so it never drops out', () => {
    assert.equal(isMine(noOwner, { id: 'x', role: 'iqac_coordinator' }), true);
    assert.equal(isMine(noOwner, { id: 'x', role: 'institution_admin' }), true);
  });

  it('filters by role, unassigned and overdue', () => {
    const all = [mineAssigned, othersAssigned, unassignedMine, unassignedOther, noOwner];
    assert.equal(filterTasks(all, { role: 'registrar' }).length, 1);
    assert.equal(filterTasks(all, { unassignedOnly: true }).length, 3);
    assert.equal(filterTasks(all, { overdueOnly: true }).length, 0);
  });
});

describe('who a task can be assigned to', () => {
  const people = [{ id: 'a', role: 'hod' }, { id: 'b', role: 'registrar' }, { id: 'c', role: 'institution_admin' },
    { id: 'd', role: 'iqac_coordinator' }];
  it('its owner role or an Institution Admin, as the server allows', () => {
    const [hodTask, unowned] = buildTasks([fact({ id: '1' }), fact({ id: '2', owner_role: '' })], []);
    assert.deepEqual(eligibleAssignees(hodTask, people).map((p) => p.id), ['a', 'c']);
    assert.deepEqual(eligibleAssignees(unowned, people).map((p) => p.id), ['c', 'd']);
  });
});

describe('OwnerTaskCard (rendered)', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const noop = 'export const __n = 0; const f = () => Promise.resolve({ data: {} });';
  const { mod, cleanup } = await bundleComponent(new URL('./OwnerTaskCard.tsx', import.meta.url), {
    'api/facts': `${noop} export const assignFact = f, confirmFact = f, correctFact = f, getFact = f, rejectFact = f;`,
    'api/gaps': `${noop} export const assignGap = f, getGap = f, markGapUnavailable = f, resolveGap = f, skipGap = f, chooseConflictValue = f;`,
    'api/evidenceRequests': `${noop} export const listEvidenceAssignees = f, createEvidenceRequest = f;`,
    AuthContext: "export const useAuth = () => ({ user: { id: 'u', role: 'registrar' } });",
  });
  after(cleanup);
  const render = (task: unknown, coordinator = false) => renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(mod.OwnerTaskCard, { task, sprintId: 's1', coordinator, people: [], onChanged() {} })));

  it('shows the source, owner, assignee and due date', () => {
    const [t] = buildTasks([fact({ assigned_to: 'u-hod', assigned_to_name: 'Dr. Rao', due_date: '2026-01-01' })], [], '2026-10-21');
    const html = render(t);
    for (const text of ['120 of 192 completed.', 'page 45', 'SSR.pdf', 'Head of Department', 'Dr. Rao', 'due 2026-01-01', '(overdue)']) {
      assert.ok(html.includes(text), text);
    }
    assert.ok(html.includes('>Confirm<') && html.includes('>Reject<'));
  });

  it('says who can act, and offers no action the server would refuse', () => {
    const reason = 'Only the Head of Department, an Institution Admin or InGage staff can act on this fact.';
    const [t] = buildTasks([fact({ can_act: false, act_blocked_reason: reason })], []);
    const html = render(t);
    assert.ok(html.includes(reason));
    assert.ok(!html.includes('>Confirm<') && !html.includes('>Reject<') && !html.includes('>Assign<'));
    assert.ok(render(t, true).includes('>Assign<'));  // a coordinator may still assign it
  });

  it('a conflict can be compared, and closed only as described by the server', () => {
    const [t] = buildTasks([], [gap({ resolve_blocked_reason: 'The values still disagree. Correct or reject the facts.' })]);
    const html = render(t);
    assert.ok(html.includes('>Compare sources<') && html.includes('>Close as unresolved<'));
    assert.match(html, /disabled=""[^>]*title="The values still disagree[^"]*">Resolve</);
  });
});
