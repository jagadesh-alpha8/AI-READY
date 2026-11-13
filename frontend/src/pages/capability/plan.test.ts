import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { bundleComponent } from '../../testing/bundle.ts';

let bundle: Awaited<ReturnType<typeof bundleComponent>>;
before(async () => {
  bundle = await bundleComponent(new URL('./PlanWorkspace.tsx', import.meta.url), {
    './CapabilityWorkspace': 'export const useCapabilityRead = () => { throw new Error("No read during comparison rendering"); };',
    '../../api/capability': ['listPlanEvaluations', 'getPlanEvaluation', 'startPlanEvaluation', 'cancelPlanEvaluation', 'downloadPlanReport']
      .map((n) => `export const ${n} = () => { throw new Error("No API call during comparison rendering"); };`).join('\n'),
    '../../utils/access': 'export const useAccess = () => ({ can: () => true });',
  });
});
after(() => bundle.cleanup());
it('renders actual standing separately from both hypothetical plans, with retained assumptions and escaped prose', () => {
  const result = (lower: number, upper: number) => ({ lower, upper, exact_score: lower === upper ? lower : null,
    pillars: [{ code: 'AIQIF-C4', lower, upper }] });
  const plan = (lower: number, upper: number) => ({ text: 'Synthetic revised plan <script>bad()</script>', evaluation: {
    baseline: result(10, 60), accepted: [{ condition_id: 'criterion1', rationale: 'If assessed work demonstrates literacy', phase: 'results', assumptions: ['Measured competence is demonstrated, not assumed from attendance'] }],
    rejected: [{ mapping: {}, reason: 'A vague workshop does not establish universal provision' }],
    scenarios: { implementation: { result: result(lower, upper), paired_change: { lower: 0, upper: 5, basis: 'Paired conditions, not guaranteed gains' } },
      results: { result: result(lower + 5, upper), paired_change: { lower: 0, upper: 10, basis: 'Paired conditions, not guaranteed gains' } } },
  } });
  const data = { comparison: { original: plan(15, 65), improved: plan(20, 70), comparison_basis: 'Same frozen baseline, scope and method',
    improvement: { constraint_note: 'No budget specified; effort not costed', changes: [{ operation: 'change', action: 'Add practical assessment', why: 'Attendance does not establish competence', suggested_owner: 'Programme lead', dependencies: ['Check teaching support'], completion_evidence: 'Assessed work', resource_note: 'Reuse event time; extra effort is uncosted' }] },
    limitations: ['Model interpretation remains fallible'] } };
  const html = renderToStaticMarkup(React.createElement(bundle.mod.PlanComparisonView, { data }));
  assert.match(html, /Current assessed standing: 10.00–60.00/);
  assert.match(html, /Your original plan/);
  assert.match(html, /Suggested improved plan/);
  assert.match(html, /Delivery only/);
  assert.match(html, /With results assumptions/);
  assert.match(html, /Faculty and staff/);
  assert.match(html, /Measured competence/);
  assert.match(html, /A vague workshop does not establish universal provision/);
  assert.match(html, /No budget specified/);
  assert.doesNotMatch(html, /<script>/);
});

it('keeps a saved original review visible without inventing a completed improved plan', () => {
  const baseline = { lower: 0, upper: 100, exact_score: null, pillars: [{ code: 'AIQIF-C4', lower: 0, upper: 100 }] };
  const plan = { evaluation: { baseline, accepted: [], rejected: [{ reason: 'Workshop attendance does not establish competence.' }],
    note: 'Conditional requirements must be demonstrated. Actual assessment unchanged.',
    scenarios: { implementation: { result: baseline }, results: { result: baseline } } } };
  const html = renderToStaticMarkup(React.createElement(bundle.mod.OriginalPlanReview, { plan }));
  assert.match(html, /Saved original plan review/);
  assert.match(html, /No improved plan is established/);
  assert.match(html, /not a predicted score or guaranteed gain/);
  assert.match(html, /Faculty and staff/);
  assert.match(html, /Workshop attendance does not establish competence/);
  assert.doesNotMatch(html, /Suggested improved plan/);
});

it('shows part-credit plans as one score and gain, with priority-plan coverage', () => {
  const result = { lower: 0, upper: 100, exact_score: null, pillars: [{ code: 'AIQIF-C4', lower: 0, upper: 100 }] };
  const score = (value: number, gain: number) => ({ score: value, gain, pillars: [{ code: 'AIQIF-C4', score: value, gain }], requirements: [], basis: 'Part-credit score' });
  const plan = (value: number) => ({ text: 'Plan', evaluation: {
    baseline: result, baseline_score: 31.4, accepted: [], rejected: [], note: 'Conditional.',
    priority_coverage: { covered: ['a'], missed: ['b', 'c'], outside_priority_plan: ['d'], target: 40, priority_projected_score: 40.2 },
    scenarios: { implementation: { result, paired_change: { lower: 0, upper: 5, basis: 'b' }, score: score(value, value - 31.4) },
      results: { result, paired_change: { lower: 0, upper: 9, basis: 'b' }, score: score(value + 2, value - 29.4) } } } });
  const data = { comparison: { original: plan(33.4), improved: plan(36.4), comparison_basis: 'Same baseline',
    improvement: { constraint_note: '', changes: [] }, limitations: [] } };
  const html = renderToStaticMarkup(React.createElement(bundle.mod.PlanComparisonView, { data }));
  assert.match(html, /Current score: 31.4 \/ 100/);
  assert.match(html, /33.4 \/ 100 \(\+2.0\)/);
  assert.match(html, /complete 1 of the 3 priority requirements/);
  assert.match(html, /40.2 \/ 100/);
  assert.doesNotMatch(html, /Paired conditional change/);
  assert.doesNotMatch(html, /unresolved range/);
});
