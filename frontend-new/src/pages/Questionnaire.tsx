import { useMemo, useRef, useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat, Table, Tabs } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import {
  addAdditionalEvidence, answerFollowUp, answerQuestion, cancelSecondLayerJob, getNextQuestion, getResponse,
  listAdditionalEvidence, listSecondLayerJobs, startSecondLayerJob,
  type AdditionalEvidenceItem, type Layer2Next, type Layer2Progress, type Layer2Response, type SecondLayerJob,
  type SecondLayerJobList, type SecondLayerOperation,
} from '../services/capability';
import { startExtraction, uploadDocument } from '../services/documents';
import { decideReviewCase, getReviewBatch, startReviewBatch } from '../services/facts';
import type { Sprint } from '../types/api';
import type { Run } from '../types/capability';
import type { ReviewBatch, ReviewCase } from '../types/workflow';
import { newKey } from '../utils/capability';
import { errorMessage } from '../utils/errors';
import { dateTime, humanize, tidyText, valueText } from '../utils/format';

/**
 * The questionnaire of the new flow (Siddharth / Harsha, 12 Nov 2026), one item at a time, each with an answer box,
 * a document upload and Skip:
 *   line 1, before the assessment: the review items on the submitted evidence (guided review batch);
 *   line 2, after the provisional score: follow-up questions about the evidence and "nothing found" questions
 *           (second assessment layer, at most one follow-up per answer);
 *   additional evidence: documents the institution thinks were missed, for at least one area / indicator / requirement.
 */
const TABS = [
  { key: 'line1', label: '1 · Evidence review' },
  { key: 'line2', label: '2 · Follow-up questions' },
  { key: 'extra', label: 'Additional evidence' },
] as const;
type Tab = (typeof TABS)[number]['key'];

/**
 * Shown on the questionnaire's first screen. Decided with Harsha on 12 Nov 2026: answers (including "don't know" and
 * skips) can lower a score, and the college is told so up front. The wording comes from Siddharth / Harsha; until it
 * arrives this stays empty and nothing is shown.
 */
const QUESTIONNAIRE_NOTICE = '';

export function Questionnaire() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const [tab, setTab] = useState<Tab>('line1');
  const cap = useCapability(sprint.id);
  return (
    <>
      <PageHeading page="questionnaire" />
      {QUESTIONNAIRE_NOTICE && <Notice tone="info">{QUESTIONNAIRE_NOTICE}</Notice>}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Questionnaire" />
      {tab === 'line1' && <LineOne sprint={sprint} />}
      {tab !== 'line1' && (cap.loading ? <Loading /> : cap.error ? <ErrorState error={cap.error} /> : !cap.run.data ? (
        <Empty title="No provisional score yet" action={<PageLink to="assessment" className="primary-action">Go to the assessment</PageLink>}>
          The follow-up questions and additional evidence belong to a completed assessment run. Finish the evidence review, then run the assessment.
        </Empty>
      ) : tab === 'line2'
        ? <LineTwo sprint={sprint} run={cap.run.data} runId={cap.provisionalId} onFinal={() => void cap.runs.refetch()} />
        : <AdditionalEvidence sprint={sprint} run={cap.run.data} runId={cap.provisionalId} />)}
    </>
  );
}

// --- shared: upload chosen files to the sprint, return their document ids ---------------------------------------

async function uploadAll(sprintId: string, files: File[]): Promise<string[]> {
  const ids: string[] = [];
  for (const f of files) ids.push((await uploadDocument(sprintId, f, 'unclassified')).data.id);
  // An answer is checked once its documents are extracted, so start processing exactly these files.
  if (ids.length) await startExtraction(sprintId, ids);
  return ids;
}

