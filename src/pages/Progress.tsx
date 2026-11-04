import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Bar, Dummy, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getPlan } from '../services/assessments';
import { getScoreHistory, recalculateScore } from '../services/scoring';
import { getSprintOverview } from '../services/sprints';
import type { ImprovementPlan, Page, ScoreHistoryRow, Sprint, SprintOverview } from '../types/api';
import { errorMessage } from '../utils/errors';
import { dateTime, num, rows } from '../utils/format';

export function Progress() {
  return <RequireSprint>{(sprint) => <ProgressBody sprint={sprint} />}</RequireSprint>;
}

/** Each scoring run is an immutable snapshot: reassessment adds a run, history keeps every earlier one. */
function ProgressBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const overview = useResource<SprintOverview>(() => getSprintOverview(sprint.id), sprint.id);
  const history = useResource<ScoreHistoryRow[] | Page<ScoreHistoryRow>>(() => getScoreHistory(sprint.id), sprint.id);
  const { cycleId } = useCycle(sprint.institution_id);
  const plan = useResource<ImprovementPlan>(() => getPlan(cycleId), `plan:${cycleId}`, !!cycleId);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const runs = [...rows(history.data)].sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  const first = runs[0];
  const last = runs[runs.length - 1];
  const s = plan.data?.summary;
  const validated = plan.data ? plan.data.gaps.filter((g) => g.status === 'validated' || g.status === 'closed').length : null;

  const reassess = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await recalculateScore(sprint.id);
      setMsg({ tone: 'success', text: `Reassessment recorded: CRI ${num(res.data.overall_cri, 1)}. Earlier results are kept below.` });
      await Promise.all([history.refetch(), overview.refetch()]);
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeading page="progress" actions={can('sprint.manage') && <button className="primary-action" disabled={busy} onClick={() => void reassess()}>{busy ? 'Reassessing…' : 'Reassess now'}</button>} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="stat-grid">
        <Stat label="Plan completion" value={s && s.tasks ? `${Math.round((s.tasks_done / s.tasks) * 100)}%` : '—'} note={s ? `${s.tasks_done} of ${s.tasks} tasks` : 'No plan yet'} />
        <Stat label="CRI movement" value={last ? num(last.overall_cri, 1) : '—'} note={first && last && runs.length > 1 ? `${last.overall_cri - first.overall_cri >= 0 ? '+' : ''}${num(last.overall_cri - first.overall_cri, 1)} since the first run` : 'One run so far'} />
        <Stat label="Verified outcomes" value={validated ?? '—'} note="Plan gaps validated with evidence" />
        <Stat label="Assessment runs" value={runs.length} note={last ? `Latest ${dateTime(last.created_at)}` : 'None yet'} />
      </div>
      <div className="content-grid">
        <Panel title="Transformation progress" sub="CRI of every assessment run">
          {history.loading ? <Loading /> : history.error ? <ErrorState error={history.error} onRetry={() => void history.refetch()} /> :
            runs.length === 0 ? <Empty title="No assessment runs yet" /> : <HistoryChart runs={runs} />}
        </Panel>
        <Panel title="Readiness by pillar" sub="Latest run">
          {overview.data?.scorecard ? (
            <div className="bar-list">{overview.data.scorecard.pillar_scores.map((p) => <Bar key={p.pillar} label={p.label} value={p.raw_score} />)}</div>
          ) : <p className="muted">Not yet assessed.</p>}
        </Panel>
      </div>
      {runs.length > 0 && (
        <Table columns={['Run', 'CRI', 'Coverage-adjusted', 'Confidence', 'Calculation']}>
          {[...runs].reverse().map((r, i) => (
            <tr key={r.id || i}>
              <td>{dateTime(r.created_at)}</td>
              <td>{num(r.overall_cri, 1)}</td>
              <td>{r.coverage_adjusted_cri != null ? num(r.coverage_adjusted_cri, 1) : '—'}</td>
              <td>{r.overall_confidence != null ? `${num(r.overall_confidence)}%` : '—'}</td>
              <td>{r.calculation_version || '—'}</td>
            </tr>
          ))}
        </Table>
      )}
      <Dummy title="Projected CRI and next reassessment" note="The backend does not project a future CRI or schedule reassessments yet.">
        <div className="stat-grid">
          <Stat label="CRI projection" value="74" note="When open goals close" />
          <Stat label="Next reassessment" value="42 days" note="13 December" />
          <Stat label="Stage-gate readiness" value="4 / 6" note="Gold gates ready" />
          <Stat label="Outcome measures" value="8" note="Across 4 pillars" />
        </div>
      </Dummy>
    </>
  );
}

function HistoryChart({ runs }: { runs: ScoreHistoryRow[] }) {
  const w = 600;
  const h = 200;
  const pad = 28;
  const x = (i: number) => (runs.length === 1 ? w / 2 : pad + (i * (w - pad * 2)) / (runs.length - 1));
  const y = (v: number) => h - pad - (v / 100) * (h - pad * 2);
  const points = runs.map((r, i) => `${x(i)},${y(r.overall_cri)}`).join(' ');
  return (
    <svg className="history-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`CRI over ${runs.length} runs, latest ${runs[runs.length - 1].overall_cri.toFixed(1)}`}>
      {[0, 25, 50, 75, 100].map((v) => (
        <g key={v}><line x1={pad} x2={w - pad} y1={y(v)} y2={y(v)} className="grid" /><text x={4} y={y(v) + 3} className="axis">{v}</text></g>
      ))}
      <polyline points={points} className="line-halo" aria-hidden="true" />
      <polyline points={points} className="line" />
      {runs.map((r, i) => (
        <circle key={r.id || i} cx={x(i)} cy={y(r.overall_cri)} r={4} className="dot"><title>{`${dateTime(r.created_at)}: ${r.overall_cri.toFixed(1)}`}</title></circle>
      ))}
    </svg>
  );
}
