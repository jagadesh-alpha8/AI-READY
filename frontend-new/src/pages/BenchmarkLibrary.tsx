import { useState } from 'react';
import { Empty, ErrorState, KeyValues, Loading, Notice, PageHeading, Panel, Pill, RowsTable, Stat, Table, Tabs } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import {
  compareVersion, getApplicabilityReference, getApplicabilityValidation, getBenchmarkHistory, getBenchmarkProvenance, getBenchmarkReadiness,
  getCatalogueBenchmark, getCurrentRelease, getRelease, getReleaseDiff, getRequirementSuggestions, getSource, getSourceReference,
  getSourceSummary, getWatcherSummary, listBenchmarkApplicabilityRules, listBenchmarkCandidates, listBenchmarkEvidenceRules, listBenchmarkRequirements,
  listCatalogue, listEvidenceTypes, listPillars, listReleases, listRequirements, listSources, listStudioAIJobs, listVersionCandidates,
  listWatcherEvents, listWatcherFeeds, listWatcherRuns,
} from '../services/benchmarks';
import type { CataloguePillar, SourceDocument, SourceLibrarySummary } from '../types/api';
import type { BenchmarkCandidate, BenchmarkRelease, CatalogueBenchmark, EvidenceTypeInfo, RequirementRow, WatcherEvent } from '../types/workflow';
import { statusOf } from '../utils/errors';
import { date, dateTime, humanize } from '../utils/format';

/**
 * The benchmark library, read-only: the backend keeps the catalogue read-only in the portal
 * (BENCHMARK_CATALOGUE_READ_ONLY) and changes it only through the controlled workbook import.
 */
