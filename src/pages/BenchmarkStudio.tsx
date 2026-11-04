import { ErrorState, Loading, Notice, PageHeading, Stat, Table } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { getSourceSummary, listPillars } from '../services/benchmarks';
import type { CataloguePillar, SourceLibrarySummary } from '../types/api';

/** Read-only view of the benchmark library (InGage staff). Master data changes only through the controlled import. */
export function BenchmarkStudio() {
  const summary = useResource<SourceLibrarySummary>(getSourceSummary, 'source-summary');
  const pillars = useResource<CataloguePillar[]>(listPillars, 'pillars');
  const totals = (pillars.data || []).reduce((t, p) => ({
    benchmarks: t.benchmarks + p.benchmark_count, mandatory: t.mandatory + p.mandatory_count, proposed: t.proposed + p.proposed_count,
  }), { benchmarks: 0, mandatory: 0, proposed: 0 });

  return (
    <>
      <PageHeading page="benchmarkstudio" />
      <Notice tone="info">Published releases are immutable; a change creates a new release. Edits to sources and requirements happen in the existing Benchmark Studio and its controlled import.</Notice>
      <div className="stat-grid">
        <Stat label="Source library" value={summary.data?.documents ?? '—'} note={summary.data ? `${summary.data.versions} versions` : ''} />
        <Stat label="Benchmarks" value={pillars.data ? totals.benchmarks : '—'} note={`${pillars.data?.length ?? 0} pillars`} />
        <Stat label="Mandatory" value={pillars.data ? totals.mandatory : '—'} note="Regulatory requirements" />
        <Stat label="InGage proposed" value={pillars.data ? totals.proposed : '—'} note="AI-readiness benchmarks" />
      </div>
      {pillars.loading ? <Loading /> : pillars.error ? <ErrorState error={pillars.error} onRetry={() => void pillars.refetch()} /> : (
        <Table columns={['Pillar', 'Benchmarks', 'Mandatory', 'Guidance', 'Proposed']}>
          {pillars.data!.map((p) => (
            <tr key={p.code}><td><strong>{p.name}</strong><small className="cell-sub">{p.code}</small></td><td>{p.benchmark_count}</td><td>{p.mandatory_count}</td><td>{p.guidance_count}</td><td>{p.proposed_count}</td></tr>
          ))}
        </Table>
      )}
    </>
  );
}
