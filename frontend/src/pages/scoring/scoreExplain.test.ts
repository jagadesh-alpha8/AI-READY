/**
 * Live CRI Preview (`npm test`): the explanations next to each score, the factor breakdown, and the separate
 * Benchmark Assessment section. Values come from fixtures shaped like the score / assessment APIs.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { EvidenceCoverage, PillarScore, Scorecard } from '../../types/scoring.ts';
import {
  adjustedReason, confidenceBand, coverageCounts, coverageReason, rawCriZeroReason, reportingPeriod, weightLabel,
  weightedTotal,
} from './scoreExplain.ts';

const pillar = (over: Partial<PillarScore>): PillarScore => ({
  pillar: 'aiqif_c1', label: 'Institutional AI Strategy & Governance', weight: 0.12, raw_score: 50, weighted_score: 6,
  confidence_score: 0.9, score: 50, confidence: 0.9, status: 'developing', evidence_count: 3, gap_count: 1,
  calculation_version: 'v1', calculated_at: null, ...over,
});

const coverage = (over: Partial<EvidenceCoverage>): EvidenceCoverage => ({
  formula_version: 'AIQIF-COV-1', formula: 'Coverage-adjusted CRI = Raw CRI x (covered / total)', status: 'incomplete',
  ratio: 0, covered_count: 0, applicable_count: 36, excluded_count: 0, unresolved_applicability_count: 36,
  covered_weight: 0, applicable_weight: 1, weights_source: 'equal_within_criterion', weights_note: 'Equal weights.',
  release_label: null, release_hash: null, applicability_note: 'No benchmark release is published yet.',
  mappings_awaiting_review: 0, indicators: [], ...over,
});

const card = (over: Partial<Scorecard>): Scorecard => ({
  sprint_id: 's', overall_cri: 33.26, raw_cri: 33.26, coverage_adjusted_cri: 0, evidence_coverage: coverage({}),
  overall_confidence: 0.88, cri_score: 33.26, cri_confidence: 0.88, calculation_version: 'v1', calculated_at: null,
  pillar_scores: [], strengths: [], weaknesses: [], unresolved_blocking_gaps: [],
  evidence_metrics: { confirmed_facts: 843, corrected_facts: 0, total_extracted_facts: 844, documents_processed: 189,
    unresolved_gaps: 15 }, ...over,
});

describe('explanations', () => {
  it('keeps the existing confidence band', () => {
    assert.equal(confidenceBand(0.88), 'High (>=80%)');
    assert.equal(confidenceBand(0.79), 'Building (below 80%)');
    assert.equal(confidenceBand(null), '—');
  });

  it('labels factor weights out of 1000', () => {
    assert.equal(weightLabel(0.12), '120 / 1000 (12%)');
    assert.equal(weightLabel(0.125), '125 / 1000 (12.5%)');
  });

  it('counts covered, uncovered, excluded and unresolved from the API counts', () => {
    assert.deepEqual(coverageCounts(coverage({ covered_count: 12, applicable_count: 34, excluded_count: 2,
      unresolved_applicability_count: 5 })), { covered: 12, uncovered: 22, excluded: 2, unresolved: 5, applicable: 34 });
  });

  it('says why coverage is 0 or missing', () => {
    assert.match(coverageReason(null), /Recalculate/);
    assert.match(coverageReason(coverage({ ratio: null })), /No AI-QIF indicator is applicable/);
    assert.match(coverageReason(coverage({ mappings_awaiting_review: 7 })), /7 AI-QIF tag\(s\).*waiting for a reviewer/);
    assert.match(coverageReason(coverage({})), /no confirmed or corrected fact carries a reviewer-confirmed AI-QIF tag/);
    assert.equal(coverageReason(coverage({ ratio: 0.3, covered_count: 10 })), '');
  });

  it('says why the coverage-adjusted CRI is what it is', () => {
    assert.match(adjustedReason(card({})), /^0 because evidence coverage is 0%/);  // the live site's case
    assert.match(adjustedReason(card({ raw_cri: 0, evidence_metrics: { ...card({}).evidence_metrics, confirmed_facts: 0 } })),
      /0 because the Raw CRI is 0/);
    assert.match(adjustedReason(card({ coverage_adjusted_cri: null, evidence_coverage: {} })), /Recalculate/);
    assert.equal(adjustedReason(card({ coverage_adjusted_cri: 10, evidence_coverage: coverage({ ratio: 0.3, covered_count: 11 }) })),
      'Raw CRI 33.26 reduced to 30% because only 11 of 36 applicable indicators are covered.');
  });

  it('says why the Raw CRI is 0', () => {
    assert.equal(rawCriZeroReason(card({})), '');
    const none = card({ raw_cri: 0, evidence_metrics: { confirmed_facts: 0, corrected_facts: 0, total_extracted_facts: 40,
      documents_processed: 3, unresolved_gaps: 2 } });
    assert.match(rawCriZeroReason(none), /None of the sprint's 40 extracted facts is confirmed/);
  });

  it('adds the contributions and shows the reporting period', () => {
    assert.equal(weightedTotal([pillar({ weighted_score: 6 }), pillar({ weighted_score: 4.26 })]), 10.26);
    assert.equal(reportingPeriod({ academic_year: '2026-27', start_date: '2026-07-01', target_completion_date: null }),
      'Academic year 2026-27 · 2026-07-01 to ?');
    assert.equal(reportingPeriod({}), '');
  });
});

describe('rendered', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const stubs = {
    // Each useApiResource call takes the next prepared result (the section's cycles, then the scorecard).
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {} };',
    AuthContext: 'export const useAuth = () => ({ user: globalThis.__user });',
    // The real API modules load; their HTTP client never sends anything (no effects run when rendering to HTML).
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  };
  const breakdown = await bundleComponent(new URL('./FactorBreakdown.tsx', import.meta.url), stubs);
  const section = await bundleComponent(new URL('./BenchmarkAssessmentSection.tsx', import.meta.url), stubs);
  const tile = await bundleComponent(new URL('./CriConfidenceTile.tsx', import.meta.url), stubs);
  after(() => { breakdown.cleanup(); section.cleanup(); tile.cleanup(); });
  const g = globalThis as Record<string, unknown>;
  const ok = (data: unknown) => ({ data, loading: false, error: '', refetch() {} });
  const render = (el: unknown) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el as React.ReactElement));

  it('the breakdown lists each factor with score, weight and contribution adding up to the Raw CRI', () => {
    const html = render(React.createElement(breakdown.mod.FactorBreakdown, {
      rawCri: 10.26, pillars: [pillar({}), pillar({ pillar: 'aiqif_c2', label: 'Responsible AI', weight: 0.1, raw_score: 42.6,
        weighted_score: 4.26, evidence_count: 0, gap_count: 0, status: 'not_started' })],
    }));
    for (const t of ['Institutional AI Strategy &amp; Governance', '50 / 100', '120 / 1000 (12%)', '100 / 1000 (10%)',
      'Raw CRI (sum of contributions)', '10.26', 'No confirmed or corrected fact backs this factor yet.']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('the Extracted Facts Review tile shows the score API confidence, its band and when it was calculated', () => {
    g.__user = { id: 'u', role: 'consultant' };
    g.__resources = [ok(card({ calculated_at: '2026-10-22T10:00:00Z' }))];
    const html = render(React.createElement(tile.mod.CriConfidenceTile, { sprintId: 's' }));
    for (const t of ['CRI Evidence Confidence', '88%', 'High (&gt;=80%)', 'until the CRI is recalculated', 'href="/sprint/s/score"']) {
      assert.ok(html.includes(t), t);
    }
    g.__resources = [ok(null)];
    assert.ok(render(React.createElement(tile.mod.CriConfidenceTile, { sprintId: 's' })).includes('—'));
  });

  const cycle = { id: 'c1', name: 'MKCE 2026', status: 'in_progress', status_label: 'Collecting evidence',
    release_label: 'AI-QIF 1.0', opens_on: '2026-08-01', closes_on: null };

  it('with no assessment: a clear empty state and where to start one', () => {
    g.__user = { id: 'u', role: 'consultant' };
    g.__resources = [ok([])];
    const html = render(React.createElement(section.mod.BenchmarkAssessmentSection, { institutionId: 'i1', institutionName: 'MKCE' }));
    assert.ok(html.includes('Benchmark Assessment (separate from the sprint CRI)'));
    assert.ok(html.includes('No Benchmark Assessment has been started for this college yet'));
    assert.ok(html.includes('href="/benchmark-assessment"'));
  });

  it('a college user sees the cycle and its release, and why scores are not shown before finalizing', () => {
    g.__user = { id: 'u', role: 'iqac_coordinator' };
    g.__resources = [ok([cycle])];
    const html = render(React.createElement(section.mod.BenchmarkAssessmentSection, { institutionId: 'i1', institutionName: 'MKCE' }));
    assert.ok(html.includes('MKCE 2026') && html.includes('AI-QIF 1.0'));
    assert.ok(html.includes('The scorecard is shared once InGage finalizes this assessment'));
  });

  it('staff see the scorecard with the four scores per benchmark', () => {
    g.__user = { id: 'u', role: 'consultant' };
    const scorecard = { ...cycle, release_hash: 'abcdef0123456789', finalized_at: null, finalized_by: null, method: 'stage5-v1',
      scoring_model: null, benchmarks: [{ benchmark_code: 'AIQIF-C1.1', title: 'AI Vision', pillar: 'aiqif_c1', kind: 'proposed',
        target_level: 'L2', snapshot_hash: 'x', assessment: { current_level: 'L3', compliance_score: '80.00',
          maturity_score: '33.30', evidence_confidence_score: '70.00', outcome_score: null, composite_score: null,
          detail: { composite: 'No approved weights.' } } }] };
    g.__resources = [ok([cycle]), ok(scorecard)];
    const html = render(React.createElement(section.mod.BenchmarkAssessmentSection, { institutionId: 'i1', institutionName: 'MKCE' }));
    for (const t of ['Compliance', 'Maturity', 'Evidence confidence', 'Outcome', 'Composite', '>80<', '>33.3<', '>70<', 'No approved weights.']) {
      assert.ok(html.includes(t), t);
    }
  });
});
