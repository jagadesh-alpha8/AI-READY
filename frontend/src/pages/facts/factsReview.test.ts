/**
 * Extracted Facts Review focuses on facts (`npm test`): no Institution Profile card and no document-processing
 * warning (those live on Institution DNA and the AI Processing Monitor); the count, expert-queue link, search and
 * filters, bulk confirmation and table are still there. The profile card renders on Institution DNA.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';

const PROFILE = 'Institution profile';

const FACT = {
  id: 'f1', sprint_id: 's1', document_id: 'd1', field_name: 'Faculty Count', field_key: 'faculty_count',
  audit_field_id: '', value: 120, value_json: 120, normalized_value: 120, data_type: 'number', pillar: 'aiqif_c4',
  pillar_label: 'Faculty', owner_role: 'hod', source_document_id: 'd1', source_document_filename: 'ssr.pdf',
  source_page: '3', source_snippet: '120 faculty', confidence_score: 0.9, confidence: 0.9, confidence_reason: '',
  extraction_method: 'ai', status: 'extracted', aiqif_mapping_status: 'mapped', aiqif_mappings: [],
  fact_kind: 'ai_evidence', naac_metric: '', profile_field: '', profile_code: '', kind_needs_check: false,
  kind_reviewed_at: null, tagging_notes: [], open_evidence_request: null, evidence_for_gaps: [], owner_role_label: 'HOD',
  assigned_to: null, assigned_to_name: '', assigned_at: null, due_date: null, can_act: true, act_blocked_reason: '',
  reviewed_by: null, reviewed_at: null, created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z',
};
const PROCESSING = 'Document processing is incomplete';

describe('Extracted Facts Review', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter, Route, Routes } = await import('react-router-dom');
  const stubs = {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {}, setData() {} };',
    AuthContext: 'export const useAuth = () => ({ user: { id: "u", role: "super_admin" } });',
    SelectedSprintContext: 'export const useSelectedSprint = () => globalThis.__selected;',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  };
  const facts = await bundleComponent(new URL('./FactsReview.tsx', import.meta.url), stubs);
  const institution = await bundleComponent(new URL('../institutions/InstitutionDetail.tsx', import.meta.url), stubs);
  after(() => { facts.cleanup(); institution.cleanup(); });
  const g = globalThis as Record<string, unknown>;
  const ok = (data: unknown) => ({ data, loading: false, error: '', refetch() {}, setData() {} });
  const route = (path: string, url: string, el: unknown) => renderToStaticMarkup(React.createElement(MemoryRouter,
    { initialEntries: [url] }, React.createElement(Routes, null, React.createElement(Route, { path, element: el }))));

  it('shows only the fact review tools', () => {
    g.__resources = [
      ok({ count: 3, next: null, previous: null, results: [FACT] }),  // the facts page
      ok({ total: 3, status: { extracted: 3 }, pillar: {}, fact_kind: {}, aiqif_mapping_status: {}, owner_role: {},
        source_document: {}, confidence_band: {} }),             // facets
      ok(null),                                                   // processing summary (drives live refresh)
      ok(null),                                                   // CRI confidence tile
    ];
    const html = route('/sprint/:sprintId/facts', '/sprint/s1/facts', React.createElement(facts.mod.FactsReview));
    for (const t of ['Extracted Facts Review', '3 facts registered', 'AI-QIF expert queue', 'Search field ID',
      'Confirm all listed facts', 'Candidate &amp; Extracted Fact Records']) {
      assert.ok(html.includes(t), t);
    }
    for (const t of [PROFILE, PROCESSING]) assert.ok(!html.includes(t), `no ${t}`);
  });

  it('the institution profile card is on Institution DNA, for this college\'s sprint', () => {
    g.__selected = { sprintId: 's1', sprints: [{ id: 's1', institution_id: 'i1', sprint_code: 'SPR-1', created_at: '2026-10-20' }] };
    const suggestion = {
      current: null, confirmed: false,
      suggested: { institution_type: { value: 'engineering', candidates: [{ value: 'engineering' }] },
        autonomous_status: { value: 'autonomous', candidates: [{ value: 'autonomous' }] }, approval_bodies: ['AICTE'],
        programmes: [] },
    };
    g.__resources = [
      ok({ id: 'i1', name: 'MKCE', departments: [], leaders: [], systems: [], department_count: 0, program_count: 0,
        digital_maturity_label: '', digital_maturity_description: '', priorities: [] }),  // the institution
      ok(suggestion),                                                            // the profile suggestion
    ];
    const html = route('/institution-dna/:institutionId', '/institution-dna/i1',
      React.createElement(institution.mod.InstitutionDetail));
    assert.ok(html.includes('Read from the documents of sprint SPR-1'));
    // The card is mounted and asked for this sprint's profile suggestion (its form fills in after the first render).
    assert.equal((g.__resources as unknown[]).length, 0);
  });
});
