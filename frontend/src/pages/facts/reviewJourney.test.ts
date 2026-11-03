import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { bundleComponent } from '../../testing/bundle.ts';

let bundle: Awaited<ReturnType<typeof bundleComponent>>;
let reads = 0;
let writes = 0;
before(async () => {
  bundle = await bundleComponent(new URL('./ReviewJourney.tsx', import.meta.url), {
    '../../api/client': `export default { get: () => { globalThis.reviewReads++; return Promise.resolve({ data: globalThis.reviewFixture }); }, post: () => { globalThis.reviewWrites++; } };`,
    '../../hooks/useApiResource': `export const useApiResource = () => ({ data: globalThis.reviewFixture, refetch: () => {}, error: null });`,
    '../../utils/access': `export const useAccess = () => ({ can: () => true });`,
    './FactsReview': `export const FactsReview = () => <p>Supporting detail</p>;`,
  });
});
after(() => bundle.cleanup());
function render(fixture: unknown) {
  (globalThis as any).reviewFixture = fixture;
  (globalThis as any).reviewReads = reads;
  (globalThis as any).reviewWrites = writes;
  return renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(bundle.mod.ReviewJourney)));
}
it('rendering offers an explicit start and never prepares a batch or model work', () => {
  const html = render({ started: false, cases: [], overflow: [] });
  assert.match(html, /Prepare review questions/);
  assert.match(html, /Continue to capability assessment/);
  assert.equal((globalThis as any).reviewWrites, 0);
});
it('initial decisions, overflow and optional follow-up have distinct presentation', () => {
  const question = { id: 'q1', question: 'Can access be established?', scope: { programme: 'engineering' }, alternatives: [], state: 'defer', initial: true, affected_requirements: [], reason: 'Scoped evidence' };
  const html = render({ started: true, cases: [question], overflow: [{ ...question, id: 'q2', question: 'Overflow question hidden by default', initial: false }], mode: 'shadow', new_material_case_count: 1 });
  assert.match(html, /1 of 1 initial questions settled/);
  assert.match(html, /1 optional overflow questions/);
  assert.doesNotMatch(html, /Overflow question hidden by default/);
  assert.match(html, /Prepare optional follow-up/);
  assert.match(html, /shadow mode/);
  assert.equal((globalThis as any).reviewWrites, 0);
});
it('scope and quotations are escaped and no score uplift is promised', () => {
  const html = render({ started: true, mode: 'enforce', overflow: [], cases: [{ id: 'q1', question: '<script>unsafe</script>', state: 'awaiting', initial: true, alternatives: [{ value: 20, fact_ids: ['a', 'b'], excerpts: [{ filename: 'source.pdf', page: '1', quote: '<img src=x onerror=bad()>', verification: 'verified' }] }], scope: { programme: 'engineering' }, affected_requirements: ['AIQIF-C6.1.F1'] }] });
  assert.doesNotMatch(html, /<script>unsafe/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /2 linked claim/);
  assert.match(html, /not a promised score change/);
  assert.match(html, /manual answer is recorded as a declaration/);
});
