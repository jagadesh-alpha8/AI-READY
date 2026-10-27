/**
 * In-app dialogs (`npm test`): without <DialogHost /> mounted they fall back to the browser's own dialogs,
 * so pages behave the same anywhere; the host renders nothing until a dialog is asked for. Also the
 * role display names used on recommendations.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../testing/bundle.ts';
import { isRealSprintId, PLACEHOLDER_SPRINT_ID } from '../utils/selectedSprint.ts';

describe('dialogs', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const dialog = await bundleComponent(new URL('./Dialog.tsx', import.meta.url));
  after(() => dialog.cleanup());
  const g = globalThis as Record<string, unknown>;

  it('without a host, uses the native dialogs and trims a prompt answer', async () => {
    const asked: string[] = [];
    g.window = {
      confirm: (m: string) => { asked.push(m); return true; },
      prompt: () => '  because  ',
      alert: (m: string) => { asked.push(m); },
    };
    try {
      assert.equal(await dialog.mod.confirmDialog('Delete?', { danger: true }), true);
      assert.equal(await dialog.mod.promptDialog('Why?'), 'because');
      await dialog.mod.alertDialog('Failed.');
      assert.deepEqual(asked, ['Delete?', 'Failed.']);
      (g.window as Record<string, unknown>).prompt = () => null;
      assert.equal(await dialog.mod.promptDialog('Why?'), null);  // cancelled
    } finally {
      delete g.window;
    }
  });

  it('the host renders nothing until a dialog is open', () => {
    assert.equal(renderToStaticMarkup(React.createElement(dialog.mod.DialogHost)), '');
  });
});

describe('role labels and sprint ids', async () => {
  const access = await bundleComponent(new URL('../utils/access.ts', import.meta.url), {
    AuthContext: 'export const useAuth = () => ({ user: null });',
  });
  after(() => access.cleanup());

  it('shows a role by its display name, and blank stays blank', () => {
    assert.equal(access.mod.roleLabel('placement_officer'), 'Placement Officer');
    assert.equal(access.mod.roleLabel('hod'), 'Head of Department');
    assert.equal(access.mod.roleLabel('dean_of_studies'), 'dean of studies');
    assert.equal(access.mod.roleLabel(''), '');
  });

  it('the old placeholder sprint id is never a real sprint', () => {
    assert.ok(isRealSprintId('s1'));
    for (const id of ['', undefined, null, PLACEHOLDER_SPRINT_ID]) assert.ok(!isRealSprintId(id));
  });
});
