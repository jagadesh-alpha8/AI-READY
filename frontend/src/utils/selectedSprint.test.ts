/**
 * The selected sprint across navigation, refresh and explicit switching (`npm test`).
 * Sessions are replayed through the same rules SelectedSprintProvider applies (utils/selectedSprint.ts);
 * the sidebar and header are rendered with react-dom/server against a stubbed selection.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../testing/bundle.ts';
import {
  PLACEHOLDER_SPRINT_ID, readStoredSprint, resolveSelection, sprintIdFromPath, sprintStepPath, storageKey,
  storedAfter, switchSprintPath, writeStoredSprint,
} from './selectedSprint.ts';

class MemoryStorage {
  map = new Map<string, string>();
  getItem(k: string) { return this.map.get(k) ?? null; }
  setItem(k: string, v: string) { this.map.set(k, v); }
  removeItem(k: string) { this.map.delete(k); }
}

/** One browser tab: what SelectedSprintProvider does on every navigation, switch and reload. */
function openApp(storage: MemoryStorage, userId: string, visible: string[], path = '/dashboard') {
  let stored = readStoredSprint(storage, userId);
  const settle = () => {
    const selection = resolveSelection(sprintIdFromPath(path), stored, visible);
    const next = storedAfter(selection, stored);
    if (next !== null) {
      writeStoredSprint(storage, userId, next);
      stored = next;
    }
    return { ...selection, path, menuLink: sprintStepPath(selection.status === 'ok' ? selection.sprintId : '', 'gaps') };
  };
  settle(); // the provider resolves the first page on mount
  return {
    now: settle,
    visit(p: string) { path = p; return settle(); },
    /** The user picks a sprint in the header. */
    choose(id: string) {
      writeStoredSprint(storage, userId, id);
      stored = id;
      path = switchSprintPath(path, id) ?? path;
      return settle();
    },
  };
}

describe('reading the URL', () => {
  it('takes the sprint from /sprint/<id>/<step> only', () => {
    assert.equal(sprintIdFromPath('/sprint/S1/gaps'), 'S1');
    assert.equal(sprintIdFromPath('/sprint/S1/gaps/extra'), 'S1');
    assert.equal(sprintIdFromPath('/sprint/setup'), '');
    assert.equal(sprintIdFromPath(`/sprint/${PLACEHOLDER_SPRINT_ID}/gaps`), '');
    assert.equal(sprintIdFromPath('/dashboard'), '');
  });

  it('builds menu links for the selected sprint, and none without one', () => {
    assert.equal(sprintStepPath('S1', 'facts'), '/sprint/S1/facts');
    assert.equal(sprintStepPath('', 'facts'), null);
  });
});

describe('the selection across navigation', () => {
  it('opening a sprint selects it, and it stays selected on every other menu', () => {
    const app = openApp(new MemoryStorage(), 'u1', ['S1', 'S2'], '/sprint/S1/upload');
    assert.equal(app.now().sprintId, 'S1');
    for (const p of ['/dashboard', '/evidence', '/reminders', '/sprint/setup', '/admin-settings']) {
      const at = app.visit(p);
      assert.deepEqual([at.sprintId, at.status, at.menuLink], ['S1', 'ok', '/sprint/S1/gaps'], p);
    }
    assert.equal(app.visit('/sprint/S1/score').sprintId, 'S1');
  });

  it('nothing selected means a prompt, not the first sprint', () => {
    const at = openApp(new MemoryStorage(), 'u1', ['S1', 'S2']).visit('/evidence');
    assert.deepEqual([at.sprintId, at.status, at.menuLink], ['', 'none', null]);
  });

  it('browser back to another sprint\'s page shows that sprint, as its URL says', () => {
    const app = openApp(new MemoryStorage(), 'u1', ['S1', 'S2'], '/sprint/S1/gaps');
    app.choose('S2');
    assert.equal(app.visit('/sprint/S1/gaps').sprintId, 'S1'); // back
    assert.equal(app.visit('/dashboard').sprintId, 'S1');
  });
});

describe('the selection across a refresh', () => {
  it('is restored on a page without a sprint in its URL', () => {
    const storage = new MemoryStorage();
    openApp(storage, 'u1', ['S1', 'S2'], '/sprint/S2/facts').now();
    const reloaded = openApp(storage, 'u1', ['S1', 'S2'], '/goals-tasks').now();
    assert.deepEqual([reloaded.sprintId, reloaded.status], ['S2', 'ok']);
  });

  it('is kept per user', () => {
    const storage = new MemoryStorage();
    openApp(storage, 'u1', ['S1'], '/sprint/S1/facts').now();
    assert.equal(openApp(storage, 'u2', ['S1'], '/dashboard').now().status, 'none');
  });

  it('forgets a saved sprint that was deleted or is no longer visible', () => {
    const storage = new MemoryStorage();
    openApp(storage, 'u1', ['S1'], '/sprint/S1/facts');
    const gone = resolveSelection('', 'S1', []);
    assert.deepEqual([gone.status, storedAfter(gone, 'S1')], ['not_found', '']);
    const app = openApp(storage, 'u1', [], '/dashboard'); // S1 was deleted meanwhile
    assert.equal(storage.getItem(storageKey('u1')), null);
    assert.equal(app.now().status, 'none');
  });

  it('works without storage (blocked): no saved selection, no crash', () => {
    const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); },
      removeItem() { throw new Error('blocked'); } };
    assert.equal(readStoredSprint(blocked, 'u1'), '');
    assert.doesNotThrow(() => writeStoredSprint(blocked, 'u1', 'S1'));
  });
});

