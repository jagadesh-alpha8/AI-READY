import { useState } from 'react';
import { CapabilityEvidence, CapabilityStanding } from './Capability';
import { Empty, ErrorState, Loading, Notice, Panel, Pill, Table } from './ui';
import { useAccess } from '../hooks/useAccess';
import { usePolling, useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { cancelRun, downloadCapabilityReport, getRun, getRunEvidence, listRuns } from '../services/capability';
import type { Sprint } from '../types/api';
import type { CapabilityPage, Job, Run } from '../types/capability';
import { isActive, scoreLabel } from '../utils/capability';
import { dateTime } from '../utils/format';

type Evidence = Awaited<ReturnType<typeof getRunEvidence>>['data'];

/** Every capability run of the sprint, any completed run's result, and the frozen excerpts it cited. */
export function RunHistory({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const [page, setPage] = useState(1);
  const runs = useResource<CapabilityPage<Job>>(() => listRuns(sprint.id, page), `runs:${sprint.id}:${page}`);
  const [chosen, setChosen] = useState('');
  const runId = chosen || runs.data?.results.find((r) => r.status === 'completed')?.id || '';
  const run = useResource<Run>(() => getRun(sprint.id, runId), `run:${runId}`, !!runId);
  const [condition, setCondition] = useState('');
  const evidence = useResource<Evidence>(() => getRunEvidence(sprint.id, runId, condition || undefined), `ev:${runId}:${condition}`, !!runId && run.data?.status === 'completed');
  const { busy, msg, setMsg, run: act } = useRunner();

  usePolling(() => void runs.refetch(), (runs.data?.results || []).some((r) => isActive(r)), 5000);
  const r = run.data;
  const sourceName = new Map((evidence.data?.sources || []).map((s) => [s.id, String(s.filename || s.document || s.id)]));

  return (
    <>
      <h2 className="section-title">Assessment runs</h2>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {runs.loading && !runs.data ? <Loading /> : runs.error ? <ErrorState error={runs.error} onRetry={() => void runs.refetch()} /> :
        !runs.data?.results.length ? <Empty title="No assessment runs yet">Start one from AI readiness assessment.</Empty> : (
          <>
            <Table columns={['Run', 'Started', 'Scope', 'Rubric', 'Status', '']}>
              {runs.data.results.map((j) => (
                <tr key={j.id} aria-selected={j.id === runId}>
                  <td><b>{j.id.slice(0, 8)}</b>{j.id === runId && <small className="cell-sub">Shown below</small>}</td>
                  <td>{dateTime(j.created_at)}</td>
                  <td>{j.reference_period || 'Default scope'}</td>
                  <td>{j.rubric_version || '—'}</td>
                  <td><Pill status={j.status === 'queued' ? 'pending' : j.status} label={j.stalled ? 'Stalled' : j.status} /></td>
                  <td>
                    <div className="row-actions nowrap">
                      {j.status === 'completed' && j.id !== runId && <button className="secondary-button" onClick={() => { setChosen(j.id); setCondition(''); }}>Show</button>}
                      {isActive(j) && can('sprint.manage') && (
                        <button className="secondary-button" disabled={!!busy} onClick={() => void act(`c:${j.id}`, async () => { await cancelRun(sprint.id, j.id); await runs.refetch(); }, 'Run cancelled.')}>Cancel</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
            {(runs.data.next || runs.data.previous) && (
              <nav className="pager" aria-label="Pages">
                <button className="secondary-button" disabled={!runs.data.previous} onClick={() => setPage(page - 1)}>Previous</button>
                <span>Page {page} · {runs.data.count} runs</span>
                <button className="secondary-button" disabled={!runs.data.next} onClick={() => setPage(page + 1)}>Next</button>
              </nav>
            )}
          </>
        )}

      {runId && (run.loading && !r ? <Loading label="Loading the run…" /> : run.error ? <ErrorState error={run.error} /> : r?.assessment && (
        <>
          <h2 className="section-title">Run {r.id.slice(0, 8)} · {scoreLabel(r.assessment.result)}</h2>
          {r.diagnostics?.explanation && <Notice tone="info">{r.diagnostics.explanation}</Notice>}
          <div className="button-row">
            {(['pdf', 'html', 'json'] as const).map((f) => (
              <button key={f} className="secondary-button" disabled={!!busy} onClick={() => void act(`dl:${f}`, () => downloadCapabilityReport(sprint.id, r.id, f, 'evidence'))}>Evidence report ({f.toUpperCase()})</button>
            ))}
          </div>
          <CapabilityStanding result={r.assessment.result} run={r} />
          <CapabilityEvidence run={r} />
          <Panel title="Frozen source excerpts" sub={evidence.data?.note || 'Exactly what this run read; new uploads need a new run'}
            actions={(
              <label className="field inline"><span>Condition</span>
                <select value={condition} onChange={(e) => setCondition(e.target.value)}>
                  <option value="">All cited</option>
                  {r.assessment.records.filter((x) => x.citations.length).map((x) => <option key={x.condition_id} value={x.condition_id}>{x.condition_id}</option>)}
                </select>
              </label>
            )}>
            {evidence.loading && !evidence.data ? <Loading /> : evidence.error ? <ErrorState error={evidence.error} /> :
              !evidence.data?.records.length ? <p className="muted">No cited excerpts.</p> : evidence.data.records.filter((x) => x.citations.length).map((x) => (
                <article key={x.condition_id} className="condition">
                  <div><b>{x.condition_id}</b> · {x.state}</div>
                  {x.reason && <p className="muted">{x.reason}</p>}
                  {x.citations.map((c, i) => <blockquote key={i}><p>{c.quote}</p><cite>{sourceName.get(c.source_id) || c.source_id}</cite></blockquote>)}
                </article>
              ))}
          </Panel>
        </>
      ))}
    </>
  );
}
