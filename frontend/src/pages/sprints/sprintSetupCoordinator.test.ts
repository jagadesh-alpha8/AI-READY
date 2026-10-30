/** Sprint Setup shows the selected college's own IQAC Coordinator as Nodal Officer, and blocks a college without
 * one (`npm test`). The server blocks it too (apps/sprints/views.py). */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';

const college = (name: string, coordinator: unknown) => ({ id: name, name, city: '', state: '', institution_type: '', coordinator });

describe('Sprint Setup nodal officer', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const ui = await bundleComponent(new URL('./SprintSetup.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => ({ data: globalThis.__institutions, loading: false, error: "", refetch() {} });',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
    'utils/access': 'export const useAccess = () => ({ step: () => null });',
    'tour/MenuTourOfferBanner': 'export const TakeTourButton = () => null;',
  });
  after(() => ui.cleanup());
  const g = globalThis as Record<string, unknown>;
  const render = () => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(ui.mod.SprintSetup)));

  it("shows the selected college's coordinator, never a fixed name", () => {
    g.__institutions = [college('SNS College', { configured: true, name: 'Jagadesh', email: 'jagadesh@sns.ac.in',
      state: 'invited', state_label: 'Invitation sent, awaiting acceptance', can_resend: true })];
    const html = render();
    assert.ok(html.includes('Jagadesh · jagadesh@sns.ac.in'));
    assert.ok(html.includes('Invitation sent, awaiting acceptance'));
    assert.ok(!html.includes('Kanthaswamy'));
  });

  it('a college without a coordinator is explained and cannot start a sprint', () => {
    g.__institutions = [college('Bare College', { configured: false, name: '', email: '', state: 'missing',
      state_label: 'Not configured', can_resend: false })];
    const html = render();
    assert.ok(html.includes('Bare College has no IQAC Coordinator yet'));
    assert.match(html, /<button[^>]*type="submit"[^>]*disabled=""/);
  });
});