const TABS = [
  { key: 'catalogue', label: 'Catalogue' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'sources', label: 'Sources' },
  { key: 'releases', label: 'Releases' },
  { key: 'watcher', label: 'Watcher' },
  { key: 'candidates', label: 'Candidates & AI jobs' },
  { key: 'reference', label: 'Reference' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export function BenchmarkLibrary() {
  const [tab, setTab] = useState<Tab>('catalogue');
  return (
    <>
      <PageHeading page="benchmarkstudio" />
      <Notice tone="info">Read-only here: published releases are immutable and the catalogue changes only through the controlled workbook import.</Notice>
      <StudioSummary />
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Library sections" />
      {tab === 'catalogue' && <Catalogue />}
      {tab === 'requirements' && <Requirements />}
      {tab === 'sources' && <Sources />}
      {tab === 'releases' && <Releases />}
      {tab === 'watcher' && <Watcher />}
      {tab === 'candidates' && <Candidates />}
      {tab === 'reference' && <Reference />}
    </>
  );
}

/** Library totals (the former Benchmark Studio page). */
function StudioSummary() {
  const summary = useResource<SourceLibrarySummary>(getSourceSummary, 'source-summary');
  const pillars = useResource<CataloguePillar[]>(listPillars, 'pillars');
  const totals = (pillars.data || []).reduce((t, p) => ({
    benchmarks: t.benchmarks + p.benchmark_count, mandatory: t.mandatory + p.mandatory_count, proposed: t.proposed + p.proposed_count,
  }), { benchmarks: 0, mandatory: 0, proposed: 0 });
  return (
    <div className="stat-grid">
      <Stat label="Source library" value={summary.data?.documents ?? '—'} note={summary.data ? `${summary.data.versions} versions · ${summary.data.flagged_versions} flagged` : ''} />
      <Stat label="Benchmarks" value={pillars.data ? totals.benchmarks : '—'} note={`${pillars.data?.length ?? 0} pillars`} />
      <Stat label="Mandatory" value={pillars.data ? totals.mandatory : '—'} note="Regulatory requirements" />
      <Stat label="InGage proposed" value={pillars.data ? totals.proposed : '—'} note="AI-readiness benchmarks" />
    </div>
  );
}

function Catalogue() {
  const pillars = useResource<CataloguePillar[]>(listPillars, 'pillars');
  const [pillar, setPillar] = useState('');
  const [q, setQ] = useState('');
  const list = useResource<CatalogueBenchmark[]>(() => listCatalogue({ pillar, q }), `cat:${pillar}:${q}`);
  const [code, setCode] = useState('');
  return (
    <>
      <div className="filter-bar">
        <label className="field inline"><span>Pillar</span>
          <select value={pillar} onChange={(e) => setPillar(e.target.value)}>
            <option value="">All</option>
            {(pillars.data || []).map((p) => <option key={p.code} value={p.code}>{p.code} · {p.name}</option>)}
          </select>
        </label>
        <label className="field inline"><span>Search</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Code or title" /></label>
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : !list.data?.length ? <Empty title="No benchmarks" /> : (
        <Table columns={['Benchmark', 'Pillar', 'Kind', 'Requirements', 'Levels', 'Status', '']}>
          {list.data.map((b) => (
            <tr key={b.benchmark_code} aria-selected={b.benchmark_code === code}>
              <td><strong>{b.benchmark_code}</strong><small className="cell-sub clamp-2">{b.title}</small></td>
              <td>{b.pillar_code}</td><td>{b.kind_label}</td><td>{b.requirement_count}</td>
              <td>{b.levels_defined ? 'Defined' : 'Missing'}</td>
              <td><Pill status={b.status} /><small className="cell-sub">{b.version_label}</small></td>
              <td><button className="secondary-button" onClick={() => setCode(b.benchmark_code === code ? '' : b.benchmark_code)}>{b.benchmark_code === code ? 'Close' : 'Open'}</button></td>
            </tr>
          ))}
        </Table>
      )}
      {code && <BenchmarkDetail code={code} />}
    </>
  );
}

function BenchmarkDetail({ code }: { code: string }) {
  const b = useResource<CatalogueBenchmark>(() => getCatalogueBenchmark(code), `cb:${code}`);
  const readiness = useResource<Record<string, unknown>>(() => getBenchmarkReadiness(code), `cbr:${code}`);
  const history = useResource(() => getBenchmarkHistory(code), `cbh:${code}`);
  const provenance = useResource<Record<string, unknown>>(() => getBenchmarkProvenance(code), `cbp:${code}`);
  const reqs = useResource<RequirementRow[]>(() => listBenchmarkRequirements(code), `cbq:${code}`);
  const evidence = useResource<Record<string, unknown>[]>(() => listBenchmarkEvidenceRules(code), `cbe:${code}`);
  const applic = useResource<Record<string, unknown>[]>(() => listBenchmarkApplicabilityRules(code), `cba:${code}`);
  const validation = useResource<Record<string, unknown>>(() => getApplicabilityValidation(code), `cbv:${code}`);
  const d = b.data;
  return (
    <Panel title={d ? `${d.benchmark_code} · ${d.title}` : code} sub={d ? `${d.pillar_name} · ${d.capability} · ${d.source_basis}` : undefined}>
      {b.error != null && <ErrorState error={b.error} />}
      {d && (
        <>
          <p className="muted">Applicability: {d.applicability || '—'} · Evidence types: {d.evidence_types.join(', ') || '—'}</p>
          <Table columns={['Level', 'Definition', 'Measurement']}>
            {d.maturity_levels.map((l) => <tr key={l.level}><td>{l.level} · {l.level_label}</td><td>{l.definition}</td><td>{l.measurement_rule}</td></tr>)}
          </Table>
        </>
      )}
      <h3>Readiness</h3>{readiness.loading ? <Loading /> : <KeyValues data={readiness.data} />}
      <h3>Source requirements</h3>
      {reqs.loading ? <Loading /> : <Table columns={['Code', 'Statement', 'Source', 'Page']}>
        {(reqs.data || []).map((r) => <tr key={r.id}><td>{r.code}</td><td>{r.statement}</td><td>{r.source_code} {r.version_label}</td><td>{r.page ?? '—'}</td></tr>)}
      </Table>}
      <h3>Evidence rules</h3>{evidence.loading ? <Loading /> : <RowsTable rows={evidence.data || []} />}
      <h3>Applicability rules</h3>{applic.loading ? <Loading /> : <RowsTable rows={applic.data || []} />}
      <h3>Applicability check</h3>{validation.loading ? <Loading /> : <KeyValues data={validation.data} />}
      <h3>Provenance</h3>{provenance.loading ? <Loading /> : <KeyValues data={provenance.data} />}
      <h3>History</h3>
      {history.loading ? <Loading /> : !history.data?.length ? <p className="muted">No changes recorded.</p> : (
        <ol className="fact-history">{history.data.map((h, i) => <li key={i}><b>{humanize(h.action)}</b> by {h.actor} · {dateTime(h.at)}</li>)}</ol>
      )}
    </Panel>
  );
}

function Requirements() {
  const [q, setQ] = useState('');
  const list = useResource<RequirementRow[]>(() => listRequirements({ q }), `reqs:${q}`);
  const [code, setCode] = useState('');
  const sug = useResource<Record<string, unknown>>(() => getRequirementSuggestions(code), `sug:${code}`, !!code);
  return (
    <>
      <div className="filter-bar"><label className="field inline"><span>Search</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Code or text" /></label></div>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : (
        <Table columns={['Code', 'Statement', 'Source', 'Kind', '']}>
          {(list.data || []).slice(0, 200).map((r) => (
            <tr key={r.id}><td>{r.code}</td><td><span className="clamp-2">{r.statement}</span></td><td>{r.source_code} {r.version_label}{r.page != null && `, p. ${r.page}`}</td><td>{humanize(r.kind)}</td>
              <td><button className="secondary-button" onClick={() => setCode(r.code)}>Benchmarks it fits</button></td></tr>
          ))}
        </Table>
      )}
      {code && <Panel title={`Suggested benchmarks for ${code}`}>{sug.loading ? <Loading /> : sug.error ? <ErrorState error={sug.error} /> : <KeyValues data={sug.data} />}</Panel>}
    </>
  );
}

