import { useState } from 'react';
import { ActionDialog, Notice } from '../components/ui';
import type { useCapability } from '../hooks/useCapability';
import { useResource } from '../hooks/useResource';
import { getReportReadiness, publishResult, startSecondLayerJob, type SecondLayerOperation } from '../services/capability';
import type { Job, ReportReadiness } from '../types/capability';
import { newKey } from '../utils/capability';
import { errorMessage } from '../utils/errors';
import { dateTime } from '../utils/format';

type Cap = ReturnType<typeof useCapability>;
type Pending = { kind: 'publish'; run: Job } | { kind: 'withdraw' } | { kind: 'write'; run: Job; operation: SecondLayerOperation };

const JOB_TEXT: Record<string, { label: string; text: string }> = {
  explain: { label: 'Write the score explanations', text: 'One model call per area, nine in all (a second only to fix the first).' },
  next_steps: { label: 'Write the next steps', text: 'One model call per step the reports show (a second only to fix the first).' },
};

/**
 * InGage staff only: which result the college sees (capability/publication.py), and whether each result's reports
 * are ready. Nothing is published by itself, a final result included; a college can't download a report that is
 * still a draft.
 */
export function PublishPanel({ sprintId, cap }: { sprintId: string; cap: Cap }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const completed = (cap.runs.data?.results || []).filter((r) => r.status === 'completed').slice(0, 6);
  const published = cap.published;

  const confirm = async (values: Record<string, string>) => {
    if (!pending) return;
    if (pending.kind === 'write') {
      // Writing jobs run on the Stage 1 run; for a final result they write for it with options.final.
      const final = pending.run.stage === 'final';
      const target = final ? pending.run.provisional_run_id || '' : pending.run.id;
      await startSecondLayerJob(sprintId, target, pending.operation, newKey(), final ? { final: true } : {});
      setMsg({ tone: 'success', text: `${JOB_TEXT[pending.operation].label}: started. It takes a few minutes; refresh this page to see the reports' state.` });
      return;
    }
    const run = pending.kind === 'publish' ? pending.run.id : null;
    await publishResult(sprintId, run, values.note || '');
    await cap.runs.refetch();
    setMsg({ tone: 'success', text: run ? 'Published. The college now sees this result.' : 'Withdrawn. The college sees no result until one is published.' });
  };

  return (
    <section className="surface surface-pad" style={{ marginTop: 24 }}>
      <div className="section-head">
        <div>
          <h2>What the college sees</h2>
          <p>{published
            ? `Published: ${published.stage === 'final' ? 'final result' : 'Stage 1 result'} of ${dateTime(completed.find((r) => r.id === published.run_id)?.created_at) || published.run_id.slice(0, 8)}, on ${dateTime(published.published_at)}${published.published_by ? ` by ${published.published_by}` : ''}.`
            : 'Nothing is published. The college sees no result until you publish one.'}</p>
        </div>
        {published && <button className="secondary-button" onClick={() => setPending({ kind: 'withdraw' })}>Withdraw</button>}
      </div>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {!completed.length ? <p className="muted">No completed result yet.</p> : (
        <div className="ws-publish-list">
          {completed.map((run) => (
            <PublishRow key={run.id} sprintId={sprintId} run={run} current={published?.run_id === run.id}
              onPublish={() => setPending({ kind: 'publish', run })}
              onWrite={(operation) => setPending({ kind: 'write', run, operation })} />
          ))}
        </div>
      )}
      {pending && (
        <ActionDialog
          title={pending.kind === 'publish' ? 'Publish this result for the college?'
            : pending.kind === 'withdraw' ? 'Withdraw the published result?' : `${JOB_TEXT[pending.operation].label}?`}
          description={pending.kind === 'publish'
            ? 'The college\'s screens and reports switch to this result. Its reports can be downloaded only once their text is written and checked.'
            : pending.kind === 'withdraw' ? 'The college sees "Your result is being prepared" until another result is published.'
              : `${JOB_TEXT[pending.operation].text} This uses model credits. One writing job runs at a time: start the other when this one has finished.`}
          fields={pending.kind === 'write' ? [] : [{ name: 'note', label: 'Note (optional, for InGage)', type: 'text' }]}
          confirmLabel={pending.kind === 'publish' ? 'Publish' : pending.kind === 'withdraw' ? 'Withdraw' : 'Start'}
          danger={pending.kind === 'withdraw'}
          onSubmit={confirm}
          onClose={() => setPending(null)}
        />
      )}
    </section>
  );
}

function PublishRow({ sprintId, run, current, onPublish, onWrite }: {
  sprintId: string; run: Job; current: boolean; onPublish: () => void; onWrite: (operation: SecondLayerOperation) => void;
}) {
  const readiness = useResource<ReportReadiness>(() => getReportReadiness(sprintId, run.id), `ws-ready:${run.id}`);
  const r = readiness.data;
  const steps = r?.next_steps;
  // The reasons say which text is missing, out of date or on plain wording (publication.readiness).
  const needsExplain = !!r && r.reasons.some((x) => x.includes('explanations'));
  const needsSteps = !!r && r.reasons.some((x) => x.includes('next steps'));
  return (
    <div className="ws-publish-row">
      <div>
        <strong>{run.stage === 'final' ? 'Final result' : 'Stage 1 result'}</strong> <small>{dateTime(run.created_at)} · {run.id.slice(0, 8)}</small>
        {current && <span className="tag" style={{ marginLeft: 8 }}>Published</span>}
        {readiness.loading && !r ? <p className="muted">Checking the reports…</p> : readiness.error ? <p className="muted">{errorMessage(readiness.error)}</p> : r && (
          r.ready ? <p className="muted">Reports ready for the college.{steps ? ` ${steps.written_steps} of ${steps.steps} steps written.` : ''}</p> : (
            <p className="muted"><span className="tag amber">Draft</span> {r.reasons.join(' ')}</p>
          ))}
        {r?.warnings.map((w) => <p key={w} className="muted" style={{ fontSize: 12 }}>{w}</p>)}
      </div>
      <div className="ws-row">
        {needsExplain && <button className="secondary-button" onClick={() => onWrite('explain')}>{JOB_TEXT.explain.label}</button>}
        {needsSteps && <button className="secondary-button" onClick={() => onWrite('next_steps')}>{JOB_TEXT.next_steps.label}</button>}
        {!current && <button className="primary-action" onClick={onPublish}>Publish</button>}
      </div>
    </div>
  );
}
