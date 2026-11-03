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
  'listPlanEvaluations',
  'getPlanEvaluation',
  'startPlanEvaluation',
  'cancelPlanEvaluation',
  'downloadPlanReport',
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
    listPlanEvaluations: async () => ({ data: { results: [], next: null, previous: null, enabled: true } }),
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
  it('flags an entirely undecided independent baseline', () => {
    const html = renderToStaticMarkup(React.createElement(bundle.mod.CapabilitySummary,
      { result: { ...result, aggregation: 'independent_conditions' } }));
    assert.match(html, /Evidence review required/);
  });
  it('shows proposed foundation goals and equal outcomes at three paces', () => {
    const goal = { id: 'resources', target_condition_ids: ['pending'], title: 'Reuse existing resources', status: 'verify_before_implementation',
      suggested_role: 'IT lead', existing_strengths: [{ condition_id: 'known', reason: 'Verified access <script>bad()</script>' }],
      steps: ['Check suitability before conditional development.'], depends_on: [] };
    const plan = { destination: 'Proposed Silver foundation goals', baseline: { message: 'Review the unresolved baseline.' },
      routes: ['Immediate', 'Progressive', 'Gradual'].map(name => ({ name, indicative_duration: 'Illustrative duration',
        outcomes: ['resources'], assumptions: ['Confirm capacity first.'] })), goals: [goal], review_questions: [],
      other_unresolved_requirements: 10, limitations: ['Completion changes no score.'] };
    const html = renderToStaticMarkup(React.createElement(bundle.mod.FoundationPathway, { plan, advice: [{ condition_id: 'pending', steps: ['Inspect the verified facility for this workload.'], basis: [] }] }));
    assert.equal((html.match(/The same 1 remaining goals/g) || []).length, 3);
    assert.match(html, /Existing findings to build on/);
    assert.match(html, /proposal, not a badge assessment/);
    assert.doesNotMatch(html, /<script>/);
    assert.match(html, /Check suitability/);
    assert.match(html, /Inspect the verified facility/);
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
  it('separates response defects from unresolved evidence without changing the score', async () => {
    (run as any).diagnostics = { explanation: 'No indicator has both foundations demonstrated.', source_documents: 1, readable_pages: 187,
      unreadable_or_unavailable_pages: 0, state_counts: { met: 1, not_met: 0, unknown: 215, conflicting: 0 },
      validation_issues: [], foundation_blockers: [], indicators_with_bounded_context: 36, limitations: 'Saved decisions only.',
      cause_audit: { validator_affected_conditions: 5, evaluation_unavailable_conditions: 0, unknown_without_validator_issue: 210,
        foundation_blockers: [{ indicator: 'C1', blockers: [{ condition_id: 'C1.F1', requirement: 'Named AI strategy owner', state: 'unknown', reason: 'No named owner established in the supplied passage.', kind: 'unresolved_evidence' }] }] } };
    try {
      const ui = await mount();
      const panel = ui.container.querySelector('[aria-label="Why the range remains unresolved"]')!;
      assert.match(panel.textContent!, /5 requirement decisions could not be validated/);
      assert.match(panel.textContent!, /210 requirements have an unknown decision/);
      assert.match(panel.textContent!, /does not prove the full documents lack the evidence/);
      assert.match(panel.textContent!, /Named AI strategy owner/);
      assert.deepEqual(calls, []);
      await ui.close();
    } finally { delete (run as any).diagnostics; }
  });
  it('exports without baseline approval or model calls', async () => {
    const ui = await mount('report');
    assert.match(ui.container.textContent!, /selected version is preserved/);
    const button = [...ui.container.querySelectorAll('button')].find(
      (b) => b.textContent === 'Download assessment JSON',
    )!;
    await act(async () => button.click());
    assert.deepEqual(calls, ['downloadCapabilityReport']);
    await ui.close();
  });
  it('downloads the selected assessment directly as PDF', async () => {
    const ui = await mount('report');
    let args: unknown[] = [];
    hooks.downloadCapabilityReport = async (...values) => { args = values; };
    const button = [...ui.container.querySelectorAll('button')].find((b) => b.textContent === 'Download leadership PDF')!;
    await act(async () => button.click());
    assert.deepEqual(args.slice(0, 3), ['sprint1', 'run1', 'pdf']);
    assert.equal(args[4], 'leadership');
    assert.deepEqual(calls, []);
    await ui.close();
  });
  it('exports supporting evidence for the same selected assessment', async () => {
    const ui = await mount('report');
    let args: unknown[] = [];
    hooks.downloadCapabilityReport = async (...values) => { args = values; };
    const button = [...ui.container.querySelectorAll('button')].find((b) => b.textContent === 'Download supporting evidence PDF')!;
    await act(async () => button.click());
    assert.deepEqual(args.slice(0, 3), ['sprint1', 'run1', 'pdf']);
    assert.equal(args[4], 'evidence');
    await ui.close();
  });
  it('starts the overview with no compulsory scope inputs', async () => {
    const ui = await mount();
    let args: any[] = [];
    hooks.startRun = async (...values) => { args = values; return { data: run }; };
    const form = ui.container.querySelector('[data-tour="capability-start"] form')!;
    assert.equal(form.querySelectorAll('input[required]').length, 0);
    await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
    assert.deepEqual(args[1], { scope_mode: 'default' });
    assert.ok(args[2]);
    assert.deepEqual(calls, []);
    await ui.close();
  });
  it('routes identity review through the shared question budget before spending', async () => {
    const ui = await mount();
    const submitted: any[][] = [];
    hooks.startRun = async (...values) => {
      submitted.push(values);
      if (submitted.length === 1) throw { response: { data: { code: 'source_identity_confirmation_required', detail: 'Confirm source identity.', source_institutions: ['Synthetic University'] } } };
      return { data: run };
    };
    const form = ui.container.querySelector('[data-tour="capability-start"] form')!;
    await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
    await flush();
    assert.equal(submitted.length, 1);
    const link = [...ui.container.querySelectorAll('a')].find((a) => a.textContent === 'Review source identity')!;
    assert.ok(link);
    assert.equal(link.getAttribute('href'), '/sprint/sprint1/evidence?tab=review');
    assert.match(ui.container.textContent || '', /25-question budget/);
    assert.equal(submitted.length, 1);
    await ui.close();
  });
  it('shows that a saved old assessment needs a fresh run', async () => {
    const ui = await mount();
    hooks.getRun = async () => ({ data: { ...run, rubric_version: 'AIQIF-CAP-0.2', current_rubric_version: 'AIQIF-CAP-0.3' } });
    const refresh = [...ui.container.querySelectorAll('button')].find((b) => b.textContent === 'Refresh')!;
    await act(async () => refresh.click());
    // Force a different history selection to reload the run with current method metadata.
    const select = ui.container.querySelector('select[aria-label="Assessment history"]') as HTMLSelectElement;
    await act(async () => { select.value = 'run2'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
    await flush();
    assert.match(ui.container.textContent!, /saved assessment uses the earlier scoring method/);
    assert.match(ui.container.textContent!, /AIQIF-CAP-0.3/);
    await ui.close();
  });
  it('flags an older protocol even when the rubric version matches', async () => {
    const ui = await mount();
    hooks.getRun = async () => ({ data: { ...run, rubric_version: 'AIQIF-CAP-0.3',
      current_rubric_version: 'AIQIF-CAP-0.3', assessment_protocol_current: false } });
    const select = ui.container.querySelector('select[aria-label="Assessment history"]') as HTMLSelectElement;
    await act(async () => { select.value = 'run2'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
    await flush();
    assert.match(ui.container.textContent!, /evaluation protocol/);
    await ui.close();
  });
  it('puts refinement and plan entry after the assessment', async () => {
    const ui = await mount();
    const content = ui.container.textContent!;
    assert.ok(content.indexOf('Refine this assessment') > content.indexOf('Next improvements'));
    assert.ok(content.indexOf('Evaluate your institution’s plan') > content.indexOf('Institutional AI capability'));
    const scope = ui.container.querySelector('section[aria-label="Refine this assessment"]')!;
    assert.equal(scope.querySelectorAll('input[required]').length, 2);
    assert.deepEqual(calls, []);
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
