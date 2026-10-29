/**
 * Fact verification UI (`npm test`): the table cell and the "Why?" breakdown keep extraction confidence,
 * grounding, validation and other sources apart, and label deterministic checks as such.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import { describeSide } from '../gaps/conflictSides.ts';

const RUN = {
  id: 'r1', source: 'extraction', mode: 'shadow', outcome: 'invalid', value: '6,909',
  reason: 'The value 6,909 contradicts its own quote, which says 6,910.',
  citation: { document_name: 'ssr.pdf', document_version: 2, source_page: '3', source_snippet: 'Sub total 6,910' },
  extraction_confidence: 0.97,
  grounding: { status: 'value_conflicts_quote', citation: 'ok', quote: 'exact', value_support: 'conflicts_quote',
    score: 1, detail: ['The value 6,909 contradicts its own quote, which says 6,910.'], quote_numbers: ['6910'],
    kind: 'deterministic' },
  validation: { status: 'fail', kind: 'deterministic', checks: [
    { code: 'arithmetic', label: 'Calculation', status: 'fail', kind: 'deterministic',
      detail: '6,910 + 234 = 7,144 -- Arithmetic FAIL', formula: '6,910 + 234' }] },
  derivation: { status: 'fail', formula: '6,910 + 234', computed: '7144', stated: '6909', includes: ['integrated'],
    excludes: [], detail: [], inputs: [
      { label: 'Subtotal', value: '6,910', number: '6910', document_id: 'd', document_name: 'ssr.pdf',
        document_version: 2, source_page: '3', source_snippet: 'Sub total 6,910',
        grounding: { status: 'exact', quote: 'exact', value_support: 'in_quote', detail: [] } },
      { label: 'Integrated', value: '234', number: '234', document_id: 'd', document_name: 'ssr.pdf',
        document_version: 2, source_page: '5', source_snippet: '234 students',
        grounding: { status: 'exact', quote: 'exact', value_support: 'in_quote', detail: [] } }] },
  cross_source: { status: 'no_other_source', compared: [], not_comparable: [] },
  scope: { period: '2022-23', population: [], unit: 'count', includes: [], excludes: [] },
  ai_assessments: [], risk_level: 'high', precedent: null, automation_decision: 'review',
  automation_reason: 'Verification: invalid', blockers: ['Verification: invalid'], created_at: '2026-10-29',
};

describe('fact verification', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const stubs = {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resource;',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  };
  const ui = await bundleComponent(new URL('./FactVerification.tsx', import.meta.url), stubs);
  after(() => ui.cleanup());
  const g = globalThis as Record<string, unknown>;
  const fact = {
    id: 'f1', field_name: 'Total students', field_key: 'total_students', value: '6,909', original_value: '6,909',
    value_origin: 'calculated',
    verification: { status: 'invalid', status_label: 'Invalid', extraction_confidence: 0.97,
      grounding: 'value_conflicts_quote', validation: 'fail', cross_source: 'no_other_source', risk_level: 'high',
      automation_decision: 'review', automation_reason: 'Verification: invalid', verified_at: null },
  };

  it('the cell shows the outcome and the separate results', () => {
    const html = renderToStaticMarkup(React.createElement(ui.mod.VerificationCell, { fact, onOpen() {} }));
    for (const t of ['Invalid', 'Value contradicts its own quote', 'checks fail', 'Why?']) assert.ok(html.includes(t), t);
  });

  it('a fact never verified says so', () => {
    const html = renderToStaticMarkup(React.createElement(ui.mod.VerificationCell, { fact: { ...fact, verification: null }, onOpen() {} }));
    assert.ok(html.includes('Not verified yet'));
  });

  it('the breakdown keeps confidence apart from the deterministic checks and shows the formula', () => {
    g.__resource = { data: { latest: RUN, precedent: null, earlier: [] }, loading: false, error: '', refetch() {} };
    const html = renderToStaticMarkup(React.createElement(ui.mod.FactVerificationModal, { fact, onClose() {} }));
    for (const t of ['Extraction confidence', 'model estimate', '97%', 'never confirms a fact on its own',
      'Source grounding', 'deterministic', 'ssr.pdf v2, page 3', 'contradicts its own quote, which says 6,910',
      'Validation', '6,910 + 234', '7144', 'FAIL', 'page 5', 'Includes: integrated',
      'shadow mode (rules record only)']) {
      assert.ok(html.includes(t), t);
    }
  });
});

describe('conflict sides show what each value measures', () => {
  it('version, period, population and checks appear when recorded', () => {
    const view = describeSide({
      side: 'A', fact_id: 'f', field_name: 'Students', value_at_detection: 7144, current_value: 7144,
      fact_status: 'extracted', document_id: 'd', document_name: 'ssr.pdf', page: '3', snippet: 'x',
      confidence_score: 0.9, document_version: 2, superseded: false, period: '2022-23', population: ['undergraduate'],
      validation_status: 'pass', grounding_status: 'exact',
    });
    const rows = Object.fromEntries(view.rows.map((r) => [r.label, r.value]));
    assert.equal(rows.Version, 'v2');
    assert.equal(rows.Period, '2022-23');
    assert.equal(rows.Population, 'undergraduate');
    assert.equal(rows.Checks, 'pass · quote exact');
  });
});
