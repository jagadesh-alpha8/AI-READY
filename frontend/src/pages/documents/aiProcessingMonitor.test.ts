/**
 * AI Processing Monitor updates in place (`npm test`): once data is on screen, a background refresh never swaps
 * the page for the loading screen, a failed refresh is a small warning (the last data stays), and an active run
 * shows "Live" with eased progress bars. Fixtures follow the jobs / documents / processing-summary APIs.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';

const job = {
  id: 'j1', sprint_id: 's1', document_id: 'd1', document_filename: 'ssr.pdf', status: 'running',
  current_step: 'extracting_facts', current_step_label: 'Extracting facts', progress_percentage: 42,
  started_at: '2026-10-27T10:00:00Z', completed_at: null, error_message: '', retry_count: 0, ai_router: '',
  attempts: [], completeness: '', extraction_warnings: [], chunks_total: 4, chunks_completed: 1,
  created_at: '2026-10-27T10:00:00Z', updated_at: '2026-10-27T10:01:00Z', ai_input_tokens: 0, ai_output_tokens: 0,
  ai_cost_usd: null,
};
const documents = [{ id: 'd1', original_filename: 'ssr.pdf', document_type: 'naac_ssr', status: 'processing' }];
const summary = {
  complete: false, description: '', incomplete: [],
  counts: { complete: 0, partial: 0, failed: 0, active: 1, not_processed: 0, total: 1 },
  documents: [{ document_id: 'd1', filename: 'ssr.pdf', state: 'active' }],
  excluded: { earlier_version: 0, rejected: 0, total: 0 }, excluded_documents: [],
};

describe('AI Processing Monitor live updates', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter, Route, Routes } = await import('react-router-dom');
  const page = await bundleComponent(new URL('./AIProcessingMonitor.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {}, refresh: async () => "", setData() {} };',
    AuthContext: 'export const useAuth = () => ({ user: { id: "u", role: "super_admin" } });',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  });
  after(() => page.cleanup());
  const g = globalThis as Record<string, unknown>;
  const res = (data: unknown, over: Record<string, unknown> = {}) =>
    ({ data, loading: false, error: '', refetch() {}, refresh: async () => '', setData() {}, ...over });
  const render = (jobsOver: Record<string, unknown> = {}) => {
    g.__resources = [res([job], jobsOver), res(documents, jobsOver), res(summary, jobsOver),
      res({ total: 3, by_document: { d1: 3 } }), res({ total: 0, gap_type: {} }), res(null)];
    return renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/sprint/s1/monitor'] },
      React.createElement(Routes, null, React.createElement(Route, {
        path: '/sprint/:sprintId/monitor', element: React.createElement(page.mod.AIProcessingMonitor) }))));
  };

  it('keeps the monitor on screen while a background refresh is loading', () => {
    const html = render({ loading: true });  // data already there, a refresh in flight
    assert.ok(!html.includes('Loading extraction jobs'), 'no full loading screen');
    for (const t of ['ssr.pdf', '42%', '3 Facts']) assert.ok(html.includes(t), t);
  });

  it('shows Live and an eased progress bar while a document is processing', () => {
    const html = render();
    assert.ok(html.includes('>Live<'));
    assert.match(html, /transition-\[width\][^"]*motion-reduce:transition-none[^>]*style="width:42%"/);
    // A quiet summary for screen readers (counts only, not every percent).
    assert.match(html, /role="status" aria-live="polite">0 of 1 documents fully processed, 1 processing</);
  });

  it('a failed background refresh keeps the last data instead of the error screen', () => {
    const html = render({ error: 'Network error' });  // error from a refresh, data still present
    assert.ok(html.includes('ssr.pdf'));
    assert.ok(!html.includes('Could not load sprint processing status'));
  });

  it('the first load still shows the loading screen', () => {
    g.__resources = [res(null, { loading: true }), res(null, { loading: true }), res(null, { loading: true })];
    const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/sprint/s1/monitor'] },
      React.createElement(Routes, null, React.createElement(Route, {
        path: '/sprint/:sprintId/monitor', element: React.createElement(page.mod.AIProcessingMonitor) }))));
    assert.ok(html.includes('Loading extraction jobs'));
  });
});
