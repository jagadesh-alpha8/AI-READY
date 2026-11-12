import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Stat, Table } from '../components/ui';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { approveBaseline, approveBaselineProvisional, getBaseline, returnBaseline, reviseBaseline } from '../services/scoring';
import type { Sprint, SprintBaseline } from '../types/api';
import { errorMessage, statusOf } from '../utils/errors';
import { dateTime, humanize, num, pct } from '../utils/format';

type Decision = 'approve' | 'provisional' | 'return' | 'revise';

/**
 * The baseline decision cycle. GET /baseline opens a pending baseline the first time (and moves the sprint to
 * baseline review), so this page loads it only after an explicit click when the sprint is not yet in review.
 */
export function BaselineApproval() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

const IN_REVIEW = new Set(['baseline_pending', 'baseline_approved', 'report_ready', 'completed']);

function Body({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const { reload } = useSprint();
  const [opened, setOpened] = useState(IN_REVIEW.has(sprint.status));
  const data = useResource<SprintBaseline>(() => getBaseline(sprint.id), `baseline:${sprint.id}`, opened);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'warn'; text: string } | null>(null);

  if (!opened) {
    return (
      <>
        <PageHeading page="baseline" />
        <Empty title="Baseline review not opened" action={can('sprint.manage') && (
          <button className="primary-action" onClick={() => setOpened(true)}>Open baseline review</button>
        )}>
          Opening the review takes the current score as the proposed baseline and moves the sprint to baseline review.
        </Empty>
      </>
    );
  }

  const d = data.data;
  const b = d?.baseline;
  const incomplete = !!d?.processing && !d.processing.complete;
  const decide = async (kind: Decision, v: Record<string, string>) => {
    if (!b) return;
    try {
      if (kind === 'approve') await approveBaseline(sprint.id, b.scoring_run_id, v.comments, v.override || '');
      else if (kind === 'provisional') await approveBaselineProvisional(sprint.id, b.scoring_run_id, v.comments, v.override || '');
      else if (kind === 'return') await returnBaseline(sprint.id, v.comments);
      else await reviseBaseline(sprint.id, v.comments);
    } catch (e) {
      // 409: the data changed after this preview; the server decided nothing and sends the new preview.
      if (statusOf(e) === 409) {
        await data.refetch();
        setMsg({ tone: 'warn', text: 'The score changed since this preview. Nothing was decided; check the new figures and decide again.' });
        return;
      }
      throw e;
    }
    await Promise.all([data.refetch(), reload()]);
    setMsg({ tone: 'success', text: kind === 'revise' ? 'A new baseline cycle is open on the current data.' : `Baseline ${kind === 'return' ? 'returned' : kind === 'provisional' ? 'approved provisionally' : 'approved'}.` });
  };

  return (
    <>
      <PageHeading page="baseline" actions={can('sprint.manage') && b && (
        b.status === 'pending' ? (
          <>
            <button className="secondary-button" onClick={() => setDecision('return')}>Return</button>
            <button className="secondary-button" disabled={!d?.can_approve} onClick={() => setDecision('provisional')}>Approve provisionally</button>
            <button className="primary-action" disabled={!d?.can_approve} onClick={() => setDecision('approve')}>Approve baseline</button>
          </>
        ) : <button className="secondary-button" onClick={() => setDecision('revise')}>Revise baseline</button>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {data.loading && !d ? <Loading label="Preparing the baseline…" /> : data.error ? <ErrorState error={data.error} onRetry={() => void data.refetch()} /> : b && (
        <>
          <div className="stat-grid">
            <Stat label="Baseline CRI" value={num(b.overall_cri, 1)} note={b.coverage_adjusted_cri != null ? `Coverage-adjusted ${num(b.coverage_adjusted_cri, 1)}` : 'From the scoring run on screen'} />
            <Stat label="Confidence" value={pct(b.overall_confidence)} />
            <Stat label="Status" value={<Pill status={b.status} label={humanize(b.status)} />} note={b.approved_by_name ? `${b.approved_by_name} · ${dateTime(b.approved_at)}` : `Calculated ${dateTime(b.scoring_run_calculated_at)}`} />
            <Stat label="Processing" value={incomplete ? 'Incomplete' : 'Complete'} note={d?.processing?.description} />
          </div>
          {d?.baseline_is_current === false && <Notice tone="warn">The data changed after this baseline was decided. Revise it to decide on the current score.</Notice>}
          {d?.refreshed && <Notice tone="info">The preview was refreshed with the latest calculation.</Notice>}
          {!d?.can_approve && b.status === 'pending' && <Notice tone="info">Approval is not available yet: settle the blocking gaps below or finish processing.</Notice>}
          {b.comments && <Panel title="Decision comments"><p>{b.comments}</p></Panel>}
          {!!d?.high_priority_gaps?.length && (
            <Panel title="High-priority gaps still open" sub="Approving now records the baseline with these open">
              <Table columns={['Gap', 'Pillar', 'Priority', 'Impact']}>
                {d.high_priority_gaps.map((g) => (
                  <tr key={g.id}><td>{g.title}</td><td>{g.pillar_label}</td><td><Pill status={g.priority} /></td><td>−{g.score_impact}</td></tr>
                ))}
              </Table>
            </Panel>
          )}
          <Panel title="History">
            {!b.history.length ? <p className="muted">No decisions yet.</p> : (
              <ol className="fact-history">
                {b.history.map((h) => <li key={h.id}><b>{humanize(h.action)}</b> by {h.user_name} · {dateTime(h.created_at)}{h.comments && <span className="cell-sub">{h.comments}</span>}</li>)}
              </ol>
            )}
          </Panel>
        </>
      )}
      {decision && (
        <ActionDialog
          title={decision === 'approve' ? 'Approve the baseline' : decision === 'provisional' ? 'Approve provisionally' : decision === 'return' ? 'Return for more work' : 'Revise the baseline'}
          confirmLabel={decision === 'return' ? 'Return' : decision === 'revise' ? 'Open new cycle' : 'Approve'}
          description={decision === 'approve' || decision === 'provisional' ? `This decides exactly the calculation on screen (CRI ${num(b?.overall_cri, 1)}). If the data changed since, nothing is decided.` : undefined}
          fields={[
            { name: 'comments', label: decision === 'revise' ? 'Reason for revising' : 'Comments', type: 'textarea', required: decision !== 'approve' },
            ...((decision === 'approve' || decision === 'provisional') && incomplete
              ? [{ name: 'override', label: 'Documents are still processing: reason to decide anyway', type: 'textarea' as const, required: true }] : []),
          ]}
          onSubmit={(v) => decide(decision, v).catch((e) => { throw new Error(errorMessage(e)); })}
          onClose={() => setDecision(null)} />
      )}
    </>
  );
}
