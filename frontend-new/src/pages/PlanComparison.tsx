import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { cancelPlanEvaluation, downloadPlanEvaluation, getPlanEvaluation, listPlanEvaluations, startPlanEvaluation } from '../services/capability';
import type { Sprint } from '../types/api';
import type { CapabilityPage } from '../types/capability';
import type { PlanComparison as Comparison, PlanEvaluationJob } from '../types/workflow';
import { newKey } from '../utils/capability';
import { dateTime, humanize } from '../utils/format';

export function PlanComparison() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const cap = useCapability(sprint.id);
  const runId = cap.run.data?.id || '';
  const list = useResource<CapabilityPage<PlanEvaluationJob>>(() => listPlanEvaluations(sprint.id, runId), `pe:${runId}`, !!runId);
  const [chosen, setChosen] = useState('');
  const shownId = chosen || list.data?.results.find((j) => j.status === 'completed')?.id || '';
  const shown = useResource<Comparison>(() => getPlanEvaluation(sprint.id, runId, shownId), `pe1:${shownId}`, !!shownId);
  const [writing, setWriting] = useState(false);
  const { busy, msg, setMsg, run } = useRunner();
  const [key, setKey] = useState(newKey);
  usePolling(() => void list.refetch(), (list.data?.results || []).some((j) => j.status === 'queued' || j.status === 'running'), 5000);

  if (cap.loading) return <><PageHeading page="plancompare" /><Loading /></>;
  if (!runId) {
    return (
      <>
        <PageHeading page="plancompare" />
        <Empty title="No completed assessment" action={<PageLink to="assessment" className="primary-action">Run an assessment</PageLink>}>A plan is compared with a completed run.</Empty>
      </>
    );
  }
  const c = shown.data;
  return (
    <>
      <PageHeading page="plancompare" actions={can('recommendations.generate') && (
        <button className="primary-action" disabled={!cap.enabled} onClick={() => setWriting(true)}>Compare a plan</button>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Panel title="Comparisons" sub={`Against run ${runId.slice(0, 8)}`}>
        {list.loading && !list.data ? <Loading /> : list.error ? <ErrorState error={list.error} /> : !list.data?.results.length ? <p className="muted">No plans compared yet.</p> : (
          <Table columns={['Comparison', 'Started', 'Status', '']}>
            {list.data.results.map((j) => (
              <tr key={j.id}>
                <td><b>{j.id.slice(0, 8)}</b>{j.id === shownId && <small className="cell-sub">Shown below</small>}</td>
                <td>{dateTime(j.created_at)}</td>
                <td><Pill status={j.status === 'queued' ? 'pending' : j.status} label={j.status} /></td>
                <td>
                  <div className="row-actions nowrap">
                    {j.status === 'completed' && j.id !== shownId && <button className="secondary-button" onClick={() => setChosen(j.id)}>Show</button>}
                    {(j.status === 'queued' || j.status === 'running') && <button className="secondary-button" disabled={!!busy} onClick={() => void run(`c:${j.id}`, async () => { await cancelPlanEvaluation(sprint.id, runId, j.id); await list.refetch(); }, 'Comparison cancelled.')}>Cancel</button>}
                    {j.status === 'completed' && (['html', 'json'] as const).map((f) => (
                      <button key={f} className="secondary-button" disabled={!!busy} onClick={() => void run(`d:${f}`, () => downloadPlanEvaluation(sprint.id, runId, j.id, f))}>{f.toUpperCase()}</button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
      {shownId && (shown.loading && !c ? <Loading /> : shown.error ? <ErrorState error={shown.error} /> : c && (
        <>
          {c.error && <Notice tone="error">{c.error.next_action || c.error.error_code}</Notice>}
          <Panel title="The plan as written"><p className="muted" style={{ whiteSpace: 'pre-wrap' }}>{c.original_text}</p></Panel>
          {c.comparison && (
            <>
              <Panel title="Suggested changes" sub={c.comparison.comparison_basis}>
                {c.comparison.improvement.constraint_note && <Notice tone="info">{c.comparison.improvement.constraint_note}</Notice>}
                <Table columns={['Change', 'Action', 'Why', 'Owner', 'Completion evidence']}>
                  {c.comparison.improvement.changes.map((ch, i) => (
                    <tr key={i}><td>{humanize(ch.operation)}</td><td>{ch.action}</td><td>{ch.why}</td><td>{ch.suggested_owner}</td><td>{ch.completion_evidence}</td></tr>
                  ))}
                </Table>
              </Panel>
              {c.comparison.limitations.length > 0 && <Panel title="Limitations"><ul className="plain-list">{c.comparison.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Panel>}
            </>
          )}
        </>
      ))}
      {writing && (
        <ActionDialog title="Compare a written plan" confirmLabel="Compare (uses credits)"
          description="Paste the institution's own transformation plan. It is compared with the assessment's evidence; the score does not change."
          fields={[{ name: 'plan', label: 'Plan text', type: 'textarea', required: true }]}
          onSubmit={async (v) => { const res = await startPlanEvaluation(sprint.id, runId, v.plan, key); setKey(newKey()); setChosen(res.data.id); await list.refetch(); setMsg({ tone: 'success', text: 'Comparison started.' }); }}
          onClose={() => setWriting(false)} />
      )}
    </>
  );
}