/** The prominent upload control used by every item. */
function UploadBox({ files, onChange, required }: { files: File[]; onChange: (f: File[]) => void; required?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="upload-zone" onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); onChange([...files, ...Array.from(e.dataTransfer.files)]); }}>
      <div>
        <div className="upload-icon" aria-hidden="true">⇧</div>
        <strong>{required ? 'Attach the supporting document' : 'Attach a supporting document'}</strong>
        <span>A typed answer counts only when a document supports it.</span>
        <div className="upload-controls">
          <input ref={input} type="file" multiple className="sr-only" id="q-files" onChange={(e) => { onChange([...files, ...Array.from(e.target.files || [])]); if (input.current) input.current.value = ''; }} />
          <label htmlFor="q-files" className="primary-action as-button">Choose files</label>
        </div>
        {files.length > 0 && (
          <ul className="plain-list">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>{f.name} <button type="button" className="link-button" onClick={() => onChange(files.filter((_, j) => j !== i))}>Remove</button></li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ProgressLine({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="bar-row">
      <span>{label}</span>
      <div className="bar-track" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total}><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
      <b>{done}/{total}</b>
    </div>
  );
}

// --- line 1: review items on the submitted evidence, one at a time -----------------------------------------------

function LineOne({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const batch = useResource<ReviewBatch>(() => getReviewBatch(sprint.id), `rb:${sprint.id}`);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const b = batch.data;

  const open = useMemo(() => (b?.cases || []).filter((c) => !b?.decisions[c.id] && c.state !== 'decided'), [b]);
  const queue = [...open.filter((c) => !skipped.includes(c.id)), ...open.filter((c) => skipped.includes(c.id))];
  const current = queue[0] || null;
  const decided = (b?.cases.length || 0) - open.length;

  const start = async () => {
    setBusy(true);
    try { batch.setData((await startReviewBatch(sprint.id)).data); } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  if (batch.loading && !b) return <Loading />;
  if (batch.error) return <ErrorState error={batch.error} onRetry={() => void batch.refetch()} />;
  if (!b?.started) {
    return (
      <Empty title="Evidence review not started" action={can('facts.review') && (
        <button className="primary-action" disabled={busy} onClick={() => void start()}>{busy ? 'Preparing…' : 'Start the evidence review'}</button>
      )}>
        Before the assessment, a short list of items needs a decision: values that disagree and high-risk facts. They come one at a time.
      </Empty>
    );
  }
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Panel title="Before the assessment" sub="Conflicting values and high-risk facts on the evidence already submitted">
        <ProgressLine done={decided} total={b.cases.length} label="Answered" />
        {skipped.length > 0 && <p className="muted">{skipped.filter((id) => open.some((c) => c.id === id)).length} skipped (left as they are; they come back at the end).</p>}
      </Panel>
      {!current ? (
        <Empty title="Evidence review complete" action={<PageLink to="assessment" className="primary-action">Run the assessment</PageLink>}>
          Every review item has an answer. The assessment gives the provisional score; the follow-up questions come after it.
        </Empty>
      ) : (
        <ReviewItem key={current.id} sprint={sprint} item={current} position={decided + 1} total={b.cases.length}
          onSkip={() => setSkipped((s) => [...s.filter((x) => x !== current.id), current.id])}
          onDone={(next, text) => { batch.setData(next); setMsg({ tone: 'success', text }); }} />
      )}
    </>
  );
}

function ReviewItem({ sprint, item, position, total, onSkip, onDone }: {
  sprint: Sprint; item: ReviewCase; position: number; total: number; onSkip: () => void; onDone: (b: ReviewBatch, text: string) => void;
}) {
  const { can } = useAccess();
  const [choice, setChoice] = useState(item.alternatives.length === 1 ? item.alternatives[0].fact_ids[0] : '');
  const [answer, setAnswer] = useState('');
  const [reason, setReason] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!reason.trim()) { setError('Say briefly why (the basis for this answer).'); return; }
    if (item.kind === 'identity' && !choice) { setError('Choose the institution the documents belong to.'); return; }
    if (item.kind !== 'identity' && !answer.trim() && !choice) { setError('Choose the correct value, or type the correct one.'); return; }
    setBusy(true);
    try {
      const docs = files.length ? await uploadAll(sprint.id, files) : [];
      const factId = choice || item.alternatives[0]?.fact_ids[0];
      const body = item.kind === 'identity'
        ? { action: 'identity' as const, source_institution: choice, reason }
        : answer.trim()
          ? { action: 'correct' as const, fact_id: factId, value: answer.trim(), reason, source_document_id: docs[0] }
          : { action: (item.alternatives.length > 1 || item.conflict ? 'choose' : 'confirm') as 'choose' | 'confirm', fact_id: factId, reason, source_document_id: docs[0] };
      const res = await decideReviewCase(sprint.id, item.id, { ...body, optional_follow_up: !item.initial || undefined });
      onDone(res.data, 'Answer recorded.');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={`Item ${position} of ${total}`} sub={item.reason} actions={<Pill status={item.conflict ? 'blocked' : 'pending'} label={item.conflict ? 'Values disagree' : 'High-risk fact'} />}>
      <form onSubmit={submit} className="questionnaire-item">
        <h3>{item.question}</h3>
        {item.suggestion && <p><b>Suggested:</b> {tidyText(item.suggestion)}</p>}
        {item.affected_requirements.length > 0 && <p className="muted">Affects {item.affected_requirements.join(', ')}</p>}
        <fieldset className="check-list">
          <legend className="muted">{item.kind === 'identity' ? 'Which institution do these documents belong to?' : 'Which value is correct?'}</legend>
          {item.alternatives.map((alt, i) => (
            <label key={i} className="field inline">
              <input type="radio" name={`alt-${item.id}`} checked={item.kind === 'identity' ? choice === String(alt.value) : choice === alt.fact_ids[0]}
                onChange={() => { setChoice(item.kind === 'identity' ? String(alt.value) : alt.fact_ids[0]); setAnswer(''); }} />
              <span><b>{valueText(alt.value)}</b>
                {alt.excerpts.slice(0, 2).map((x) => <small key={x.fact_id} className="cell-sub">{x.filename}{x.page && `, p. ${x.page}`}: “{tidyText(x.quote)}”</small>)}
              </span>
            </label>
          ))}
        </fieldset>
        {item.kind !== 'identity' && (
          <label className="field"><span>Or type the correct value</span>
            <input value={answer} onChange={(e) => { setAnswer(e.target.value); if (e.target.value) setChoice(''); }} placeholder="Only if none of the values above is right" />
          </label>
        )}
        <UploadBox files={files} onChange={setFiles} />
        <label className="field"><span>Basis for your answer *</span>
          <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. The approved 2024 policy states 42 faculty." />
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="button-row">
          <button type="button" className="secondary-button" disabled={busy} onClick={onSkip}>Skip</button>
          {can('facts.review') && <button className="primary-action" disabled={busy}>{busy ? 'Saving…' : 'Submit answer'}</button>}
        </div>
      </form>
    </Panel>
  );
}

// --- line 2: follow-up and "nothing found" questions after the provisional score ---------------------------------

function LineTwo({ sprint, run, runId, onFinal }: { sprint: Sprint; run: Run; runId: string; onFinal: () => void }) {
  const next = useResource<{ next: Layer2Next | null; progress: Layer2Progress }>(() => getNextQuestion(sprint.id, runId), `l2:${runId}`);
  const [answered, setAnswered] = useState<Layer2Response[]>([]);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const p = next.data?.progress;
  const pending = answered.filter((r) => r.status === 'pending');

  // Responses come back "pending" until the check has run; refresh them while any is pending.
  usePolling(() => {
    void Promise.all(pending.map((r) => getResponse(sprint.id, runId, r.id).then((x) => x.data).catch(() => r)))
      .then((fresh) => {
        setAnswered((all) => all.map((r) => fresh.find((f) => f.id === r.id) || r));
        // A check that asks a follow-up puts it back in the queue as next.type = "follow_up".
        if (fresh.some((f) => f.status === 'checked')) void next.refetch();
      });
  }, pending.length > 0, 8000);

  if (next.loading && !next.data) return <Loading />;
  if (next.error) return <ErrorState error={next.error} onRetry={() => void next.refetch()} />;
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {p?.final_run_id && (
        <Notice tone="success">The final result has been published (run {p.final_run_id.slice(0, 8)}). Reports, recommendations and plan comparison now use it.</Notice>
      )}
      <SecondLayerJobs sprint={sprint} runId={runId} progress={p} onChange={() => void next.refetch()} onFinal={onFinal} />
      <div className="stat-grid">
        <Stat label="Questions" value={p?.questions ?? 0} note={`${p?.linked ? `${p.linked} more answered through linked questions · ` : ''}Provisional run ${runId.slice(0, 8)}${run.id === runId ? ` · ${dateTime(run.created_at)}` : ''}`} />
        <Stat label="Answered or skipped" value={p?.answered ?? 0} note={`${p?.open ?? 0} open`} />
        <Stat label="Checks waiting" value={p?.checks_waiting ?? 0} note="Answers are checked against the documents" />
        <Stat label="Follow-ups open" value={p?.follow_ups_open ?? 0} note="At most one per answer" />
      </div>
      {p && p.questions > 0 && (
        <Panel>
          <ProgressLine done={p.answered} total={p.questions} label="Questions answered" />
          <p className="muted">Questions come in order of the points they can earn, highest first. You can stop whenever you like; unanswered questions earn nothing back.</p>
        </Panel>
      )}
      {!p?.questions ? (
        <Empty title="No follow-up questions yet">Questions for this run have not been planned yet. Use “Plan follow-up questions” above (it uses model credits).</Empty>
      ) : !next.data?.next ? (
        <Empty title="All questions answered" action={<PageLink to="cri" className="primary-action">See the report</PageLink>}>
          {p.checks_waiting ? `${p.checks_waiting} answer(s) are still being checked against the documents.` : 'Every question has an answer or was skipped.'}
        </Empty>
      ) : (
        <QuestionItem key={`${next.data.next.type}:${next.data.next.response_id || next.data.next.question.id}`} sprint={sprint} runId={runId} item={next.data.next}
          position={(p.answered || 0) + 1} total={p.questions}
          onDone={(r, text) => { setAnswered((a) => [r, ...a]); setMsg({ tone: 'success', text }); void next.refetch(); }} />
      )}
      {answered.length > 0 && (
        <Panel title="Your answers this session" sub="A typed answer counts only when supporting evidence is found for it">
          {answered.map((r) => (
            <article key={r.id} className="condition">
              <div>
                <Pill status={r.status === 'pending' ? 'pending' : r.supported ? 'active' : 'neutral'}
                  label={r.status === 'pending' ? 'Being checked' : r.kind === 'dont_know' ? 'Skipped' : r.supported ? 'Supported by evidence' : 'No supporting evidence found'} />
                {' '}{r.parent_id ? 'Follow-up answer' : 'Answer'} · {dateTime(r.created_at)}
              </div>
              {r.answer && <p>{tidyText(r.answer)}</p>}
              {r.document_ids.length > 0 && <p className="muted">{r.document_ids.length} document(s) attached</p>}
              {r.status === 'checked' && <p className="muted">{r.passages_found} passage(s) found{r.dimensions.length ? ` · ${r.dimensions.map((d) => `${humanize(d.dimension_id)}: ${humanize(d.support)}`).join(', ')}` : ''}</p>}
              {!!r.search?.already_counted?.length && (
                <p className="muted">Already read in the first assessment, so it added nothing new: {r.search.already_counted.map((d) => d.name).join(', ')}</p>
              )}
              {r.follow_up && <p><b>Follow-up asked:</b> {r.follow_up}</p>}
            </article>
          ))}
        </Panel>
      )}
    </>
  );
}

