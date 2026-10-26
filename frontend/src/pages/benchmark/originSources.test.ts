/**
 * Read-only Benchmark Studio (`npm test`): exactly three sections; no create / edit / delete / draft / approve /
 * publish / AI controls; source mappings only where the workbook gives them ("Source mapping not provided."
 * otherwise); applicability only from a saved profile. Fixtures are shaped like the API responses.
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import type { ApplicabilityPreview, IndicatorProvenance, SourceDocument } from '../../api/benchmarks.ts';
import { bundleComponent } from '../../testing/bundle.ts';

const workbookOrigin = {
  type: 'framework_import' as const, label: 'Initial framework (manager-provided workbook)', recorded: 'row',
  workbook: 'InGage_AI_QIF_Benchmark_Master_v1_0_AI_Criteria.xlsx', framework: 'AIQIF-V1.0',
  framework_version: 'AI-QIF v1.0', sheet: 'AI Benchmark Master', row: 2, indicator_code: 'AIQIF-C1.1',
  imported_at: '2026-10-15T09:30:32Z', imported_by: 'import_aiqif', workbook_source_refs: [],
};

const prov = (over: Partial<IndicatorProvenance>): IndicatorProvenance => ({
  benchmark_code: 'AIQIF-C1.1', version_label: 'AI-QIF v1.0', status: 'draft', origin: workbookOrigin,
  source_references: [], source_document_linked: false, naac_crosswalk_count: 2, frozen_in: null, releases: [], ...over,
});

const mapping = {
  requirement_code: 'UGC-005-R001', statement: 'Publish an AI-use policy.', source_code: 'UGC-005',
  source_title: 'UGC Regulations', source_version: '2018', source_version_status: 'active', page: 3,
  source_quote: 'Every institution shall publish a policy', quote_in_source_text: true,
  relationship: 'primary' as const, relationship_label: 'Primary', requirement_origin: 'manager_workbook' as const,
  workbook_ref: { workbook: 'AIQIF.xlsx', workbook_sha256: 'ab', sheet: 'AI-QIF Source References', row: 2 },
  accepted_by: null, accepted_at: null, linked_by: null, linked_at: null,
};

const doc = (over: Partial<SourceDocument>): SourceDocument => ({
  id: 'd', source_code: 'UGC-005', title: 'UGC Plagiarism Regulations, 2018', authority: 'UGC', authority_name: 'UGC',
  authority_kind: 'regulatory', category: '', source_role: '', source_role_label: '', document_type: '', applies_to: '',
  official_url: '', licensed_content: false, review_cadence_months: 12, version_count: 1, latest_version: null,
  review_flag_count: 0, linked_indicators: [], delete_blockers: [], ...over,
});

/** Labels that would mean a master-data action is offered. */
const ACTIONS = ['Add source', 'Edit', 'Delete', 'Approve', 'Withdraw', 'Draft requirements', 'Confirm', 'Publish',
  'Write L3', 'Link an approved requirement', 'Cite a source', 'Suggest', 'with AI', 'Unlink', 'Record where'];
const noActions = (html: string) => {
  for (const t of ACTIONS) assert.ok(!html.includes(`>${t}`) && !html.includes(`${t}<`), `no "${t}" control`);
};

