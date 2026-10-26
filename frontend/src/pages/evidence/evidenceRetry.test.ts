/**
 * Evidence AI assessment retry (`npm test`): a failed assessment offers "Retry AI assessment" to a reviewer, a running
 * retry shows progress with the action disabled, a ready one shows the advisory result, and a repeated failure reads
 * clearly. Fixtures follow GET /evidence-requests/<id>.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import type { EvidenceLink, EvidenceRequestDetail } from '../../types/index.ts';
import { bundleComponent } from '../../testing/bundle.ts';

const link = (over: Partial<EvidenceLink>): EvidenceLink => ({
  id: 'e1', document: null, document_filename: 'Text evidence', document_status: null, page_count: null,
  uploaded_for_request: false, source_page: '', source_snippet: '', submitted_text: '120 of 192 faculty completed.',
  source_context: 'HR register', note: '', submitted_by: 'hod', submitted_by_name: 'HOD',
  analysis_status: 'failed', analysis_outcome: '', analysis_summary: '', analysis_quote: '', analysis_page_number: null,
  analysis_document_reference: '', analysis_suggested_value: null, analysis_confidence: null,
  analysis_error: 'The AI service timed out before it answered. Retry the assessment when the service is available.',
  analysis_attempts: 1, analysis_retry_count: 0, analysis_started_at: null, analysis_finished_at: null,
  analysis_retry_requested_at: null, status: 'submitted', review_reason: '', reviewed_by: null, reviewed_by_name: '',
  reviewed_at: null, created_at: '2026-10-26T10:00:00Z', ...over,
} as EvidenceLink);

const detail = { id: 'r1', fact_value: 62.5, suggested_facts: [] } as unknown as EvidenceRequestDetail;

describe('Retry AI assessment', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const page = await bundleComponent(new URL('./EvidenceRequests.tsx', import.meta.url), {
    'hooks/useApiResource': 'export const useApiResource = () => ({ data: null, loading: false, error: "", refetch() {} });',
    AuthContext: 'export const useAuth = () => ({ user: { id: "admin", role: "institution_admin" } });',
    SelectedSprintContext: 'export const useSelectedSprint = () => ({ selectedSprintId: null });',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  });
  after(() => page.cleanup());
  const render = (l: EvidenceLink, canDecide = true) => renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(page.mod.EvidenceCard, { link: l, detail, busy: false, canDecide,
      onDecide: async () => true, onRetry: async () => undefined })));

  it('offers the retry to a reviewer after a failure, with a readable error', () => {
    const html = render(link({}));
    for (const t of ['Analysis failed', 'AI assessment failed', 'timed out', 'Retry AI assessment']) {
      assert.ok(html.includes(t), t);
    }
  });

  it('does not offer it to the submitter or anyone who cannot decide', () => {
    assert.ok(!render(link({}), false).includes('Retry AI assessment'));
  });

  it('shows a running retry and disables the action', () => {
    const html = render(link({ analysis_status: 'processing', analysis_retry_count: 1 }));
    for (const t of ['Retrying AI assessment', 'Retrying the AI assessment (retry 1)', 'Retry in progress']) {
      assert.ok(html.includes(t), t);
    }
    assert.match(html, /<button[^>]*disabled[^>]*>Retry in progress/);
    assert.ok(!html.includes('>Retry AI assessment<'));
  });

  it('a queued retry shows as in progress too', () => {
    assert.ok(render(link({ analysis_status: 'pending', analysis_retry_count: 1 })).includes('Retry queued'));
  });

  it('a ready assessment is advisory, ready for a human decision', () => {
    const html = render(link({ analysis_status: 'ready', analysis_outcome: 'supports', analysis_confidence: 0.93,
      analysis_summary: 'The register supports the rate.', analysis_error: '', analysis_retry_count: 1 }));
    for (const t of ['Ready for review', 'AI assessment (advisory)', 'AI never confirms the fact']) {
      assert.ok(html.includes(t), t);
    }
    assert.ok(!html.includes('Retry AI assessment'));
  });

  it('a repeated failure says so and can be retried again', () => {
    const html = render(link({ analysis_retry_count: 2,
      analysis_error: 'The AI service was temporarily unavailable. Retry the assessment in a little while.' }));
    for (const t of ['AI assessment failed again', 'after 2 retries', 'temporarily unavailable', 'Retry AI assessment']) {
      assert.ok(html.includes(t), t);
    }
  });
});
