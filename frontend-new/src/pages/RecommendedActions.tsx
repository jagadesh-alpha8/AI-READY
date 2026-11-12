import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { cancelAdvice, getAdvice, listAdvice, startAdvice, updateActionState } from '../services/capability';
import type { Sprint } from '../types/api';
import type { CapabilityAction, CapabilityPage, CapabilityRecommendation, Job } from '../types/capability';
import type { ActionState } from '../types/workflow';
import { isActive, newKey, stateLabel } from '../utils/capability';
import { dateTime, humanize } from '../utils/format';

export function RecommendedActions() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  return (
    <>
      <PageHeading page="actions" />
      <p className="muted">Audit recommendations (from gaps, facts and pillars) are managed in <PageLink to="plan">Transformation plan</PageLink>.</p>
      <CapabilityAdvice sprint={sprint} />
    </>
  );
}

// --- grounded advice for the latest completed capability run ---------------------------------------------

function CapabilityAdvice({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const cap = useCapability(sprint.id);
  const runId = cap.run.data?.id || '';
  const list = useResource<CapabilityPage<Job>>(() => listAdvice(sprint.id, runId), `adv-list:${runId}`, !!runId);
  const newest = list.data?.results[0] || null;
  const completedId = list.data?.results.find((a) => a.status === 'completed')?.id || '';
  const advice = useResource<CapabilityRecommendation>(() => getAdvice(sprint.id, runId, completedId), `adv:${completedId}`, !!completedId);
  const { busy, msg, setMsg, run } = useRunner();
  const [confirming, setConfirming] = useState(false);
  const [key] = useState(newKey);
  const [editing, setEditing] = useState<CapabilityAction | null>(null);
  usePolling(() => void list.refetch(), isActive(newest), 4000);

  const states = new Map((advice.data?.action_states || []).map((s) => [s.condition_id, s]));
  const actions = advice.data?.plan.actions || cap.run.data?.deterministic_plan?.actions || [];
  const tailored = new Map((advice.data?.tailoring?.advice || []).map((t) => [String(t.condition_id || t.id || ''), String(t.advice || t.text || '')]));
  const count = (st: string) => actions.filter((a) => (states.get(a.id)?.status || 'proposed') === st).length;

  if (cap.loading) return <Loading />;
  if (cap.error) return <ErrorState error={cap.error} />;
  if (!runId) return <Empty title="No completed assessment" action={<PageLink to="assessment" className="primary-action">Run an assessment</PageLink>}>Advice is grounded in a completed run.</Empty>;

  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Panel title="Grounded advice" sub={newest ? `Latest request ${dateTime(newest.created_at)} · run ${runId.slice(0, 8)}` : `For run ${runId.slice(0, 8)}; the plan below is the deterministic one`}
        actions={newest && <Pill status={newest.status === 'queued' ? 'pending' : newest.status} label={newest.status} />}>
        {isActive(newest) && <Notice tone="info">Writing advice. This refreshes every few seconds.</Notice>}
        {advice.data?.fallback && <Notice tone="warn">No model-tailored advice was produced; the actions are the deterministic plan.</Notice>}
        {advice.data?.error && <Notice tone="error">{advice.data.error.next_action || advice.data.error.error_code}</Notice>}
        <div className="button-row">
          {can('recommendations.generate') && <button className="primary-action" disabled={!cap.enabled || isActive(newest) || !!busy} onClick={() => setConfirming(true)}>Write tailored advice</button>}
          {isActive(newest) && newest && can('recommendations.generate') && (
            <button className="secondary-button" disabled={!!busy} onClick={() => void run('cancel', async () => { await cancelAdvice(sprint.id, runId, newest.id); await list.refetch(); }, 'Cancelled. A call already in flight may still finish and be billed.')}>Cancel</button>
          )}
        </div>
      </Panel>
      <div className="stat-grid">
        <Stat label="Actions" value={actions.length} />
        <Stat label="In progress" value={count('in_progress')} />
        <Stat label="Completed" value={count('completed')} note="Reassess to count new evidence" />
        <Stat label="Dismissed" value={count('dismissed')} />
      </div>
      {!actions.length ? <Empty title="No actions">The assessment found nothing to act on.</Empty> : (
        <Table columns={['Action', 'Requirement', 'Completion evidence', 'Owner', 'Feasibility', 'Status', '']}>
          {actions.map((a) => {
            const st = states.get(a.id);
            return (
              <tr key={a.id}>
                <td className="source-cell"><strong>{a.indicator} · {a.id}</strong><small className="cell-sub clamp-2">{tailored.get(a.id) || a.suggestion}</small></td>
                <td><span className="clamp-2" title={a.requirement}>{a.requirement}</span>{a.state && <small className="cell-sub">{stateLabel(a.state)}</small>}</td>
                <td><span className="clamp-2">{a.completion_evidence}</span></td>
                <td>{st?.owner || '—'}</td>
                <td>{humanize(st?.feasibility || 'unreviewed')}</td>
                <td><Pill status={st?.status === 'completed' ? 'active' : st?.status === 'dismissed' ? 'neutral' : 'pending'} label={humanize(st?.status || 'proposed')} /></td>
                <td>{completedId && can('recommendations.generate') && <button className="secondary-button" onClick={() => setEditing(a)}>Update</button>}</td>
              </tr>
            );
          })}
        </Table>
      )}
      {!completedId && actions.length > 0 && <p className="muted">Tracking owner and status needs tailored advice first (it records the actions it was written for).</p>}
      {confirming && (
        <ActionDialog title="Write tailored advice?" confirmLabel="Start (uses credits)" fields={[]}
          description="This uses model credits. Advice is written from the run's frozen evidence and never changes its score."
          onSubmit={async () => { await startAdvice(sprint.id, runId, key); await list.refetch(); setMsg({ tone: 'success', text: 'Advice requested.' }); }}
          onClose={() => setConfirming(false)} />
      )}
      {editing && completedId && (
        <ActionDialog title={`Update ${editing.id}`} confirmLabel="Save"
          fields={[
            { name: 'owner', label: 'Owner', initial: states.get(editing.id)?.owner || '' },
            { name: 'feasibility', label: 'Feasibility', type: 'select', required: true, initial: states.get(editing.id)?.feasibility || 'unreviewed', options: ['unreviewed', 'feasible', 'blocked'].map((v) => ({ value: v, label: humanize(v) })) },
            { name: 'status', label: 'Status', type: 'select', required: true, initial: states.get(editing.id)?.status || 'proposed', options: ['proposed', 'in_progress', 'completed', 'dismissed'].map((v) => ({ value: v, label: humanize(v) })) },
          ]}
          onSubmit={async (v) => {
            await updateActionState(sprint.id, runId, completedId, editing.id, { owner: v.owner, feasibility: v.feasibility as ActionState['feasibility'], status: v.status as ActionState['status'] });
            await advice.refetch();
            setMsg({ tone: 'success', text: 'Workflow updated. Assessment scores are unchanged; reassess new evidence.' });
          }}
          onClose={() => setEditing(null)} />
      )}
    </>
  );
}