describe('read-only Benchmark Studio', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { MemoryRouter } = await import('react-router-dom');
  const stubs = {
    'hooks/useApiResource': 'export const useApiResource = () => globalThis.__resources.shift() || { data: null, loading: false, error: "", refetch() {} };',
    AuthContext: 'export const useAuth = () => ({ user: { role: "super_admin" } });',
    './client': 'const f = () => new Promise(() => {}); export default { get: f, post: f, put: f, patch: f, delete: f };',
  };
  const panel = await bundleComponent(new URL('./OriginSources.tsx', import.meta.url), stubs);
  const studio = await bundleComponent(new URL('./BenchmarkStudio.tsx', import.meta.url), stubs);
  const table = await bundleComponent(new URL('./SourcesTable.tsx', import.meta.url), stubs);
  const preview = await bundleComponent(new URL('./Applicability.tsx', import.meta.url), stubs);
  const catalogue = await bundleComponent(new URL('./CatalogueTab.tsx', import.meta.url), stubs);
  after(() => { panel.cleanup(); studio.cleanup(); table.cleanup(); preview.cleanup(); catalogue.cleanup(); });
  const g = globalThis as Record<string, unknown>;
  const ok = (data: unknown) => ({ data, loading: false, error: '', refetch() {} });
  const render = (el: unknown, url = '/benchmark-studio') => renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: [url] }, el as React.ReactElement));

  it('has exactly three sections: Source Library, Benchmark Library, Applicability Preview', () => {
    g.__resources = [ok(null), ok([])];
    const html = render(React.createElement(studio.mod.BenchmarkStudio));
    for (const t of ['Source Library', 'Benchmark Library', 'Applicability Preview']) {
      assert.ok(html.includes(t), t);
    }
    for (const t of ['Requirements', 'Levels', 'Releases', 'Watcher', 'Candidates', 'Source Updates']) {
      assert.ok(!html.includes(`>${t}<`), `no ${t} section`);
    }
    noActions(html);
  });

  it('shows the workbook origin and "Source mapping not provided." when the workbook gives no mapping', () => {
    g.__resources = [ok(prov({}))];
    const html = render(React.createElement(panel.mod.OriginSources, { benchmarkCode: 'AIQIF-C1.1' }));
    for (const t of ['InGage_AI_QIF_Benchmark_Master_v1_0_AI_Criteria.xlsx', 'sheet “AI Benchmark Master”', 'row 2',
      'Source mapping not provided.']) {
      assert.ok(html.includes(t), t);
    }
    noActions(html);
  });

  it('shows an explicit mapping with source, version, page, exact quote and relationship', () => {
    g.__resources = [ok(prov({ source_references: [mapping], source_document_linked: true }))];
    const html = render(React.createElement(panel.mod.OriginSources, { benchmarkCode: 'AIQIF-C1.1' }));
    for (const t of ['Source mappings (1)', 'version 2018', 'page 3', 'Primary', '“Every institution shall publish a policy”',
      'href="/benchmark-studio?tab=sources&amp;source=UGC-005"']) {
      assert.ok(html.includes(t), t);
    }
    assert.ok(!html.includes('Source mapping not provided'));
    noActions(html);
  });

  it('the Benchmark Library list shows only code, title, criterion and weight', () => {
    const bench = { id: 'b', benchmark_code: 'AIQIF-C1.1', title: 'AI Vision', pillar_code: 'AIQIF-C1',
      pillar_name: 'Strategy', capability: 'Define an AI vision.', benchmark_kind: 'proposed', kind_label: 'Proposed',
      benchmark_class: '', version_label: 'AI-QIF v1.0', status: 'draft', applicability: 'Institution-specific',
      source_basis: 'workbook', scoring_dimensions: '', activation_status: '', expert_owner: '', evidence_types: ['EV-01'],
      maturity_levels: [], requirement_count: 0, levels_defined: false, framework: 'AIQIF-V1.0', weight: '30.00',
      pillar_weight: '120.00', naac_crosswalk: [], origin_type: 'framework_import', origin_type_label: '',
      confirmation: { state: 'none', confirmed_by: null, confirmed_at: null } };
    g.__resources = [ok([{ code: 'AIQIF-C1', name: 'Strategy', coverage: '', catalogue_status: '', weight: '120.00',
      benchmark_count: 4, mandatory_count: 0, guidance_count: 0, proposed_count: 4 }]), ok([bench])];
    const html = render(React.createElement(catalogue.mod.CatalogueTab));
    for (const t of ['1.</span>', 'AIQIF-C1.1', 'AI Vision', 'AIQIF-C1 Strategy', 'weight 30 / 1000', '120 / 1000', '4 indicators']) {
      assert.ok(html.includes(t), t);
    }
    for (const t of ['Proposed', 'draft', 'template wording', 'source mapping(s)', 'All kinds', 'Evidence types',
      'Institution-specific', 'workbook']) {
      assert.ok(!html.includes(t), `no ${t}`);
    }
    noActions(html);
  });

  it('the Source Library table shows only the register columns and no actions', () => {
    const html = render(React.createElement(table.mod.SourcesTable, { docs: [
      doc({ official_url: 'https://www.ugc.gov.in/regs', category: '2. Higher-Education Regulation' }),
    ] }));
    const headers = [...html.matchAll(/<th[^>]*>([^<]+)<\/th>/g)].map((m) => m[1]);
    assert.deepEqual(headers, ['S.No', 'Source Code', 'Title', 'Authority', 'Category', 'Source Role', 'Document Type',
      'Applies To', 'Official URL', 'Direct URL', 'Drive Link']);
    for (const t of ['UGC-005', 'href="https://www.ugc.gov.in/regs"', 'Missing']) assert.ok(html.includes(t), t);
    for (const t of ['Approval', 'Linked Indicators', 'missing</', 'aria-expanded']) assert.ok(!html.includes(t), `no ${t}`);
    noActions(html);
  });

  it('applicability uses a saved profile and says so when there is none, guessing nothing', () => {
    const colleges = [{ id: 'a', name: 'MKCE', has_profile: true }, { id: 'b', name: 'New College', has_profile: false }];
    const none: ApplicabilityPreview = { institution: 'New College', profile: null, counts: {}, benchmarks: [],
      detail: 'New College has no saved benchmark profile, so applicability is not shown (nothing is guessed).' };
    g.__resources = [ok(colleges), ok(none)];
    let html = render(React.createElement(preview.mod.ApplicabilityPreviewTab));
    for (const t of ['MKCE', 'New College (no saved profile)', 'no saved benchmark profile', 'nothing is guessed']) {
      assert.ok(html.includes(t), t);
    }
    assert.ok(!html.includes('Institution type</span>'), 'no typed-in profile');
    const saved: ApplicabilityPreview = { institution: 'MKCE', counts: { requires_review: 1 },
      profile: { institution_type: 'engineering', autonomous_status: 'autonomous', programme_types: ['ug_engineering'],
        approval_bodies: ['AICTE'], jurisdiction: 'India' },
      benchmarks: [{ benchmark_code: 'AIQIF-C1.1', title: 'AI Vision', pillar_code: 'AIQIF-C1', result: 'requires_review',
        reason: 'No applicability rules yet.' }] };
    g.__resources = [ok(colleges), ok(saved)];
    html = render(React.createElement(preview.mod.ApplicabilityPreviewTab));
    for (const t of ['Saved profile: engineering', 'Requires review: 1', 'No applicability rules yet.']) {
      assert.ok(html.includes(t), t);
    }
    noActions(html);
  });
});