// --- second-layer jobs: plan the questions, judge depth, publish the final result --------------------------------

const OPERATION_LABEL: Record<SecondLayerOperation, string> = {
  questions: 'Planning follow-up questions',
  checks: 'Checking answers and additional evidence',
  depth: 'Judging how deep the credited evidence goes',
  rejudge: 'Publishing the final result',
  explain: 'Writing score explanations',
};

/** Siddharth's job error codes, in plain words. */
const JOB_ERROR: Record<string, string> = {
  budget_exhausted: "This assessment's second-layer budget is spent. A consultant can raise it (manage.py layer2_budget).",
  not_ready: 'Not ready yet.',
  cancelled_by_user: 'The job was cancelled.',
  inference_stopped: 'The job was cancelled.',
  worker_lost: 'The job ran past its deadline and was stopped. Start it again.',
  provider_quota_exhausted: 'The AI provider refused the request (quota). Ask an administrator to check the provider account.',
  model_pricing_required: "The server's model has no price configured (AI_PRICING_JSON). Ask an administrator.",
  job_failed: 'The job failed. Ask an administrator to check the server logs.',
};

const isActiveJob = (j: SecondLayerJob) => j.status === 'queued' || j.status === 'running';

/** "Writing score explanations", plus "(final result)" for the job that starts by itself after publishing. */
const jobLabel = (j: SecondLayerJob) => `${OPERATION_LABEL[j.operation]}${j.operation === 'explain' && j.options?.final ? ' (final result)' : ''}`;

