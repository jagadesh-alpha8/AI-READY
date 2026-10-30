import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { JSDOM } from 'jsdom';
import { bundleComponent } from '../../testing/bundle.ts';
import { attempt, scoreLabel, tierLabel, active } from './presentation.ts';

const result = {
  lower: 0,
  upper: 100,
  exact_score: null,
  assessment_coverage: 0,
  condition_decision_coverage: 0,
  methodology: 'synthetic-test',
  methodology_status: 'experimental',
  pillars: [],
  tiers: ['Silver', 'Gold', 'Platinum'].map((name) => ({
    name,
    eligibility: 'unresolved',
    threshold: 50,
    pillar_floor: '30',
    gates: {},
  })),
  indicators: Array.from({ length: 36 }, (_, n) => ({
    code: `C${n + 1}`,
    name: `Indicator ${n + 1}`,
    pillar: 'P1',
    lower_level: 0,
    upper_level: 3,
    lower: 0,
    upper: 100,
    conditions: [
      {
        id: `C${n + 1}.F1`,
        text: 'Scoped requirement',
        state: 'unknown',
        level: 'F',
        completion_evidence: 'Scoped demonstration',
      },
    ],
  })),
};
const assessment = {
  result,
  records: result.indicators.map((i) => ({
    condition_id: i.conditions[0].id,
    state: 'unknown',
    reason: 'Not established',
    citations: [],
  })),
  actions: [],
  pathways: [],
};
const run = {
  id: 'run1',
  status: 'completed',
  requests_reserved: 0,
  reserved_cost_usd: '0',
  inputs_hash: 'frozen',
  profile: { name: 'Synthetic College <script>bad()</script>' },
  population: 'All',
  reference_period: '2025-26',
  source_manifest: [],
  assessment,
  partial_decisions: [],
  error: null,
};
let bundle: Awaited<ReturnType<typeof bundleComponent>>;
let dom: JSDOM;
let calls: string[];
let hooks: Record<string, (...args: any[]) => any>;
const names = [
  'listRuns',
  'getRun',
  'startRun',
  'cancelRun',
  'listAdvice',
  'getAdvice',
  'startAdvice',
  'cancelAdvice',
  'updateAction',
  'downloadCapabilityReport',
];
before(async () => {
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
  });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  bundle = await bundleComponent(
    new URL('./CapabilityWorkspace.tsx', import.meta.url),
    {
      '../../api/capability': names
        .map(
          (name) =>
            `export const ${name} = (...args) => globalThis.capabilityApi.${name}(...args);`,
        )
        .join('\n'),
      '../../context/SelectedSprintContext': `export const useSelectedSprint = () => ({ sprintId: 'sprint1' });`,
      '../../utils/access': `export const useAccess = () => ({ can: () => true });`,
    },
  );
});
after(() => {
  bundle.cleanup();
  dom.window.close();
});
function defaults() {
  calls = [];
  hooks = {
    listRuns: async () => ({
      data: {
        results: [run, { ...run, id: 'run2' }],
        next: null,
        previous: null,
        enabled: true,
      },
    }),
    getRun: async (_s, id) => ({ data: { ...run, id } }),
    listAdvice: async () => ({
      data: { results: [], next: null, previous: null, enabled: true },
    }),
  };
  for (const name of names)
    if (!hooks[name])
      hooks[name] = async () => {
        calls.push(name);
        return { data: run };
      };
  (globalThis as any).capabilityApi = hooks;
}
async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
async function mount(mode = 'standing') {
  defaults();
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () =>
    root.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/score?run=run1'] },
        React.createElement(bundle.mod.CapabilityWorkspace, { mode }),
      ),
    ),
  );
  await flush();
  await flush();
  return {
    container,
    async close() {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}
describe('capability presentation and explicit spending', () => {
  it('keeps uncertainty distinct from zero and reuses retry keys', () => {
    assert.equal(scoreLabel(result as any), '0.00–100.00 / 100');
    assert.equal(
      scoreLabel({ ...result, upper: 0, exact_score: 0 } as any),
      '0.00 / 100',
    );
    assert.equal(tierLabel('unresolved'), 'Unresolved evidence');
    assert.equal(active({ status: 'failed' } as any), false);
    const prior = attempt(null, 'same-body', () => 'key1');
    assert.equal(attempt(prior, 'same-body', () => 'key2').key, 'key1');
    assert.equal(attempt(prior, 'changed-body', () => 'key2').key, 'key2');
  });
  it('renders experimental bounds without a confidence claim', () => {
    const html = renderToStaticMarkup(
      React.createElement(bundle.mod.CapabilitySummary, { result }),
    );
    assert.match(html, /upper bound is not demonstrated capability/);
    assert.match(html, /Experimental internal criteria/);
    assert.doesNotMatch(html, /100% confidence/);
  });
  it('loads all 36 indicators read-only and escapes profile text', async () => {
    const ui = await mount();
    assert.equal(
      ui.container.querySelectorAll(
        'section[aria-label="Indicator evidence"] > details',
      ).length,
      36,
    );
    assert.equal(ui.container.querySelector('script'), null);
    assert.match(
      ui.container.textContent!,
      /Synthetic College <script>bad\(\)<\/script>/,
    );
    assert.deepEqual(calls, []);
    await ui.close();
  });
  it('exports without baseline approval or model calls', async () => {
    const ui = await mount('report');
    assert.match(ui.container.textContent!, /No baseline approval is required/);
    const button = [...ui.container.querySelectorAll('button')].find(
      (b) => b.textContent === 'Download assessment JSON',
    )!;
    await act(async () => button.click());
    assert.deepEqual(calls, ['downloadCapabilityReport']);
    await ui.close();
  });
  it('discards late responses after changing assessments', async () => {
    const ui = await mount();
    let resolveOld: (v: any) => void = () => {};
    hooks.getRun = async (_s, id) =>
      id === 'run2'
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : { data: { ...run, id, profile: { name: 'Selected institution' } } };
    const select = ui.container.querySelector(
      'select[aria-label="Assessment history"]',
    ) as HTMLSelectElement;
    await act(async () => {
      select.value = 'run2';
      select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    });
    await act(async () => {
      select.value = 'run1';
      select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    });
    await flush();
    await act(async () =>
      resolveOld({
        data: { ...run, id: 'run2', profile: { name: 'WRONG INSTITUTION' } },
      }),
    );
    assert.doesNotMatch(ui.container.textContent!, /WRONG INSTITUTION/);
    assert.match(ui.container.textContent!, /Selected institution/);
    assert.deepEqual(calls, []);
    await ui.close();
  });
});
