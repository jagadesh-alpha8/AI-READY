/**
 * Conflict comparison: `npm test` (Node's own test runner; no extra dependencies).
 * The view-model tests run conflictSides.ts directly. The render tests compile ConflictComparison.tsx with
 * esbuild (installed with Vite) and render it to HTML with react-dom/server.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';

import type { ConflictSide, Gap } from '../../types/gaps.ts';
import { NOT_AVAILABLE, describeSide, formatValue } from './conflictSides.ts';

const sideA: ConflictSide = {
  side: 'A', fact_id: 'fa', field_name: 'FDP certification %', value_at_detection: 62.5, current_value: 62.5,
  fact_status: 'extracted', document_id: 'da', document_name: 'SSR 2025.pdf', page: '45',
  snippet: '120 of 192 faculty completed the FDP.', confidence_score: 0.82,
};
const missingB: ConflictSide = {
  side: 'B', fact_id: null, field_name: '', value_at_detection: null, current_value: null, fact_status: '',
  document_id: null, document_name: null, page: null, snippet: null, confidence_score: null,
};
const rows = (side: ConflictSide) => Object.fromEntries(describeSide(side).rows.map((r) => [r.label, r.value]));

describe('describeSide', () => {
  it('shows value, document, page, snippet and confidence as recorded', () => {
    assert.deepEqual(rows(sideA), {
      'Extracted value': '62.5', 'Source document': 'SSR 2025.pdf', Page: '45',
      Snippet: '120 of 192 faculty completed the FDP.', Confidence: '82%',
    });
    assert.equal(describeSide(sideA).heading, 'Source A · FDP certification %');
    assert.equal(describeSide(sideA).valueNote, '');
  });

  it('says "Not available" for anything not recorded, and invents nothing', () => {
    const view = describeSide(missingB);
    assert.ok(view.rows.every((r) => r.value === NOT_AVAILABLE && r.missing));
    assert.equal(view.factId, null);
    assert.equal(rows({ ...sideA, page: '', snippet: '   ' }).Page, NOT_AVAILABLE);
    assert.equal(rows({ ...sideA, snippet: '   ' }).Snippet, NOT_AVAILABLE);
  });

  it('keeps the value found at detection and notes a later change', () => {
    const view = describeSide({ ...sideA, current_value: 60 });
    assert.equal(view.rows[0].value, '62.5');
    assert.equal(view.valueNote, 'The fact has changed since: now 60.');
  });

  it('falls back to the fact\'s current value, labelled, when no snapshot was stored', () => {
    const view = describeSide({ ...sideA, value_at_detection: null });
    assert.equal(view.rows[0].value, '62.5');
    assert.match(view.valueNote, /no value was stored/);
  });

  it('formats structured values and a zero confidence', () => {
    assert.equal(formatValue({ ug: 10 }), '{"ug":10}');
    assert.equal(formatValue(0), '0');
    assert.equal(rows({ ...sideA, confidence_score: 0 }).Confidence, '0%');
  });
});

describe('ConflictComparison (rendered)', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { mod, cleanup } = await bundleComponent(new URL('./ConflictComparison.tsx', import.meta.url), {
    // The dialog's API calls; the comparison itself renders from the gap it is given.
    'api/gaps': 'const f = () => Promise.resolve({ data: {} }); export const getGap = f, chooseConflictValue = f;',
  });
  after(cleanup);
  const { ConflictComparison } = mod;

  const gap = {
    id: 'g1', title: 'Conflicting values for FDP %', description: 'The two documents disagree.',
    status: 'open', priority: 'high', conflict_confidence: 0.9,
    conflict_sides: [sideA, { ...missingB, value_at_detection: 58, snippet: '<b>112</b> <script>alert(1)</script>' }],
  } as unknown as Gap;
  const html = renderToStaticMarkup(React.createElement(ConflictComparison, { gap }));

  it('lays the sides out next to each other on wide screens and stacked on small ones', () => {
    assert.match(html, /class="grid grid-cols-1 lg:grid-cols-2/);
    assert.equal((html.match(/<section/g) || []).length, 2);
    assert.match(html, /aria-label="Source A · FDP certification %"/);
    assert.match(html, /aria-label="Source B"/);
  });

  it('shows each side\'s citation, and "Not available" where it is missing', () => {
    for (const text of ['SSR 2025.pdf', '45', '82%', '62.5', '58', 'Conflict check confidence: 90%']) {
      assert.ok(html.includes(text), text);
    }
    assert.equal((html.match(/Not available/g) || []).length, 3); // side B: document, page, confidence
  });

  it('offers "Use this value" only to someone who may choose, and lists every competing value', () => {
    assert.ok(!html.includes('Use this value'));  // no onChoose: the read-only comparison
    const three = { ...gap, conflict_candidates: [sideA, { ...sideA, side: 'B', fact_id: 'f2', current_value: 30 },
      { ...sideA, side: 'C', fact_id: 'f3', current_value: 120 }] } as unknown as Gap;
    const chooser = renderToStaticMarkup(React.createElement(ConflictComparison, { gap: three, onChoose() {} }));
    assert.equal((chooser.match(/<section/g) || []).length, 3);
    assert.equal((chooser.match(/Use this value/g) || []).length, 3);
  });

  it('renders source text as text, never as markup', () => {
    assert.ok(!html.includes('<script>'));
    assert.ok(!html.includes('<b>112'));
    assert.ok(html.includes('&lt;b&gt;112&lt;/b&gt; &lt;script&gt;alert(1)&lt;/script&gt;'));
  });
});
