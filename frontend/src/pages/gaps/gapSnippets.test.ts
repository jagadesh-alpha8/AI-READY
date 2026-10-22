/**
 * The Gap Dashboard's Source Snippet column and its search (`npm test`).
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { ConflictSide, Gap } from '../../types/gaps.ts';
import { PREVIEW_CHARS, gapSnippets, snippetPreview, snippetSearchText } from './gapSnippets.ts';

const LONG = 'The institution reported 120 of 192 faculty members completing the AI foundation FDP in the '
  + 'academic year 2025-26, as recorded in the signed attendance register kept by the IQAC office.';

const side = (s: 'A' | 'B', over: Partial<ConflictSide> = {}): ConflictSide => ({
  side: s, fact_id: `f${s}`, field_name: 'Year of Establishment', value_at_detection: null, current_value: null,
  fact_status: 'extracted', document_id: `d${s}`, document_name: `${s === 'A' ? 'AICTE Mgmt' : 'AICTE Marine'}.pdf`,
  page: s === 'A' ? '12' : '11', snippet: `Year of Establishment ${s === 'A' ? 1998 : 2007}`, confidence_score: 1,
  ...over,
});

const gap = (over: Partial<Gap>): Gap => ({
  id: 'g', gap_type: 'unconfirmed_fact', source_fact_id: 'f1', conflict_sides: null,
  source_snippet: '120 of 192 faculty completed the FDP.', source_page: '45', ...over,
} as Gap);

describe('gapSnippets', () => {
  it('a gap on a fact: its snippet and page', () => {
    assert.deepEqual(gapSnippets(gap({})),
      [{ label: '', document: null, page: '45', snippet: '120 of 192 faculty completed the FDP.' }]);
  });

  it('a conflict: Source A and Source B apart, each with its document and page', () => {
    const entries = gapSnippets(gap({ gap_type: 'conflict', conflict_sides: [side('A'), side('B')] }));
    assert.deepEqual(entries.map((e) => [e.label, e.document, e.page, e.snippet]), [
      ['Source A', 'AICTE Mgmt.pdf', '12', 'Year of Establishment 1998'],
      ['Source B', 'AICTE Marine.pdf', '11', 'Year of Establishment 2007'],
    ]);
  });

  it('nothing recorded stays empty -- no fact, blank snippet, or a conflict with no side B', () => {
    assert.deepEqual(gapSnippets(gap({ source_fact_id: null, source_snippet: null, source_page: null })), []);
    assert.equal(gapSnippets(gap({ source_snippet: '  ' }))[0].snippet, null);
    const noB = gapSnippets(gap({ gap_type: 'conflict', conflict_sides: [side('A'),
      side('B', { fact_id: null, document_name: null, page: null, snippet: null })] }));
    assert.deepEqual([noB[1].document, noB[1].page, noB[1].snippet], [null, null, null]);
  });
});

describe('snippetPreview', () => {
  it('keeps a short snippet whole', () => {
    assert.deepEqual(snippetPreview('Year of Establishment 1998'), { text: 'Year of Establishment 1998', truncated: false });
  });

  it('cuts a long one at a word, under the limit, and marks it', () => {
    const p = snippetPreview(LONG);
    assert.ok(p.truncated && p.text.endsWith('…') && p.text.length <= PREVIEW_CHARS + 1);
    assert.ok(LONG.startsWith(p.text.slice(0, -1)));
    assert.ok(!p.text.slice(0, -1).endsWith(' '));
  });

  it('flattens line breaks from the document', () => {
    assert.equal(snippetPreview('2.1 12243\nNumber of students').text, '2.1 12243 Number of students');
  });
});

describe('search', async () => {
  const { mod, cleanup } = await bundleComponent(new URL('../../components/TableFilters.tsx', import.meta.url));
  after(cleanup);
  const matches = (term: string, g: Gap) => mod.matchesSearch(term, g.title, ...snippetSearchText(g));

  it('finds a gap by its fact\'s snippet', () => {
    assert.ok(matches('192 faculty', gap({ title: 'Needs confirmation: FDP %' })));
    assert.ok(!matches('attendance register', gap({ title: 'Needs confirmation: FDP %' })));
  });

  it('finds a conflict by either side\'s snippet or document', () => {
    const conflict = gap({ title: 'Conflicting values', gap_type: 'conflict', conflict_sides: [side('A'), side('B')] });
    assert.ok(matches('2007', conflict));
    assert.ok(matches('marine', conflict));
    assert.ok(!matches('2011', conflict));
  });
});

describe('GapSnippetCell (rendered)', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { mod, cleanup } = await bundleComponent(new URL('./GapSnippetCell.tsx', import.meta.url));
  after(cleanup);
  const render = (g: Gap) => renderToStaticMarkup(React.createElement(mod.GapSnippetCell, { gap: g }));

  it('shows a short preview with the page, the full text on hover, and a toggle for the rest', () => {
    const html = render(gap({ source_snippet: LONG, source_page: '45' }));
    assert.ok(html.includes(snippetPreview(LONG).text));
    assert.ok(html.includes(`title="${LONG}"`));
    assert.ok(html.includes('(p. <!-- -->45<!-- -->)') || html.includes('(p. 45)'));
    assert.match(html, /aria-expanded="false"[^>]*>Show full snippet</);
  });

  it('no toggle for a snippet that fits', () => {
    assert.ok(!render(gap({})).includes('Show full snippet'));
  });

  it('a conflict lists Source A and Source B apart, with documents and pages', () => {
    const html = render(gap({ gap_type: 'conflict', conflict_sides: [side('A'), side('B')] }));
    const a = html.indexOf('Source A');
    const b = html.indexOf('Source B');
    assert.ok(a >= 0 && b > a);
    for (const t of ['AICTE Mgmt.pdf', 'AICTE Marine.pdf', 'Year of Establishment 1998', 'Year of Establishment 2007']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('shows "—" with no fact, and for a side or snippet that was not recorded', () => {
    assert.equal(render(gap({ source_fact_id: null, source_snippet: null, source_page: null })),
      '<span class="text-ink-500">—</span>');
    assert.ok(render(gap({ source_snippet: null, source_page: null })).includes('>—</p>'));
    const html = render(gap({ gap_type: 'conflict', conflict_sides: [side('A'),
      side('B', { fact_id: null, document_name: null, page: null, snippet: null })] }));
    assert.ok(html.includes('Source B') && html.includes('>—</p>'));
  });

  it('renders snippet text as text, never as markup', () => {
    const html = render(gap({ source_snippet: '<img src=x onerror=alert(1)> 120 of 192' }));
    assert.ok(!html.includes('<img'));
    assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt; 120 of 192'));
  });
});