/** An explain job's result: { calls, explained, fallbacks, areas_with_problems: { area: count } }. */
function explainOutcome(r: Record<string, unknown> | null): string {
  if (!r) return 'Done';
  const num = (k: string) => (typeof r[k] === 'number' ? (r[k] as number) : 0);
  const problems = Object.keys((r.areas_with_problems as Record<string, number> | undefined) || {}).length;
  return [`${num('explained')} requirements explained in ${num('calls')} calls`,
    num('fallbacks') ? `${num('fallbacks')} plain factual versions` : '',
    problems ? `${problems} area${problems === 1 ? '' : 's'} with problems` : ''].filter(Boolean).join(' · ');
}

function jobOutcome(j: SecondLayerJob): string {
  if (j.status === 'completed' && j.operation === 'explain') return explainOutcome(j.result);
  if (j.status === 'completed') return j.operation === 'rejudge' && j.final_run_id ? `Final run ${j.final_run_id.slice(0, 8)}` : 'Done';
  if (!j.error_code) return j.detail || '';
  const words = JOB_ERROR[j.error_code] || j.error_code;
  return j.detail && !['cancelled_by_user', 'inference_stopped'].includes(j.error_code) ? `${words} ${j.detail}` : words;
}

/**
 * The provisional run's second-layer jobs: "Plan follow-up questions" (without it a run has no questions), "Judge
 * evidence depth", and "Publish final result" once the college has finished answering. One job runs at a time;
 * the active one shows its progress and can be cancelled. Answer checks start by themselves.
 */
