import { useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getScoreHistory, recalculateScore } from '../services/scoring';
import type { Page, ScoreHistoryRow, Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { dateTime, num, rows } from '../utils/format';
import { Empty, ErrorState, Loading, Notice, Panel, Table } from './ui';

/** Every audit CRI run (each an immutable snapshot) and the reassess control (POST /score adds a run). */
export function ScoreHistory({ sprint, onReassessed }: { sprint: Sprint; onReassessed?: () => void }) {
  const { can } = useAccess();
  const history = useResource<ScoreHistoryRow[] | Page<ScoreHistoryRow>>(() => getScoreHistory(sprint.id), `hist:${sprint.id}`);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const runs = [...rows(history.data)].sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  const first = runs[0];
  const last = runs[runs.length - 1];

  const reassess = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await recalculateScore(sprint.id);
      setMsg({ tone: 'success', text: `Reassessment recorded: CRI ${num(res.data.overall_cri, 1)}. Earlier results are kept.` });
      await history.refetch();
      onReassessed?.();
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  return (
    <Panel title="Score history" sub={last && runs.length > 1 ? `${last.overall_cri - first.overall_cri >= 0 ? '+' : ''}${num(last.overall_cri - first.overall_cri, 1)} since the first of ${runs.length} runs` : 'Every scoring run is kept'}
      actions={can('sprint.manage') && <button className="secondary-button" disabled={busy} onClick={() => void reassess()}>{busy ? 'Reassessing…' : 'Reassess now'}</button>}>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {history.loading ? <Loading /> : history.error ? <ErrorState error={history.error} onRetry={() => void history.refetch()} /> :
        runs.length === 0 ? <Empty title="No assessment runs yet" /> : (
          <>
            <HistoryChart runs={runs} />
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
          </>
        )}
    </Panel>
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
