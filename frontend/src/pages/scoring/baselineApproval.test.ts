/**
 * Baseline Approval (`npm test`): the reviewer sees which calculation they are approving, a recalculated preview
 * says so, and a decided baseline whose Live CRI moved on keeps its own score. Fixtures follow GET .../baseline/.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import type { Baseline, SprintBaseline } from '../../types/index.ts';
import { bundleComponent } from '../../testing/bundle.ts';

const baseline = (over: Partial<Baseline>): Baseline => ({
  id: 'b1', sprint_id: 's', scoring_run_id: '0ddc48ce-f5af-4918-afe3-8dfa85825d56',
  scoring_run_calculated_at: '2026-10-26T07:22:35Z', status: 'pending', revises: null, overall_cri: 13, overall_confidence: 0.13,
  calculation_version: 'v1', pillar_snapshot: [], coverage_adjusted_cri: 0, evidence_coverage: {},
  approved_by: null, approved_by_name: '', approved_at: null, comments: '', created_at: '', updated_at: '',
  history: [{ id: 'h', action: 'refreshed', user: null, user_name: '', comments: 'x', created_at: '2026-10-26T07:22:35Z' }],
  ...over,
});

const score = {
  sprint_id: 's', overall_cri: 13, raw_cri: 13, coverage_adjusted_cri: 0, evidence_coverage: {}, overall_confidence: 0.13,
  cri_score: 13, cri_confidence: 0.13, calculation_version: 'v1', calculated_at: null, pillar_scores: [],
  strengths: [], weaknesses: [], unresolved_blocking_gaps: [],
  evidence_metrics: { confirmed_facts: 1, corrected_facts: 0, total_extracted_facts: 2, documents_processed: 2, unresolved_gaps: 5 },
};

const payload = (over: Partial<SprintBaseline>): SprintBaseline => ({
  baseline: baseline({}), score: score as SprintBaseline['score'], high_priority_gaps: [], can_approve: true,
  processing: undefined, refreshed: false, baseline_is_current: true, ...over,
});

describe('Baseline Approval', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter, Route, Routes } = await import('react-router-dom');
  const page = await bundleComponent(new URL('./BaselineApproval.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {}, setData() {} };',
    AuthContext: 'export const useAuth = () => ({ user: { id: "u", role: "super_admin" } });',
    'utils/devMode': 'export const isLocalDev = false;',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  });
  after(() => page.cleanup());
  const g = globalThis as Record<string, unknown>;
  const ok = (data: unknown) => ({ data, loading: false, error: '', refetch() {}, setData() {} });
  const render = (data: SprintBaseline) => {
    g.__resources = [ok(data), ok({ completion_percentage: 40 }), ok(null)];
    return renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/sprint/s/baseline'] },
      React.createElement(Routes, null, React.createElement(Route, {
        path: '/sprint/:sprintId/baseline', element: React.createElement(page.mod.BaselineApproval) }))));
  };

  it('shows which calculation is under review', () => {
    const html = render(payload({}));
    for (const t of ['Calculation 0ddc48ce', '13.0', '13% evidence confidence', 'Preview recalculated']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('the history lists every cycle, not only the current one', () => {
    const decided = baseline({ id: 'old', status: 'provisional', overall_cri: 0, scoring_run_id: '76ae0e84-0000-0000-0000-000000000000',
      history: [{ id: 'a', action: 'submitted', user: null, user_name: 'Super Admin', comments: '', created_at: '2026-10-26T06:12:04Z' },
        { id: 'b', action: 'approved_provisional', user: null, user_name: 'Super Admin', comments: 'Pilot', created_at: '2026-10-26T11:20:03Z' }] });
    const current = baseline({ id: 'new', revises: 'old',
      history: [{ id: 'c', action: 'submitted', user: null, user_name: 'Super Admin', comments: 'Revision', created_at: '2026-10-26T18:00:00Z' }] });
    const html = render(payload({ baseline: current, cycles: [current, decided] }));
    for (const t of ['Approval History (2 cycles)', 'Cycle 2', 'Cycle 1', 'revises cycle 1', 'Approved provisionally',
      '&quot;Pilot&quot;', 'Calculation 76ae0e84']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('says when the preview was recalculated because the data changed', () => {
    const html = render(payload({ refreshed: true }));
    assert.ok(html.includes('so it now shows the latest calculation. Review it before approving.'));
  });

  it('a decided baseline keeps its score when the Live CRI moves on', () => {
    const html = render(payload({
      baseline: baseline({ status: 'provisional', overall_cri: 0, approved_by_name: 'Super Admin',
        approved_at: '2026-10-26T11:20:03Z' }),
      baseline_is_current: false,
    }));
    for (const t of ['The Live CRI has moved on since this decision', 'it is now 13.0', 'keeps the 0.0 it',
      'This baseline is locked', 'Start a new baseline revision']) {
      assert.ok(html.includes(t), t);
    }
    assert.ok(!html.includes('Approve Baseline</span>'), 'no approve button on a decided baseline');
  });
});

describe('Start demo revision (local development only)', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter, Route, Routes } = await import('react-router-dom');
  const build = (dev: boolean) => bundleComponent(new URL('./BaselineApproval.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {}, setData() {} };',
    AuthContext: 'export const useAuth = () => ({ user: { id: "u", role: globalThis.__role } });',
    'utils/devMode': `export const isLocalDev = ${dev};`,
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  });
  const local = await build(true);
  const production = await build(false);
  after(() => { local.cleanup(); production.cleanup(); });
  const g = globalThis as Record<string, unknown>;
  const ok = (data: unknown) => ({ data, loading: false, error: '', refetch() {}, setData() {} });
  const decidedCurrent = payload({
    baseline: baseline({ status: 'provisional', approved_by_name: 'Super Admin', approved_at: '2026-10-26T11:20:03Z' }),
    baseline_is_current: true,
  });
  const render = (page: { mod: Record<string, unknown> }, role: string, data: SprintBaseline) => {
    g.__role = role;
    g.__resources = [ok(data), ok({ completion_percentage: 40 }), ok(null)];
    return renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/sprint/s/baseline'] },
      React.createElement(Routes, null, React.createElement(Route, {
        path: '/sprint/:sprintId/baseline', element: React.createElement(page.mod.BaselineApproval as React.FC) }))));
  };

  it('a sprint manager sees it on the local dev server for a current decided baseline', () => {
    const html = render(local, 'super_admin', decidedCurrent);
    for (const t of ['Local development only', 'Start demo revision', 'The current decision stays in force']) {
      assert.ok(html.includes(t), t);
    }
    assert.ok(!html.includes('The Live CRI has moved on'), 'the score has not changed');
  });

  it('never appears in a production build', () => {
    const html = render(production, 'super_admin', decidedCurrent);
    for (const t of ['Local development only', 'Start demo revision']) assert.ok(!html.includes(t), `no ${t}`);
  });

  it('is not offered to roles that cannot manage the sprint', () => {
    for (const role of ['viewer', 'faculty']) {
      assert.ok(!render(local, role, decidedCurrent).includes('Start demo revision'), role);
    }
    // In the consolidated 3-role model, IQAC Coordinator manages the sprint and baseline approval
    assert.ok(render(local, 'iqac_coordinator', decidedCurrent).includes('Start demo revision'), 'iqac_coordinator manages sprint');
  });

  it('is not offered for a pending or returned baseline, or when the normal revision applies', () => {
    assert.ok(!render(local, 'super_admin', payload({})).includes('Start demo revision'));
    assert.ok(!render(local, 'super_admin', payload({ baseline: baseline({ status: 'returned' }) }))
      .includes('Start demo revision'));
    const moved = render(local, 'super_admin', payload({
      baseline: baseline({ status: 'approved', overall_cri: 0, approved_at: '2026-10-26T11:20:03Z' }),
      baseline_is_current: false,
    }));
    assert.ok(moved.includes('Start a new baseline revision') && !moved.includes('Start demo revision'));
  });
});
