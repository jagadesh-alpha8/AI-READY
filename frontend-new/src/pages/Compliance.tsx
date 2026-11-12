import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, PageHeading, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getSourceSummary, listSources } from '../services/benchmarks';
import type { SourceDocument, SourceLibrarySummary, Sprint } from '../types/api';
import { KIND_LABEL } from '../utils/benchmark';
import { humanize } from '../utils/format';

export function Compliance() {
  return <RequireSprint>{(sprint) => <ComplianceBody sprint={sprint} />}</RequireSprint>;
}

/** Staff see the source library; everyone sees how the institution's benchmarks split by source class. */
function ComplianceBody({ sprint }: { sprint: Sprint }) {
  const { staff } = useAccess();
  const sources = useResource<SourceDocument[]>(() => listSources(), 'sources', staff);
  const summary = useResource<SourceLibrarySummary>(getSourceSummary, 'source-summary', staff);
  const { cycleId, detail } = useCycle(sprint.institution_id);
  const byKind = Object.keys(KIND_LABEL).map((k) => ({ k, rows: (detail.data?.benchmarks || []).filter((b) => b.kind === k && b.included !== false) }));

  return (
    <>
      <PageHeading page="compliance" />
      <h2 className="section-title">This institution's benchmarks by source class</h2>
      {!cycleId ? <Empty title="No assessment cycle yet">The mapping appears once a benchmark assessment cycle exists.</Empty> : detail.loading ? <Loading /> : detail.error ? <ErrorState error={detail.error} /> : (
        <Table columns={['Source class', 'Applicable benchmarks', 'Scored', 'Evidence accepted', 'Release']}>
          {byKind.map(({ k, rows }) => (
            <tr key={k}>
              <td><span className={`kind kind-${k}`}>{KIND_LABEL[k]}</span></td>
              <td>{rows.length}</td>
              <td>{rows.filter((r) => r.assessment?.current_level).length}</td>
              <td>{rows.reduce((n, r) => n + r.accepted, 0)} of {rows.reduce((n, r) => n + r.evidence, 0)}</td>
              <td>{detail.data!.release_label}</td>
            </tr>
          ))}
        </Table>
      )}
      {staff && (
        <>
          <h2 className="section-title">Source library</h2>
          {summary.data && (
            <div className="stat-grid">
              <Stat label="Source documents" value={summary.data.documents} />
              <Stat label="Versions" value={summary.data.versions} />
              <Stat label="Categories" value={Object.keys(summary.data.by_category).length} />
              <Stat label="Flagged versions" value={summary.data.flagged_versions} note="Need review" />
            </div>
          )}
          {sources.loading ? <Loading /> : sources.error ? <ErrorState error={sources.error} onRetry={() => void sources.refetch()} /> :
            !sources.data?.length ? <Empty title="No sources" /> : (
              <Table columns={['Framework', 'Authority', 'Version', 'Requirements', 'Review']}>
                {sources.data.map((s) => (
                  <tr key={s.id}>
                    <td><strong>{s.title}</strong><small className="cell-sub">{s.source_code} · {s.source_role_label || humanize(s.category)}</small></td>
                    <td>{s.authority_name}</td>
                    <td>{s.latest_version?.version_label || '—'}</td>
                    <td>{s.latest_version?.requirement_count ?? '—'}</td>
                    <td>{s.latest_version ? <Pill status={s.latest_version.status} /> : '—'}</td>
                  </tr>
                ))}
              </Table>
            )}
        </>
      )}
    </>
  );
}