function SecondLayerJobs({ sprint, runId, progress, onChange, onFinal }: {
  sprint: Sprint; runId: string; progress?: Layer2Progress; onChange: () => void; onFinal: () => void;
}) {
  const { can } = useAccess();
  const jobs = useResource<SecondLayerJobList>(() => listSecondLayerJobs(sprint.id, runId), `slj:${runId}`);
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const list = jobs.data?.results || [];
  const active = list.find(isActiveJob) || null;
  const checking = !!progress?.checks_waiting;

  // Poll while a job is queued or running, or answers wait for their check job; report each job that finishes.
  usePolling(() => {
    void listSecondLayerJobs(sprint.id, runId).then(({ data }) => {
      const before = new Map(list.map((j) => [j.id, j.status]));
      for (const j of data.results) {
        const was = before.get(j.id);
        if (was && (was === 'queued' || was === 'running') && !isActiveJob(j)) {
          onChange();
          if (j.operation === 'rejudge' && j.status === 'completed' && j.final_run_id) onFinal();
          setMsg(j.status === 'completed'
            ? { tone: 'success', text: `${jobLabel(j)}: ${j.operation === 'explain' ? explainOutcome(j.result) : 'done'}.${j.final_run_id ? ' The final result is published; its explanations start by themselves.' : ''}` }
            : { tone: 'error', text: `${jobLabel(j)}: ${jobOutcome(j)}` });
        }
      }
      jobs.setData(data);
    }).catch(() => undefined);
  }, !!active || checking, 5000);

  const start = async (operation: SecondLayerOperation, options: Record<string, boolean> = {}) => {
    setBusy(operation);
    setMsg(null);
    try {
      await startSecondLayerJob(sprint.id, runId, operation, newKey(), options);
      setMsg({ tone: 'info', text: `${OPERATION_LABEL[operation]} started. This panel updates when it finishes.` });
      await jobs.refetch();
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(''); }
  };
  const cancel = async (j: SecondLayerJob) => {
    setBusy('cancel');
    try {
      const res = await cancelSecondLayerJob(sprint.id, runId, j.id);
      setMsg({ tone: 'info', text: res.data.note || 'Cancelled.' });
      await jobs.refetch();
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(''); }
  };

  if (jobs.loading && !jobs.data) return <Loading label="Loading second-layer jobs…" />;
  if (jobs.error) return <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />;
  const manage = can('sprint.manage');
  const p = progress;
  const hasQuestions = !!p?.questions;
  const finished = !!p && hasQuestions && !p.open && !p.checks_waiting && !p.follow_ups_open;
  const budget = jobs.data?.budget;
  const disabled = !jobs.data?.enabled || !!active || !!busy;
  // Final results are explained automatically; the provisional run's explanations are written on request.
  const explained = list.some((j) => j.operation === 'explain' && !j.options?.final && j.status === 'completed');

  return (
    <Panel title="Follow-up questions and final result" sub="Background jobs on the provisional run; each uses model credits from this assessment's budget"
      actions={manage && (
        <div className="row-actions">
          {!hasQuestions && <button className="primary-action" disabled={disabled} onClick={() => void start('questions')}>{busy === 'questions' ? 'Starting…' : 'Plan follow-up questions'}</button>}
          {hasQuestions && !p?.answered && <button className="secondary-button" disabled={disabled} onClick={() => setConfirmReplace(true)}>Plan again</button>}
          {hasQuestions && <button className="secondary-button" disabled={disabled} onClick={() => void start('depth')}>{busy === 'depth' ? 'Starting…' : 'Judge evidence depth'}</button>}
          <button className="secondary-button" disabled={disabled} title="One model call per area (about 9), checked against this run's record"
            onClick={() => void start('explain')}>{busy === 'explain' ? 'Starting…' : explained ? 'Write explanations again' : 'Write explanations'}</button>
          {finished && !p?.final_run_id && <button className="primary-action" disabled={disabled} onClick={() => void start('rejudge', { publish: true })}>{busy === 'rejudge' ? 'Starting…' : 'Publish final result'}</button>}
        </div>
      )}>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {!jobs.data?.enabled && <Notice tone="info">Second-layer jobs are switched off on this server (SECOND_LAYER_JOBS_ENABLED). Answers stay unchecked until they are on.</Notice>}
      {confirmReplace && (
        <Notice tone="info">
          Plan the questions again? The current questions are replaced (refused once any question has an answer).{' '}
          <button className="link-button" onClick={() => { setConfirmReplace(false); void start('questions', { replace: true }); }}>Yes, plan again</button>{' '}
          <button className="link-button" onClick={() => setConfirmReplace(false)}>No</button>
        </Notice>
      )}
      {active ? (
        <div className="condition">
          <div><Pill status="pending" label={active.status === 'queued' ? 'Queued' : 'Running'} /> <b>{jobLabel(active)}</b> · started {dateTime(active.started_at || active.created_at)}</div>
          <p className="muted">{active.requests_reserved} model request(s) reserved so far (${active.usd_reserved}).</p>
          {manage && <div className="button-row"><button className="secondary-button" disabled={busy === 'cancel'} onClick={() => void cancel(active)}>Cancel this job</button></div>}
        </div>
      ) : checking && <p className="muted">{p?.checks_waiting} answer(s) wait for their check; it starts by itself once their documents are processed (the server sweeps every 5 minutes).</p>}
      {hasQuestions && !finished && !p?.final_run_id && <p className="muted">“Publish final result” appears once every question is answered or skipped and every answer has been checked.</p>}
      {budget && <p className="muted">Budget: {budget.requests_reserved} of {budget.max_http_calls} requests and ${budget.usd_reserved} of ${budget.max_cost_usd} reserved.</p>}
      {list.length > 0 && (
        <details>
          <summary>Job history ({list.length})</summary>
          <Table columns={['Job', 'Started', 'Status', 'Outcome', 'Reserved']}>
            {list.map((j) => (
              <tr key={j.id}>
                <td><b>{jobLabel(j)}</b><small className="cell-sub">{j.id.slice(0, 8)}</small></td>
                <td>{dateTime(j.created_at)}</td>
                <td><Pill status={isActiveJob(j) ? 'pending' : j.status === 'completed' ? 'completed' : j.status === 'cancelled' ? 'neutral' : 'failed'} label={j.status} /></td>
                <td>{jobOutcome(j)}</td>
                <td>{j.requests_reserved} · ${j.usd_reserved}</td>
              </tr>
            ))}
          </Table>
        </details>
      )}
    </Panel>
  );
}