function Sources() {
  const list = useResource<SourceDocument[]>(() => listSources(), 'sources');
  const [code, setCode] = useState('');
  const src = useResource<SourceDocument & { versions?: { id: string; version_label: string; status: string }[] }>(() => getSource(code), `src:${code}`, !!code);
  const [version, setVersion] = useState<{ id: string; label: string } | null>(null);
  const cands = useResource<Record<string, unknown>[]>(() => listVersionCandidates(version!.id), `vc:${version?.id}`, !!version);
  const cmp = useResource<Record<string, unknown>>(() => compareVersion(version!.id), `vcmp:${version?.id}`, !!version);
  return (
    <>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : (
        <Table columns={['Source', 'Authority', 'Category', 'Versions', 'Latest', '']}>
          {(list.data || []).map((s) => (
            <tr key={s.id}><td><strong>{s.source_code}</strong><small className="cell-sub clamp-2">{s.title}</small></td><td>{s.authority_name}</td><td>{humanize(s.category)}<small className="cell-sub">{s.source_role_label}</small></td>
              <td>{s.version_count}</td><td>{s.latest_version ? `${s.latest_version.version_label} · ${humanize(s.latest_version.status)} · ${s.latest_version.requirement_count} req.` : '—'}</td>
              <td><button className="secondary-button" onClick={() => { setCode(s.source_code); setVersion(null); }}>Open</button></td></tr>
          ))}
        </Table>
      )}
      {code && (src.loading ? <Loading /> : src.error ? <ErrorState error={src.error} /> : src.data && (
        <Panel title={`${src.data.source_code} · ${src.data.title}`}>
          {src.data.versions?.length ? (
            <Table columns={['Version', 'Status', '']}>
              {src.data.versions.map((v) => <tr key={v.id}><td>{v.version_label}</td><td><Pill status={v.status} /></td>
                <td><button className="secondary-button" onClick={() => setVersion({ id: v.id, label: v.version_label })}>Candidates & changes</button></td></tr>)}
            </Table>
          ) : <KeyValues data={src.data as unknown as Record<string, unknown>} skip={['id']} />}
        </Panel>
      ))}
      {version && (
        <Panel title={`Version ${version.label}`}>
          <h3>Requirement candidates</h3>{cands.loading ? <Loading /> : cands.error ? <ErrorState error={cands.error} /> : <RowsTable rows={cands.data || []} />}
          <h3>Compared with the previous version</h3>{cmp.loading ? <Loading /> : cmp.error ? <ErrorState error={cmp.error} /> : <KeyValues data={cmp.data} />}
        </Panel>
      )}
    </>
  );
}

function Releases() {
  const list = useResource<BenchmarkRelease[]>(listReleases, 'releases');
  const current = useResource(getCurrentRelease, 'release-current');
  const [label, setLabel] = useState('');
  const rel = useResource(() => getRelease(label), `rel:${label}`, !!label);
  const diff = useResource<Record<string, unknown>>(() => getReleaseDiff(label), `reld:${label}`, !!label);
  return (
    <>
      <div className="stat-grid">
        <Stat label="Published release" value={current.data?.release_label || (statusOf(current.error) === 404 ? 'None yet' : '—')} note={current.data ? `${current.data.item_count} items · ${date(current.data.published_at)}` : ''} />
        <Stat label="Releases" value={list.data?.length ?? '—'} />
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : (
        <Table columns={['Release', 'Status', 'Items', 'Based on', 'Published', '']}>
          {(list.data || []).map((r) => (
            <tr key={r.id}><td><strong>{r.release_label}</strong><small className="cell-sub clamp-2">{r.release_notes}</small></td><td><Pill status={r.status} /></td><td>{r.item_count}</td>
              <td>{r.based_on || '—'}</td><td>{date(r.published_at)}</td><td><button className="secondary-button" onClick={() => setLabel(r.release_label)}>Open</button></td></tr>
          ))}
        </Table>
      )}
      {label && (
        <Panel title={`Release ${label}`}>
          {rel.loading ? <Loading /> : <KeyValues data={rel.data as Record<string, unknown> | null} skip={['id', 'items']} />}
          <h3>Changes from the release it is based on</h3>{diff.loading ? <Loading /> : diff.error ? <ErrorState error={diff.error} /> : <KeyValues data={diff.data} />}
        </Panel>
      )}
    </>
  );
}