describe('switching sprints explicitly', () => {
  it('on a sprint page: the same step for the new sprint, and it stays selected', () => {
    const storage = new MemoryStorage();
    const app = openApp(storage, 'u1', ['S1', 'S2'], '/sprint/S1/gaps');
    const at = app.choose('S2');
    assert.deepEqual([at.path, at.sprintId, at.menuLink], ['/sprint/S2/gaps', 'S2', '/sprint/S2/gaps']);
    assert.equal(app.visit('/dashboard').sprintId, 'S2');
    assert.equal(openApp(storage, 'u1', ['S1', 'S2'], '/dashboard').now().sprintId, 'S2'); // and after a refresh
  });

  it('on another page: the page stays, now for the new sprint', () => {
    const app = openApp(new MemoryStorage(), 'u1', ['S1', 'S2'], '/sprint/S1/gaps');
    app.visit('/transformation-plan');
    const at = app.choose('S2');
    assert.deepEqual([at.path, at.sprintId], ['/transformation-plan', 'S2']);
  });

  it('a sprint in the URL the user cannot see is not saved as the selection', () => {
    const storage = new MemoryStorage();
    const app = openApp(storage, 'u1', ['S1'], '/sprint/S1/gaps');
    assert.equal(app.visit('/sprint/OTHER/gaps').status, 'not_found');
    assert.equal(storage.getItem(storageKey('u1')), 'S1');
    assert.equal(app.visit('/dashboard').sprintId, 'S1');
  });

  it('keeps the step and drops nothing else of the path', () => {
    assert.equal(switchSprintPath('/sprint/S1/recommendations', 'S2'), '/sprint/S2/recommendations');
    assert.equal(switchSprintPath('/dashboard', 'S2'), null);
  });
});

describe('rendered', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  // The selection the components read, set per test (stubs SelectedSprintContext.useSelectedSprint).
  const stubs = {
    SelectedSprintContext: 'export const useSelectedSprint = () => globalThis.__selection;',
    // A consultant sees every sprint step, Sprint Setup included.
    AuthContext: "export const useAuth = () => ({ user: { id: 'u1', role: 'consultant' } });",
    'api/evidenceRequests': 'export const getEvidenceRequestSummary = () => new Promise(() => {});',
  };
  const sidebar = await bundleComponent(new URL('../components/Sidebar.tsx', import.meta.url), stubs);
  const bar = await bundleComponent(new URL('../components/SprintContextBar.tsx', import.meta.url), stubs);
  after(() => { sidebar.cleanup(); bar.cleanup(); });

  const sprint = (id: string, code: string) => ({
    id, sprint_code: code, name: '', institution_name: 'VELS University', status: 'reviewing', academic_year: '2025-26',
  });
  const S1 = sprint('S1', 'VELS-2025-01');
  const S2 = sprint('S2', 'VELS-2026-02');
  const render = (component: unknown, selection: Record<string, unknown>, url = '/dashboard') => {
    (globalThis as Record<string, unknown>).__selection = {
      sprints: [S1, S2], loadError: false, selectSprint() {}, refreshSprints() {}, ...selection,
    };
    return renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [url] },
      React.createElement(component as React.FC)));
  };

  it('every sprint step in the menu links to the selected sprint', () => {
    const html = render(sidebar.mod.Sidebar, { sprintId: 'S2', sprint: S2, status: 'ok' });
    for (const step of ['upload', 'evidence', 'score', 'recommendations', 'report']) {
      assert.ok(html.includes(`href="/sprint/S2/${step}"`), step);
    }
    for (const removed of ['Evidence Requests', 'Owner Workspace', 'Legacy', 'Goals &amp; Tasks', 'Sprint Transformation Plan']) {
      assert.ok(!html.includes(removed), removed);
    }
    assert.ok(html.includes('Evidence &amp; Review'));
    assert.ok(!html.includes('/sprint/S1/'));
    assert.ok(!html.includes(PLACEHOLDER_SPRINT_ID));
  });

  it('with no sprint selected the steps are not links, and say why', () => {
    const html = render(sidebar.mod.Sidebar, { sprintId: '', sprint: null, status: 'none' });
    assert.ok(!/href="\/sprint\/[^s]/.test(html)); // only /sprint/setup remains a link
    assert.ok(html.includes('href="/sprint/setup"'));
    assert.ok(html.includes('Choose a sprint to open its steps.'));
    assert.ok(!html.includes(PLACEHOLDER_SPRINT_ID));
  });

  it('the header names the selected sprint and its institution, with the picker on it', () => {
    const html = render(bar.mod.SprintContextBar, { sprintId: 'S1', sprint: S1, status: 'ok' });
    assert.ok(html.includes('VELS-2025-01') && html.includes('VELS University'));
    assert.match(html, /<option value="S1" selected="">/);
    assert.ok(!html.includes('Choose a sprint…'));
  });

  it('the header says plainly when nothing is selected, or the sprint is gone', () => {
    const none = render(bar.mod.SprintContextBar, { sprintId: '', sprint: null, status: 'none' });
    assert.ok(none.includes('No sprint selected'));
    assert.ok(!none.includes('Selected sprint</p>'));
    assert.match(none, /<option value="" selected="">Choose a sprint…<\/option>/);
    const gone = render(bar.mod.SprintContextBar, { sprintId: '', sprint: null, status: 'not_found' });
    assert.ok(gone.includes('no longer exists'));
  });

  it('a failed load offers a retry instead of dropping the selection', () => {
    const html = render(bar.mod.SprintContextBar, { sprintId: 'S1', sprint: null, status: 'loading', sprints: null, loadError: true });
    assert.ok(html.includes('Could not load your sprints.') && html.includes('Retry'));
  });
});
