/** The IQAC Coordinator activation page (/activate-account): a link without a token is explained, a link with one
 * is checked with the server first (`npm test`). */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';

describe('Activate account page', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const ui = await bundleComponent(new URL('./ActivateAccount.tsx', import.meta.url), {
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
    'ingage-logo-mark.png': 'export default "logo.png";',
    'ingage-logo-mark-dark.png': 'export default "logo-dark.png";',
  });
  after(() => ui.cleanup());
  const render = (url: string) => renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [url] },
    React.createElement(ui.mod.ActivateAccount)));

  it('a link without a token is explained', () => {
    assert.ok(render('/activate-account').includes('Invitation link incomplete'));
  });

  it('a link with a token is checked first, never shown', () => {
    const html = render('/activate-account?token=abc123');
    assert.ok(html.includes('Checking your invitation'));
    assert.ok(!html.includes('abc123'));
  });
});
