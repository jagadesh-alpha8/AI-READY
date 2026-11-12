import { useState } from 'react';
import { CyclePicker } from '../components/CyclePicker';
import { BenchmarkDialog, CycleActions, CycleScorecardPanel } from '../components/CycleWorkspace';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { createCycle } from '../services/assessments';
import type { CycleBenchmarkRow, Sprint } from '../types/api';
import { KIND_LABEL, gapText } from '../utils/benchmark';
import { tierName } from '../utils/maturity';
import { humanize } from '../utils/format';

export function BenchmarkComparison() {
  return <RequireSprint>{(sprint) => <ComparisonBody sprint={sprint} />}</RequireSprint>;
}

function ComparisonBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const { cycles, cyclesState, cycleId, choose, detail } = useCycle(sprint.institution_id);
  const [creating, setCreating] = useState(false);
  const [done, setDone] = useState('');
  const [kind, setKind] = useState('');
  const [open, setOpen] = useState<CycleBenchmarkRow | null>(null);
  const changed = (text: string) => { setDone(text); void detail.refetch(); };

  const createButton = can('assessments.manage') && <button className="primary-action" onClick={() => setCreating(true)}>New assessment cycle</button>;

  let body;
  if (cyclesState.loading || (cycleId && detail.loading)) body = <Loading />;
  else if (cyclesState.error) body = <ErrorState error={cyclesState.error} onRetry={() => void cyclesState.refetch()} />;
  else if (!cycleId) body = <Empty title="No benchmark assessment yet">An assessment cycle freezes the published benchmark release and the institution profile. InGage staff open it.</Empty>;
  else if (detail.error) body = <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  else {
    const c = detail.data!;
    const rows = c.benchmarks.filter((b) => b.included !== false && (!kind || b.kind === kind));
    const met = c.benchmarks.filter((b) => gapText(b) === 'Met').length;
    body = (
      <>
        <div className="stat-grid">
          <Stat label="Benchmark release" value={c.release_label || '—'} note={`Snapshot ${c.release_hash.slice(0, 8)}`} />
          <Stat label="Benchmarks in scope" value={c.benchmarks.filter((b) => b.included !== false).length} note={`${c.benchmarks.filter((b) => b.included === false).length} excluded with a reason`} />
          <Stat label="Target met" value={met} note="Current level at or above target" />
          <Stat label="Cycle" value={<Pill status={c.status} label={c.status_label} />} note={c.name} />
        </div>
        {!c.scores_visible && <Notice tone="info">Scores become visible to the institution once InGage reviews the cycle.</Notice>}
        <div className="button-row"><CycleActions cycle={c} onChanged={changed} /></div>
        <div className="filter-bar">
          <CyclePicker cycles={cycles} value={cycleId} onChange={choose} />
          <label className="field inline"><span>Source class</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All</option>
              {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
        </div>
        {rows.length === 0 ? <Empty title="No benchmarks in this view" /> : (
          <Table columns={['Capability', 'Source class', 'Current', 'Required', 'Gap', 'Applicability', 'Evidence', '']}>
            {rows.map((b) => (
              <tr key={b.benchmark_code}>
                <td><strong>{b.title}</strong><small className="cell-sub">{b.benchmark_code} · {b.pillar}</small></td>
                <td><span className={`kind kind-${b.kind}`}>{KIND_LABEL[b.kind] || humanize(b.kind)}</span></td>
                <td>{b.assessment?.current_level ? `${b.assessment.current_level} · ${tierName(b.assessment.current_level)}` : 'Unknown'}</td>
                <td>{b.target_level} · {tierName(b.target_level)}</td>
                <td><Pill status={gapText(b) === 'Met' ? 'met' : gapText(b) === 'Not scored' ? 'pending' : 'at_risk'} label={gapText(b)} /></td>
                <td><Pill status={b.applicability_result} /><small className="cell-sub">{b.applicability_reason}</small></td>
                <td>{b.accepted} accepted<small className="cell-sub">{b.waiting} waiting · {b.requests} requests</small></td>
                <td><button className="secondary-button" onClick={() => setOpen(b)}>Open</button></td>
              </tr>
            ))}
          </Table>
        )}
        {c.scores_visible && <CycleScorecardPanel cycleId={c.id} />}
        {open && <BenchmarkDialog cycleId={c.id} code={open.benchmark_code} onClose={() => setOpen(null)} onChanged={() => void detail.refetch()} />}
      </>
    );
  }

  return (
    <>
      <PageHeading page="benchmark" actions={createButton} />
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      {body}
      {creating && (
        <ActionDialog
          title="New assessment cycle"
          description="Freezes the current published benchmark release and this institution's saved profile."
          fields={[{ name: 'name', label: 'Cycle name', required: true, initial: `${sprint.academic_year || 'Current'} assessment` },
            { name: 'opens_on', label: 'Opens on', type: 'date' }, { name: 'closes_on', label: 'Closes on', type: 'date' }]}
          confirmLabel="Create cycle"
          onSubmit={async (v) => {
            const res = await createCycle({ institution: sprint.institution_id, name: v.name, opens_on: v.opens_on || undefined, closes_on: v.closes_on || undefined });
            await cyclesState.refetch();
            choose(res.data.id);
            setDone(`Cycle "${res.data.name}" created on release ${res.data.release_label}.`);
          }}
          onClose={() => setCreating(false)}
        />
      )}
    </>
  );
}