function QuestionItem({ sprint, runId, item, position, total, onDone }: {
  sprint: Sprint; runId: string; item: Layer2Next; position: number; total: number; onDone: (r: Layer2Response, text: string) => void;
}) {
  const { can } = useAccess();
  const [answer, setAnswer] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const followUp = item.type === 'follow_up';
  const missing = item.question.kind === 'missing';
  const points = item.question.points_at_stake;
  const [own, ...shared] = item.question.condition_ids;

  const send = async (skip: boolean) => {
    setError('');
    if (!skip && !answer.trim() && !files.length) { setError('Type an answer, attach a document, or skip.'); return; }
    setBusy(true);
    try {
      const document_ids = !skip && files.length ? await uploadAll(sprint.id, files) : [];
      const body = { answer: skip ? '' : answer.trim(), document_ids, skip };
      const res = followUp && item.response_id
        ? await answerFollowUp(sprint.id, runId, item.response_id, body)
        : await answerQuestion(sprint.id, runId, item.question.id, body);
      onDone(res.data, skip ? 'Skipped: the item stays as it is.' : res.data.status === 'pending'
        ? 'Saved. Your answer is checked against the documents once they are processed.' : 'Saved and checked.');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={followUp ? 'One follow-up' : `Question ${position} of ${total}`}
      sub={`${item.question.indicator_code}${own ? ` · ${missing ? item.question.condition_ids.join(', ') : own}` : ''}`}
      actions={(
        <>
          {!followUp && !!points && <Pill tone="good" label={`Up to ${pointsLabel(points)}`} />}
          {' '}<Pill status={followUp ? 'pending' : missing ? 'blocked' : 'active'} label={followUp ? 'Follow-up' : missing ? 'Nothing found yet' : 'About credited evidence'} />
        </>
      )}>
      <form onSubmit={(e) => { e.preventDefault(); void send(false); }} className="questionnaire-item">
        <h3>{item.text}</h3>
        {missing && !followUp && <p className="muted">We found nothing for this in the documents submitted. If you have anything, attach it here.</p>}
        {!followUp && !!points && (
          <p className="muted">Answering this with supporting documents can add up to {pointsLabel(points)} to the score.</p>
        )}
        {!missing && shared.length > 0 && <p className="muted">Also answers: {shared.join(', ')} (they need the same fact).</p>}
        <UploadBox files={files} onChange={setFiles} required={missing} />
        <label className="field"><span>Your answer</span>
          <textarea rows={3} maxLength={4000} value={answer} onChange={(e) => setAnswer(e.target.value)}
            placeholder={missing ? 'Optional: say what the document shows' : 'e.g. 300 hours, 42 of 60 faculty, delivered by NPTEL'} />
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="button-row">
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void send(true)}>Skip</button>
          {can('sprint.manage') && <button className="primary-action" disabled={busy}>{busy ? 'Saving…' : 'Submit answer'}</button>}
        </div>
      </form>
    </Panel>
  );
}