function Watcher() {
  const summary = useResource<Record<string, unknown>>(getWatcherSummary, 'w-sum');
  const feeds = useResource<Record<string, unknown>[]>(listWatcherFeeds, 'w-feeds');
  const runs = useResource<Record<string, unknown>[]>(listWatcherRuns, 'w-runs');
  const events = useResource<WatcherEvent[]>(listWatcherEvents, 'w-events');
  return (
    <>
      <Panel title="Regulatory watcher" sub="Feeds checked for new circulars and versions">{summary.loading ? <Loading /> : <KeyValues data={summary.data} />}</Panel>
      <Panel title="Feeds">{feeds.loading ? <Loading /> : <RowsTable rows={feeds.data || []} />}</Panel>
      <Panel title="Recent runs">{runs.loading ? <Loading /> : <RowsTable rows={(runs.data || []).slice(0, 20)} />}</Panel>
      <Panel title="Detected changes">
        {events.loading ? <Loading /> : !events.data?.length ? <p className="muted">Nothing detected.</p> : (
          <Table columns={['Change', 'Source', 'Detected', 'Status']}>
            {events.data.map((e) => <tr key={e.id}><td><strong>{e.title || e.id}</strong><small className="cell-sub clamp-2">{e.summary}</small></td><td>{e.source_code || '—'}</td><td>{dateTime(e.detected_at || e.created_at)}</td><td><Pill status={e.status} /></td></tr>)}
          </Table>
        )}
      </Panel>
    </>
  );
}

function Candidates() {
  const [status, setStatus] = useState('open');
  const cands = useResource<BenchmarkCandidate[]>(() => listBenchmarkCandidates(status), `bc:${status}`);
  const jobs = useResource<Record<string, unknown>[]>(listStudioAIJobs, 'ai-jobs');
  const { msg, setMsg } = useRunner();
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="filter-bar">
        <label className="field inline"><span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>{['open', 'accepted', 'rejected', 'all'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select>
        </label>
      </div>
      <Panel title="Benchmark candidates" sub="Proposed new or changed benchmarks waiting for a decision">
        {cands.loading ? <Loading /> : cands.error ? <ErrorState error={cands.error} /> : !cands.data?.length ? <p className="muted">No candidates.</p> : (
          <Table columns={['Candidate', 'Type', 'Benchmark', 'Source', 'Created', 'Status']}>
            {cands.data.map((c) => <tr key={c.id}><td>{c.title}</td><td>{c.type_label}</td><td>{c.benchmark_code || '—'}</td><td>{c.source_code || '—'}</td><td>{date(c.created_at)}</td><td><Pill status={c.status} label={c.status_label} /></td></tr>)}
          </Table>
        )}
      </Panel>
      <Panel title="Studio AI jobs" sub="Drafting jobs and their status">{jobs.loading ? <Loading /> : jobs.error ? <ErrorState error={jobs.error} /> : <RowsTable rows={jobs.data || []} empty="No AI jobs." />}</Panel>
    </>
  );
}

function Reference() {
  const types = useResource<EvidenceTypeInfo[]>(listEvidenceTypes, 'ev-types');
  const applic = useResource<Record<string, unknown>>(getApplicabilityReference, 'applic-ref');
  const sourceRef = useResource<Record<string, unknown>>(getSourceReference, 'source-ref');
  return (
    <>
      <Panel title="Evidence types">
        {types.loading ? <Loading /> : <Table columns={['Code', 'Name', 'Validation', 'Examples']}>
          {(types.data || []).map((t) => <tr key={t.code}><td>{t.code}</td><td>{t.name}</td><td>{t.validation_method}</td><td>{t.examples}</td></tr>)}
        </Table>}
      </Panel>
      <Panel title="Applicability vocabulary">{applic.loading ? <Loading /> : <KeyValues data={applic.data} />}</Panel>
      <Panel title="Source vocabulary">{sourceRef.loading ? <Loading /> : <KeyValues data={sourceRef.data} />}</Panel>
    </>
  );
}
