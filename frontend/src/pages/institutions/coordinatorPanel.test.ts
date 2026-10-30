/**
 * The IQAC Coordinator panel on Institution DNA (`npm test`): status for everyone who can open the page, edit and
 * resend controls only for InGage staff (the server enforces both again), the staff-only "no activation link was
 * created" explanation, and field-level API errors.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import { coordinatorEmailError, coordinatorNameError } from '../../utils/coordinator.ts';

const INVITED = {
  configured: true, name: 'Dr. S. Priya', email: 'priya@mkce.ac.in', state: 'invited',
  state_label: 'Invitation sent, awaiting acceptance', can_resend: true, last_sent_at: null, send_count: 1,
  events: [{ action: 'invited', label: 'Coordinator invited', note: '', user_name: 'Admin', created_at: '2026-10-29T10:00:00Z' }],
};

describe('IQAC Coordinator panel', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const ui = await bundleComponent(new URL('./CoordinatorPanel.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__coordinator;',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  });
  after(() => ui.cleanup());
  const g = globalThis as Record<string, unknown>;
  const render = (data: unknown, canManage: boolean) => {
    g.__coordinator = { data, loading: false, error: '', refetch() {} };
    return renderToStaticMarkup(React.createElement(MemoryRouter, null,
      React.createElement(ui.mod.CoordinatorPanel, { institutionId: 'i1', canManage })));
  };

  it('staff see the coordinator, the status and the change / resend actions', () => {
    const html = render(INVITED, true);
    for (const t of ['IQAC Coordinator', 'Dr. S. Priya', 'priya@mkce.ac.in', 'Invitation sent, awaiting acceptance',
      'Change coordinator', 'Resend invitation', 'previous link stops working', 'History (1)']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('college users see the coordinator but no edit or resend controls', () => {
    const html = render(INVITED, false);
    assert.ok(html.includes('Dr. S. Priya'));
    assert.ok(!html.includes('Change coordinator'));
    assert.ok(!html.includes('Resend invitation'));
  });

  it('resend is offered only when the server says it is available', () => {
    const html = render({ ...INVITED, state: 'active', state_label: 'Active', can_resend: false }, true);
    assert.ok(html.includes('Active'));
    assert.ok(!html.includes('Resend invitation'));
  });

  it('an unusable email says no link was created and what to do', () => {
    const html = render({ ...INVITED, state: 'account_unavailable', can_resend: false,
      state_label: "No activation link was created: this email address can't be used for this college's IQAC Coordinator." }, true);
    assert.ok(html.includes('No activation link was created'));
    assert.ok(!html.includes('Resend invitation'));
  });

  it('a college without a coordinator is told sprints are blocked, and staff can add one', () => {
    const html = render({ configured: false, name: '', email: '', state: 'missing', state_label: 'Not configured',
      can_resend: false }, true);
    assert.ok(html.includes('Add coordinator'));
    assert.ok(html.includes('sprints cannot be started'));
  });

  it('API errors land on their field, a general one stays general', () => {
    const fieldErr = { response: { data: { coordinator_email: ['No activation link was created: use another address.'] } } };
    assert.deepEqual(ui.mod.coordinatorApiErrors(fieldErr),
      { fields: { coordinator_email: 'No activation link was created: use another address.' }, general: '' });
    const general = { response: { data: { detail: ['There is no pending invitation. Name the coordinator first.'] } } };
    assert.equal(ui.mod.coordinatorApiErrors(general).general, 'There is no pending invitation. Name the coordinator first.');
  });
});

describe('coordinator validators match the server rules', () => {
  it('names', () => {
    assert.equal(coordinatorNameError('Dr. S. Priya'), '');
    assert.equal(coordinatorNameError('சுப்ரமணியன்'), '');
    assert.ok(coordinatorNameError(''));
    assert.ok(coordinatorNameError('R2D2'));
    assert.ok(coordinatorNameError('<b>x</b>'));
  });

  it('emails', () => {
    assert.equal(coordinatorEmailError('priya@mkce.ac.in'), '');
    assert.ok(coordinatorEmailError(''));
    assert.ok(coordinatorEmailError('priya@'));
    assert.ok(coordinatorEmailError('priya mkce.ac.in'));
  });
});