// --- additional evidence: documents we may have missed, with what they are for ---------------------------------

function AdditionalEvidence({ sprint, run, runId }: { sprint: Sprint; run: Run; runId: string }) {
  const { can } = useAccess();
  const list = useResource<{ results: AdditionalEvidenceItem[] }>(() => listAdditionalEvidence(sprint.id, runId), `ae:${runId}`);
  const result = run.assessment?.result;
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [requirements, setRequirements] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const toggle = (code: string) => setPicked((p) => (p.includes(code) ? p.filter((x) => x !== code) : [...p, code]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    const reqs = requirements.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
    const all = [...picked, ...reqs];
    if (!files.length) { setMsg({ tone: 'error', text: 'Attach at least one document.' }); return; }
    if (!all.length) { setMsg({ tone: 'error', text: 'Pick at least one readiness area, key indicator or requirement the documents are for.' }); return; }
    setBusy(true);
    try {
      const document_ids = await uploadAll(sprint.id, files);
      const res = await addAdditionalEvidence(sprint.id, runId, { document_ids, note, picked: all });
      setFiles([]); setNote(''); setPicked([]); setRequirements('');
      await list.refetch();
      setMsg({ tone: 'success', text: res.data.unknown_picks.length ? `Saved. Not recognised: ${res.data.unknown_picks.join(', ')}.` : 'Saved. It is checked once the documents are processed.' });
    } catch (err) {
      setMsg({ tone: 'error', text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {can('sprint.manage') && (
        <Panel title="Add evidence we may have missed" sub="Optional. Documents, a note, and what they are for (at least one pick)">
          <form onSubmit={submit} className="questionnaire-item">
            <UploadBox files={files} onChange={setFiles} required />
            <label className="field"><span>Note</span>
              <textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What the documents show and where to look" />
            </label>
            <fieldset>
              <legend className="muted">Readiness areas and key indicators *</legend>
              <div className="indicator-list">
                {(result?.pillars || []).map((area) => (
                  <details key={area.code} className="indicator">
                    <summary>
                      <label className="field inline" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={picked.includes(area.code)} onChange={() => toggle(area.code)} /> <b>{area.code}</b> (whole area)
                      </label>
                    </summary>
                    {(result?.indicators || []).filter((i) => i.pillar === area.code).map((i) => (
                      <label key={i.code} className="field inline">
                        <input type="checkbox" checked={picked.includes(i.code)} onChange={() => toggle(i.code)} /> {i.code} · {i.name}
                      </label>
                    ))}
                  </details>
                ))}
              </div>
            </fieldset>
            <label className="field"><span>Specific requirements (optional, e.g. AIQIF-C4.1-a)</span>
              <input value={requirements} onChange={(e) => setRequirements(e.target.value)} placeholder="Comma-separated requirement ids" />
            </label>
            <div className="button-row"><button className="primary-action" disabled={busy}>{busy ? 'Uploading…' : 'Submit evidence'}</button></div>
          </form>
        </Panel>
      )}
      <Panel title="Submitted so far">
        {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : !list.data?.results.length ? <p className="muted">Nothing submitted yet.</p> : list.data.results.map((a) => (
          <article key={a.id} className="condition">
            <div><Pill status={a.status === 'pending' ? 'pending' : 'active'} label={a.status === 'pending' ? 'Waiting for a check' : 'Checked'} /> {a.document_ids.length} document(s) · {dateTime(a.created_at)}</div>
            {a.note && <p>{tidyText(a.note)}</p>}
            <p className="muted">For: {a.picked.join(', ')}{a.routed_indicators.length ? ` · routed to ${a.routed_indicators.join(', ')}` : ''}{a.over_cap.length ? ` · over the 8-indicator cap: ${a.over_cap.join(', ')}` : ''}</p>
            {a.status === 'checked' && <p className="muted">{a.passages_found} passage(s) found</p>}
          </article>
        ))}
      </Panel>
    </>
  );
}

/** "0.42 points", rounded to two decimals the way the backend reports points_at_stake. */
function pointsLabel(n: number) {
  const v = Number(n.toFixed(2));
  return `${v} point${v === 1 ? '' : 's'}`;
}
