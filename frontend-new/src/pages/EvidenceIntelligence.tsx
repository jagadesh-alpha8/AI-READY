import { useState } from 'react';
import { FactDetailDialog } from '../components/FactDetail';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, Pager, Pill, Stat, Table } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { getSprintFactFacets, listSprintFactsPage } from '../services/facts';
import type { Fact, FactFacets, Page, Sprint } from '../types/api';
import { humanize, pct, valueText } from '../utils/format';

const PAGE_SIZE = 25;

/** Source file -> extracted fact -> source location -> candidate requirement -> confidence and flags. */
export function EvidenceIntelligence() {
  return <RequireSprint>{(sprint) => <EvidenceBody sprint={sprint} />}</RequireSprint>;
}

function EvidenceBody({ sprint }: { sprint: Sprint }) {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [pillar, setPillar] = useState('');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [viewing, setViewing] = useState<Fact | null>(null);
  const facets = useResource<FactFacets>(() => getSprintFactFacets(sprint.id), sprint.id);
  const key = `${sprint.id}:${page}:${status}:${pillar}:${query}`;
  const facts = useResource<Page<Fact>>(() => listSprintFactsPage(sprint.id, { page, page_size: PAGE_SIZE, status, pillar, q: query }), key);
  const f = facets.data;
  const verified = f ? (f.status.confirmed || 0) + (f.status.corrected || 0) : null;

  return (
    <>
      <PageHeading page="evidence" />
      <Notice tone="info">AI extraction is a candidate interpretation, not verified truth. Only facts a reviewer confirms count toward the assessment.</Notice>
      <div className="stat-grid">
        <Stat label="Extracted facts" value={f ? f.total : '—'} note="Across all documents" />
        <Stat label="Verified" value={verified ?? '—'} note="Confirmed or corrected" />
        <Stat label="Awaiting review" value={f ? f.status.extracted || 0 : '—'} note="Candidate only" />
        <Stat label="Evidence requested" value={f ? f.status.evidence_requested || 0 : '—'} note="Need more proof" />
      </div>
      <form className="filter-bar" onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(q); }}>
        <label className="field inline"><span>Search</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Field, value or snippet" /></label>
        <label className="field inline"><span>Status</span>
          <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }}>
            <option value="">All</option>
            {Object.keys(f?.status || {}).map((s) => <option key={s} value={s}>{humanize(s)} ({f!.status[s]})</option>)}
          </select>
        </label>
        <label className="field inline"><span>Pillar</span>
          <select value={pillar} onChange={(e) => { setPage(1); setPillar(e.target.value); }}>
            <option value="">All</option>
            {Object.keys(f?.pillar || {}).map((p) => <option key={p} value={p}>{humanize(p)} ({f!.pillar[p]})</option>)}
          </select>
        </label>
        <button className="secondary-button">Apply</button>
      </form>
      {facts.loading && !facts.data ? <Loading /> : facts.error ? <ErrorState error={facts.error} onRetry={() => void facts.refetch()} /> :
        !facts.data?.results.length ? <Empty title="No evidence items match">Upload and process documents to populate the catalogue.</Empty> : (
          <>
            <Table columns={['Evidence item', 'Source location', 'Supports', 'Confidence', 'Status']}>
              {facts.data.results.map((fact) => (
                <tr key={fact.id}>
                  <td>
                    <strong>{fact.field_name}</strong>
                    <small className="cell-sub clamp-2" title={valueText(fact.value)}>{valueText(fact.value)}</small>
                  </td>
                  <td className="source-cell">{fact.source_document_filename || 'No source document'}{fact.source_page && `, p. ${fact.source_page}`}
                    {fact.source_snippet && <small className="cell-sub quote clamp-2">“{fact.source_snippet}”</small>}
                    <button className="link-button" onClick={() => setViewing(fact)}>View full fact</button>
                  </td>
                  <td>{fact.pillar_label}{fact.aiqif_mappings.length > 0 && <small className="cell-sub">{fact.aiqif_mappings.map((m) => m.indicator_code).join(', ')}</small>}</td>
                  <td>{pct(fact.confidence_score)}</td>
                  <td>
                    {fact.verification
                      ? <><Pill status={fact.verification.status} label={fact.verification.status_label} /><small className="cell-sub">{humanize(fact.status)}</small></>
                      : <Pill status={fact.status} />}
                  </td>
                </tr>
              ))}
            </Table>
            <Pager page={page} count={facts.data.count} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      {viewing && <FactDetailDialog fact={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}
