import { useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat, Table, Tabs } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import {
  addAdditionalEvidence, answerFollowUp, answerQuestion, cancelSecondLayerJob, getNextQuestion, getQuestions, getResponse,
  listAdditionalEvidence, listSecondLayerJobs, markToCheck, startSecondLayerJob,
  type AdditionalEvidenceItem, type Layer2Next, type Layer2Question, type Layer2Progress, type Layer2Questions, type Layer2Response, type SecondLayerJob,
  type SecondLayerJobList, type SecondLayerOperation,
} from '../services/capability';
import { startExtraction, uploadDocument } from '../services/documents';
import { decideReviewCase, getReviewBatch, startReviewBatch } from '../services/facts';
import type { Sprint } from '../types/api';
import type { Run, ScreenPractice } from '../types/capability';
import type { ReviewBatch, ReviewCase } from '../types/workflow';
import { DEMO_MODE } from '../config/env';
import { areaTitle } from '../utils/areaTitles';
import { FINAL_SCORE, newKey, pillarName } from '../utils/capability';
import { errorMessage } from '../utils/errors';
import { dateTime, humanize, tidyText, valueText } from '../utils/format';
import { answerState, littleAfter } from '../utils/answers';

/**
 * The questionnaire of the new flow (Siddharth / Harsha, 12 Nov 2026), one item at a time, each with an answer box,
 * a document upload and Skip:
 *   line 1, before the assessment: the review items on the submitted evidence (guided review batch);
 *   line 2, after the provisional score: follow-up questions about the evidence and "nothing found" questions
 *           (second assessment layer, at most one follow-up per answer);
 *   additional evidence: documents the institution thinks were missed, for at least one area / indicator / requirement.
 */
const ALL_TABS = [
  { key: 'line1', label: '1 · Evidence review' },
  { key: 'line2', label: '2 · Follow-up questions' },
  { key: 'extra', label: 'Additional evidence' },
] as const;
type Tab = (typeof ALL_TABS)[number]['key'];
// Demo mode: only what follows the Stage 1 result, in plain words (the evidence review comes before the assessment).
const TABS: readonly { key: Tab; label: string }[] = DEMO_MODE
  ? [{ key: 'line1', label: 'Before the assessment: check the facts' }, { key: 'line2', label: 'Follow-up questions' },
    { key: 'extra', label: 'Send a document we missed' }]
  : ALL_TABS;

/**
 * A notice for the questionnaire's first screen. The follow-up notice agreed on 23 Nov (answers count only with a
 * document; a document can move the score up or down) is served with the questions (GET .../questions `notice`) and
 * shown on the follow-up tab, so this stays empty.
 */
const QUESTIONNAIRE_NOTICE = '';

export function Questionnaire() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { staff } = useAccess();
  const [tab, setTab] = useState<Tab>(DEMO_MODE ? 'line2' : 'line1');

  const cap = useCapability(sprint.id);
  return (
    <>
      <PageHeading page="questionnaire" />
      {QUESTIONNAIRE_NOTICE && <Notice tone="info">{QUESTIONNAIRE_NOTICE}</Notice>}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Questionnaire" />
      {tab === 'line1' && <LineOne sprint={sprint} />}
      {tab !== 'line1' && (cap.loading ? <Loading /> : cap.error ? <ErrorState error={cap.error} /> : !cap.run.data ? (
        staff ? (
          <Empty title="No Stage 1 result yet" action={<PageLink to="assessment" className="primary-action">Go to the assessment</PageLink>}>
            The follow-up questions and additional evidence belong to a completed assessment run. Finish the evidence review, then run the assessment.
          </Empty>
        ) : (
          <Empty title="Your follow-up questions come with your Stage 1 result">
            Once your documents have been read and your Stage 1 result is out, the questions appear here.
          </Empty>
        )
      ) : tab === 'line2'
        ? <LineTwo sprint={sprint} run={cap.run.data} runId={cap.provisionalId} onFinal={() => void cap.runs.refetch()} />
        : <AdditionalEvidence sprint={sprint} run={cap.run.data} runId={cap.provisionalId} closed={cap.stage === 'final'} />)}
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
          Every review item has an answer. The assessment gives the Stage 1 result; the follow-up questions come after it.
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
  const { staff } = useAccess();
  const next = useResource<Layer2Questions>(() => getNextQuestion(sprint.id, runId), `l2:${runId}`);
  // A question opened by name (?question=…), from a practice not found on the Results page or from Your answers.
  const [params, setParams] = useSearchParams();
  const asked = params.get('question') || '';
  // Every question in order with its latest answer: the list on the left (merged design, 27 Nov).
  const listed = useResource<Layer2Questions>(() => getQuestions(sprint.id, runId), `l2-list:${runId}`);
  const clearAsked = () => { const p = new URLSearchParams(params); p.delete('question'); setParams(p, { replace: true }); };
  const openQuestion = (id: string) => { const p = new URLSearchParams(params); p.set('question', id); setParams(p); };
  const refresh = () => { void next.refetch(); void listed.refetch(); };
  // What Stage 1 found for each practice, from the result view the Results page shows (merged design, 27 Nov).
  const practices = useMemo(() => {
    const m = new Map<string, ScreenPractice>();
    for (const c of run.next_steps?.presentation?.cards || []) for (const t of c.topics) for (const p of t.practices) m.set(p.id, p);
    return m;
  }, [run]);
  // Each topic's area and plain name, for the question's heading and the list.
  const topics = useMemo(() => {
    const m = new Map<string, { area: string; topic: string }>();
    for (const c of run.next_steps?.presentation?.cards || []) for (const t of c.topics) m.set(t.code, { area: c.name, topic: t.name });
    return m;
  }, [run]);
  const [answered, setAnswered] = useState<Layer2Response[]>([]);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const p = next.data?.progress;
  const notice = next.data?.notice;
  const pending = answered.filter((r) => r.status === 'pending');

  // Responses come back "pending" until the check has run; refresh them while any is pending.
  usePolling(() => {
    void Promise.all(pending.map((r) => getResponse(sprint.id, runId, r.id).then((x) => x.data).catch(() => r)))
      .then((fresh) => {
        setAnswered((all) => all.map((r) => fresh.find((f) => f.id === r.id) || r));
        // A check that asks a follow-up puts it back in the queue as next.type = "follow_up".
        if (fresh.some((f) => f.status === 'checked')) refresh();
      });
  }, pending.length > 0, 8000);
  // The questions are planned by themselves once the Stage 1 result is published: wait for them.
  usePolling(() => void next.refetch(), !!next.data && !next.data.progress?.questions && !next.data.progress?.final_run_id, 10000);

  if (next.loading && !next.data) return <Loading />;
  if (next.error) return <ErrorState error={next.error} onRetry={() => void next.refetch()} />;
  const all = (listed.data?.questions || []).filter((q) => q.status !== 'linked');
  const closed = !!p?.final_run_id || !!p?.closed;
  const followUp = !asked && !closed && next.data?.next?.type === 'follow_up' ? next.data.next : null;
  const selected = all.find((q) => q.id === asked)
    || (!closed && next.data?.next?.type === 'question' ? all.find((q) => q.id === next.data!.next!.question.id) : undefined)
    || (closed ? all[0] : undefined);
  const at = selected ? all.indexOf(selected) : -1;
  const done = (r: Layer2Response | null, text: string) => {
    if (r) setAnswered((a) => [r, ...a]);
    setMsg({ tone: 'success', text });
    clearAsked();
    refresh();
  };
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {closed && p?.final_run_id && (
        staff
          ? <Notice tone="success">The follow-up stage is closed and the {FINAL_SCORE} has been published (run {p.final_run_id.slice(0, 8)}). Reports, recommendations and plan comparison now use it.</Notice>
          : <Notice tone="success">The follow-up questions are closed and your final result is out. It is on your Overview, and your answers stay under Your answers.</Notice>
      )}
      {notice && !closed && (
        <details className="fu-rules">
          <summary><strong>{notice.title}</strong> {notice.rules[0]}</summary>
          <p>{notice.intro}</p>
          <ul>{notice.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </details>
      )}
      {staff && <SecondLayerJobs sprint={sprint} runId={runId} progress={p} onChange={refresh} onFinal={onFinal} />}
      {!DEMO_MODE && staff && <div className="stat-grid">
        <Stat label="Questions" value={p?.questions ?? 0} note={`${p?.linked ? `${p.linked} more answered through linked questions · ` : ''}Stage 1 result, run ${runId.slice(0, 8)}${run.id === runId ? ` · ${dateTime(run.created_at)}` : ''}`} />
        <Stat label="Answered or skipped" value={p?.answered ?? 0} note={`${p?.open ?? 0} open`} />
        <Stat label="Checks waiting" value={p?.checks_waiting ?? 0} note="Answers are checked against the documents" />
        <Stat label="Follow-ups open" value={p?.follow_ups_open ?? 0} note="At most one per answer" />
      </div>}
      {!p?.questions && !closed ? (
        staff
          ? <Empty title="No follow-up questions yet">Questions for this run have not been planned yet. They are planned by themselves once the Stage 1 result is published; “Plan follow-up questions” above starts it by hand.</Empty>
          : <Empty title="Your follow-up questions are being prepared">They appear here once they are ready. This page updates by itself.</Empty>
      ) : (
        <div className="fu-grid">
          <QuestionList questions={all} current={followUp ? '' : selected?.id || ''} topics={topics} onOpen={openQuestion}
            answered={p?.answered ?? 0} total={p?.questions ?? all.length} closed={closed} />
          <div className="fu-main">
            {followUp ? (
              <QuestionItem key={`fu:${followUp.response_id}`} sprint={sprint} runId={runId} item={followUp} found={practices} topics={topics}
                position={0} total={all.length} onDone={done} />
            ) : selected && !closed && !selected.response ? (
              <QuestionItem key={`q:${selected.id}`} sprint={sprint} runId={runId} found={practices} topics={topics}
                item={{ type: 'question', text: selected.text, question: selected, response_id: null }}
                position={at + 1} total={all.length} onDone={done}
                onPrevious={at > 0 ? () => openQuestion(all[at - 1].id) : undefined} />
            ) : selected ? (
              <AnsweredQuestion q={selected} position={at + 1} total={all.length} found={practices} topics={topics} closed={closed}
                onPrevious={at > 0 ? () => openQuestion(all[at - 1].id) : undefined}
                onNext={!closed && next.data?.next ? clearAsked : at < all.length - 1 ? () => openQuestion(all[at + 1].id) : undefined} />
            ) : (
              <Empty title="All questions answered" action={<PageLink to="areas" className="primary-action">See your nine areas</PageLink>}>
                {p?.checks_waiting ? `${p.checks_waiting} answer(s) are still being checked against the documents.` : 'Every question has an answer.'}
              </Empty>
            )}
            {!staff && <SecondLayerJobs sprint={sprint} runId={runId} progress={p} onChange={refresh} onFinal={onFinal} />}
          </div>
        </div>
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
  next_steps: 'Writing next steps',
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

/** A next-steps job's result: { calls, written, fallbacks }. */
function stepsOutcome(r: Record<string, unknown> | null): string {
  if (!r) return 'Done';
  const num = (k: string) => (typeof r[k] === 'number' ? (r[k] as number) : 0);
  return [`${num('written')} steps written in ${num('calls')} calls`,
    num('fallbacks') ? `${num('fallbacks')} on the plain checklist` : ''].filter(Boolean).join(' · ');
}

function jobOutcome(j: SecondLayerJob): string {
  if (j.status === 'completed' && j.operation === 'explain') return explainOutcome(j.result);
  if (j.status === 'completed' && j.operation === 'next_steps') return stepsOutcome(j.result);
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
  const { can, staff } = useAccess();
  const jobs = useResource<SecondLayerJobList>(() => listSecondLayerJobs(sprint.id, runId), `slj:${runId}`);
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
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
          // The college is not told about the background jobs (they run by themselves), only that its result is in.
          if (!staff) {
            if (j.operation === 'rejudge') setMsg(j.status === 'completed'
              ? { tone: 'success', text: `Your ${FINAL_SCORE} is being prepared. It appears here once its report is written.` }
              : { tone: 'error', text: 'Finishing did not go through. Please try again, or tell your InGage contact.' });
            continue;
          }
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
  if (!staff) return <CollegeFinish progress={p} active={active} enabled={!!jobs.data?.enabled} busy={busy} msg={msg}
    onClear={() => setMsg(null)} onFinish={() => void start('rejudge', { close: true })} manage={manage} />;
  const hasQuestions = !!p?.questions;
  const closed = !!p?.final_run_id;
  // The college can stop whenever it likes (the questionnaire notice says so): publishing closes the follow-up stage
  // once no answer is still waiting for its check. Unanswered questions earn nothing.
  const canPublish = !!p && !closed && !p.checks_waiting && hasQuestions;
  const budget = jobs.data?.budget;
  const disabled = !jobs.data?.enabled || !!active || !!busy;
  // Final results are explained automatically; the provisional run's explanations are written on request.
  const explained = list.some((j) => j.operation === 'explain' && !j.options?.final && j.status === 'completed');

  return (
    <Panel title={DEMO_MODE ? 'Your final result' : 'Follow-up questions and final result'} sub={DEMO_MODE ? `Publishing gives your ${FINAL_SCORE} and readiness level, and closes the follow-up questions.` : "Background jobs on the Stage 1 result; each uses model credits from this assessment's budget"}
      actions={manage && (
        <div className="row-actions">
          {!closed && !hasQuestions && <button className="primary-action" disabled={disabled} onClick={() => void start('questions')}>{busy === 'questions' ? 'Starting…' : 'Plan follow-up questions'}</button>}
          {!DEMO_MODE && !closed && hasQuestions && !p?.answered && <button className="secondary-button" disabled={disabled} onClick={() => setConfirmReplace(true)}>Plan again</button>}
          {!closed && hasQuestions && <button className="secondary-button" disabled={disabled} title="Needed before closing whenever an answer about credited evidence has been checked"
            onClick={() => void start('depth')}>{busy === 'depth' ? 'Starting…' : DEMO_MODE ? 'Check how far the evidence goes' : 'Judge evidence depth'}</button>}
          {!(DEMO_MODE && (closed || explained)) && <button className="secondary-button" disabled={disabled} title="One model call per area (about 9), checked against this run's record"
            onClick={() => void start('explain')}>{busy === 'explain' ? 'Starting…' : DEMO_MODE ? 'Explain the Stage 1 result' : explained ? 'Write explanations again' : 'Write explanations'}</button>}
          {!DEMO_MODE && <button className="secondary-button" disabled={disabled} title="One model call per first step (at most six), checked against this run's record; written once, never on a reload"
            onClick={() => void start('next_steps')}>{busy === 'next_steps' ? 'Starting…' : 'Write next steps'}</button>}
          {canPublish && <button className="primary-action" disabled={disabled} title="Closes the follow-up stage: after this no answer or document can change the final AI-READY Score"
            onClick={() => setConfirmPublish(true)}>{busy === 'rejudge' ? 'Starting…' : 'Finish and publish the final result'}</button>}
        </div>
      )}>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {!jobs.data?.enabled && <Notice tone="info">{DEMO_MODE ? 'Answer checking is switched off on this server for now, so answers stay unchecked until it is on.' : 'Second-layer jobs are switched off on this server (SECOND_LAYER_JOBS_ENABLED). Answers stay unchecked until they are on.'}</Notice>}
      {confirmReplace && (
        <Notice tone="info">
          Plan the questions again? The current questions are replaced (refused once any question has an answer).{' '}
          <button className="link-button" onClick={() => { setConfirmReplace(false); void start('questions', { replace: true }); }}>Yes, plan again</button>{' '}
          <button className="link-button" onClick={() => setConfirmReplace(false)}>No</button>
        </Notice>
      )}
      {confirmPublish && (
        <Notice tone="info">
          Publish the {FINAL_SCORE}? This closes the follow-up stage: no more answers or documents can be added, and
          unanswered questions earn nothing.
          {!!p?.to_check && <strong> {p.to_check} question{p.to_check === 1 ? ' is' : 's are'} still marked “I need to check”.</strong>}{' '}
          <button className="link-button" onClick={() => { setConfirmPublish(false); void start('rejudge', { close: true }); }}>Yes, publish</button>{' '}
          <button className="link-button" onClick={() => setConfirmPublish(false)}>No</button>
        </Notice>
      )}
      {active ? (
        <div className="condition">
          <div><Pill status="pending" label={active.status === 'queued' ? 'Queued' : 'Running'} /> <b>{jobLabel(active)}</b> · started {dateTime(active.started_at || active.created_at)}</div>
          <p className="muted">{active.requests_reserved} model request(s) reserved so far (${active.usd_reserved}).</p>
          {manage && <div className="button-row"><button className="secondary-button" disabled={busy === 'cancel'} onClick={() => void cancel(active)}>Cancel this job</button></div>}
        </div>
      ) : checking && (
        <div>
          <p className="muted">{p?.checks_waiting} answer(s) or evidence item(s) wait for their check. It starts once their documents are processed; if it hasn't, check them now.</p>
          {manage && <div className="button-row"><button className="secondary-button" disabled={disabled} onClick={() => void start('checks')}>{busy === 'checks' ? 'Starting…' : 'Check answers now'}</button></div>}
        </div>
      )}
      {!closed && !!p?.checks_waiting && <p className="muted">“Finish and publish the final result” appears once every answer has been checked.</p>}
      {!DEMO_MODE && budget && <p className="muted">Budget: {budget.requests_reserved} of {budget.max_http_calls} requests and ${Number(budget.usd_reserved).toFixed(2)} of ${Number(budget.max_cost_usd).toFixed(2)} reserved.</p>}
      {!DEMO_MODE && list.length > 0 && (
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

/**
 * What a college sees of the follow-up stage (26 Nov): no job controls, budgets or model wording. Its questions are
 * planned and its answers checked and judged by themselves (publication.keep_going); the college's one decision is
 * when to finish, which closes the stage and produces the final result.
 */
function CollegeFinish({ progress: p, active, enabled, busy, msg, onClear, onFinish, manage }: {
  progress?: Layer2Progress; active: SecondLayerJob | null; enabled: boolean; busy: string;
  msg: { tone: 'success' | 'error' | 'info'; text: string } | null; onClear: () => void; onFinish: () => void; manage: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  if (!p?.questions || p.final_run_id) return msg ? <Notice tone={msg.tone} onClose={onClear}>{msg.text}</Notice> : null;
  const working = !!active || !!p.checks_waiting;
  const finishing = active?.operation === 'rejudge' || busy === 'rejudge';
  return (
    <Panel title="Finish the follow-up questions" sub={`When you have answered what you can, finish to get your ${FINAL_SCORE} and readiness level.`}
      actions={manage && !finishing && (
        <button className="primary-action" disabled={working || !!busy || !enabled} onClick={() => setConfirm(true)}
          title={working ? 'Available once your latest answers have been checked' : undefined}>Finish and get the final result</button>
      )}>
      {msg && <Notice tone={msg.tone} onClose={onClear}>{msg.text}</Notice>}
      {confirm && (
        <Notice tone="info">
          Finish now? After this no more answers or documents can be added, and unanswered questions earn nothing.
          {!!p.to_check && <strong> {p.to_check} question{p.to_check === 1 ? ' is' : 's are'} still marked “I need to check”.</strong>}{' '}
          <button className="link-button" onClick={() => { setConfirm(false); onFinish(); }}>Yes, finish</button>{' '}
          <button className="link-button" onClick={() => setConfirm(false)}>Not yet</button>
        </Notice>
      )}
      <p className="muted">
        {finishing ? `Your ${FINAL_SCORE} is being prepared. This page updates when it is ready.`
          : working ? 'Your latest answers are being checked against the documents you attached. You can keep answering meanwhile.'
          : 'You can stop whenever you like. Answers backed by a document can raise your score; unanswered questions earn nothing back.'}
      </p>
    </Panel>
  );
}

/** "What we found at Stage 1" beside a question (merged design, 27 Nov): its practices looked up in the result
 * view by the question's condition_ids, which are the same practice ids. */
function StageOneFound({ ids, found }: { ids: string[]; found: Map<string, ScreenPractice> }) {
  const ps = ids.map((id) => found.get(id)).filter((p): p is ScreenPractice => !!p);
  if (!ps.length) return null;
  const missing = ps.every((p) => p.status === 'missing');
  return (
    <div className="ws-found">
      <strong>What we found at Stage 1</strong>
      {missing ? (
        <p>{ps.length === 1 ? 'Nothing in the documents you sent shows this yet.' : `Nothing in the documents you sent shows ${ps.length === 2 ? 'either of these' : 'any of these'} yet.`}</p>
      ) : ps.map((p) => (
        <p key={p.id}>
          {ps.length > 1 && <b>{p.label_short}: </b>}
          {p.status === 'missing' ? 'Not found in the documents you sent.' : [p.found, p.why].filter(Boolean).join(' ') || (p.status === 'shown' ? 'In place.' : 'Partly in place.')}
          {!!p.evidence_in?.length && <small> {p.evidence_in.join('; ')}</small>}
        </p>
      ))}
    </div>
  );
}

type Topics = Map<string, { area: string; topic: string }>;

/** The first sentence of a question, for the list: a missing-evidence question names its topic instead. */
function listLabel(q: Layer2Question, topics: Topics) {
  const t = topics.get(q.indicator_code);
  if (q.kind === 'missing') {
    const n = q.condition_ids.length;
    const name = !t ? 'this topic' : /^[A-Z]{2}/.test(t.topic) ? t.topic : t.topic[0].toLowerCase() + t.topic.slice(1);
    return `What your documents did not show about ${name} (${n} practice${n === 1 ? '' : 's'})`;
  }
  const first = q.text.split('\n')[0].split(/(?<=[.?!])\s/)[0];
  return first.length > 120 ? `${first.slice(0, 117).trimEnd()}…` : first;
}

const answerTag = (q: Layer2Question & { response: Layer2Response | null }, closed = false) =>
  q.response ? (q.response.status === 'pending' ? ['Being checked', 'blue'] : q.response.choice === 'not_yet' ? ['Not yet', 'gray'] : ['Answered', ''])
    : closed ? ['Not answered', 'gray'] : q.to_check ? ['To check', 'amber'] : ['Open', 'gray'];

/** The list beside the question (merged design, 27 Nov): most important first, with a marker where answers stop
 * adding much. Choosing a question opens it. */
function QuestionList({ questions, current, topics, onOpen, answered, total, closed }: {
  questions: (Layer2Question & { response: Layer2Response | null })[]; current: string; topics: Topics;
  onOpen: (id: string) => void; answered: number; total: number; closed: boolean;
}) {
  const little = closed ? -1 : littleAfter(questions);
  return (
    <aside className="fu-list" aria-label="All follow-up questions">
      <div className="fu-list-head"><h2>Most important first</h2><span className="tag">{answered} of {total} answered</span></div>
      <p className="muted">Questions that can confirm the most come first.</p>
      <ol>
        {questions.map((q, i) => {
          const [label, tone] = answerTag(q, closed);
          const t = topics.get(q.indicator_code);
          return (
            <li key={q.id}>
              {i === little && (
                <p className="fu-little">From question {i + 1} on, each answer adds little. Answer them if you have the documents to hand.</p>
              )}
              <button type="button" className={q.id === current ? 'on' : ''} aria-current={q.id === current ? 'true' : undefined} onClick={() => onOpen(q.id)}>
                <span className="q">{listLabel(q, topics)}</span>
                <span className="m"><small>{t?.area || pillarName(q.indicator_code.split('.')[0])}</small><span className={`tag ${tone}`}>{label}</span></span>
              </button>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

/** A question's heading: the area and topic, and where it sits in the list. */
function QuestionHead({ q, position, total, topics, extra }: { q: Layer2Question; position: number; total: number; topics: Topics; extra?: ReactNode }) {
  const t = topics.get(q.indicator_code);
  return (
    <div className="fu-head">
      <span>{t ? `${t.area}: ${t.topic}` : pillarName(q.indicator_code.split('.')[0])}</span>
      <span className="ws-row">{extra}{position > 0 && <span>Question {position} of {total}</span>}</span>
    </div>
  );
}

/** A question's text: the first line as the question, the numbered practices of a missing-evidence question below. */
function QuestionText({ text }: { text: string }) {
  const [first, ...rest] = text.split('\n');
  return (
    <>
      <h2 className="fu-q">{first}</h2>
      {rest.length > 0 && <div className="fu-q-rest">{rest.map((line, i) => <p key={i}>{line}</p>)}</div>}
    </>
  );
}

/** An answered question, read only: after finishing, every question is shown this way (merged design, 27 Nov). */
function AnsweredQuestion({ q, position, total, found, topics, closed, onPrevious, onNext }: {
  q: Layer2Question & { response: Layer2Response | null }; position: number; total: number; found: Map<string, ScreenPractice>;
  topics: Topics; closed: boolean; onPrevious?: () => void; onNext?: () => void;
}) {
  const r = q.response;
  return (
    <section className="question-card fu-card">
      <QuestionHead q={q} position={position} total={total} topics={topics} />
      <QuestionText text={q.text} />
      <StageOneFound ids={q.condition_ids} found={found} />
      <div className="fu-answer">
        <strong>Your answer</strong>
        {r ? (
          <>
            <p><span className={`tag ${answerTag(q)[1]}`}>{answerState(r).label}</span></p>
            {r.answer && <p>{tidyText(r.answer)}</p>}
            <p className="muted">{r.document_ids.length ? `${r.document_ids.length} document${r.document_ids.length === 1 ? '' : 's'} attached` : 'No document attached'} · {dateTime(r.created_at)}</p>
          </>
        ) : <p className="muted">{closed ? 'Not answered before the questions closed.' : 'Not answered yet.'}</p>}
      </div>
      <div className="fu-nav">
        {onPrevious ? <button type="button" className="text-btn" onClick={onPrevious}>Previous question</button> : <span />}
        {onNext && <button type="button" className="text-btn" onClick={onNext}>{closed ? 'Next question' : 'Go to the next open question'}</button>}
      </div>
    </section>
  );
}

function QuestionItem({ sprint, runId, item, position, total, onDone, found, topics, onPrevious }: {
  sprint: Sprint; runId: string; item: Layer2Next; position: number; total: number; onDone: (r: Layer2Response | null, text: string) => void;
  found?: Map<string, ScreenPractice>; topics: Topics; onPrevious?: () => void;
}) {
  const { can, staff } = useAccess();
  const [answer, setAnswer] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [noDocOk, setNoDocOk] = useState(false);
  const followUp = item.type === 'follow_up';
  const points = item.question.points_at_stake;
  const manage = can('sprint.manage');

  /** save: an answer (with its documents), sent without an answer option, since only the documents decide credit;
   *  check: "I need to check"; none: "We do not have this" (recorded as not_yet). */
  const send = async (how: 'save' | 'check' | 'none') => {
    setError('');
    if (how === 'save' && !files.length && !noDocOk) {
      if (!answer.trim()) { setError('Attach the document that shows this, or say where to find it.'); return; }
      setNoDocOk(true);
      setError('An answer counts only when a document supports it. Attach one, or press Save again to send the answer without a document: it is recorded, but earns nothing.');
      return;
    }
    setBusy(how);
    try {
      if (how === 'check') {
        await markToCheck(sprint.id, runId, item.question.id, true);
        onDone(null, 'Saved for later: this question waits at the end of the list.');
        return;
      }
      const document_ids = how === 'save' && files.length ? await uploadAll(sprint.id, files) : [];
      const body = how === 'none'
        ? { answer: answer.trim(), document_ids: [], choice: 'not_yet' as const }
        : { answer: answer.trim(), document_ids };
      const res = followUp && item.response_id
        ? await answerFollowUp(sprint.id, runId, item.response_id, body)
        : await answerQuestion(sprint.id, runId, item.question.id, body);
      onDone(res.data, how === 'none' ? 'Recorded as not yet in place. It does not lower your score.'
        : res.data.status === 'pending' ? 'Saved. Your answer is checked against your documents once they have been read.' : 'Saved.');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy('');
    }
  };

  return (
    <section className="question-card fu-card">
      <QuestionHead q={item.question} position={followUp ? 0 : position} total={total} topics={topics}
        extra={<>
          {followUp && <span className="tag blue">One more thing about your answer</span>}
          {item.question.to_check && <span className="tag amber">Marked to check</span>}
          {/* Points to two decimals are for staff; a college's screens carry no decimals (merged design, 27 Nov). */}
          {staff && !followUp && !!points && <span className="tag">Up to {pointsLabel(points)}</span>}
        </>} />
      <QuestionText text={item.text} />
      {!followUp && found && <StageOneFound ids={item.question.condition_ids} found={found} />}
      <form onSubmit={(e) => { e.preventDefault(); void send('save'); }}>
        <h3 className="fu-label">The document that shows this</h3>
        <UploadBox files={files} onChange={(f) => { setFiles(f); setNoDocOk(false); }} required={false} />
        <label className="field fu-field">
          <span><strong>Your answer</strong> <span className="muted">(tells us where to look in the document)</span></span>
          <textarea rows={3} maxLength={4000} value={answer} onChange={(e) => { setAnswer(e.target.value); setNoDocOk(false); }}
            placeholder="For example: “The IT Policy, section 6, sets out the weekly backup and the restore test.”" />
        </label>
        {error && <Notice tone={noDocOk ? 'warn' : 'error'}>{error}</Notice>}
        {manage && (
          <div className="fu-actions">
            <button className="btn primary" disabled={!!busy}>{busy === 'save' ? 'Saving…' : 'Save and go to the next question'}</button>
            {!followUp && <button type="button" className="btn" disabled={!!busy} onClick={() => void send('check')}
              title="Saved for later: the question waits at the end of the list">I need to check</button>}
            {!followUp && <button type="button" className="btn" disabled={!!busy} onClick={() => void send('none')}
              title="Recorded for your improvement plan. It does not lower your score.">We do not have this</button>}
          </div>
        )}
        {onPrevious && <div className="fu-nav"><span /><button type="button" className="text-btn" onClick={onPrevious}>Previous question</button></div>}
      </form>
    </section>
  );
}

// --- additional evidence: documents we may have missed, with what they are for ---------------------------------

function AdditionalEvidence({ sprint, run, runId, closed }: { sprint: Sprint; run: Run; runId: string; closed: boolean }) {
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
      {closed && (
        <Notice tone="info">The follow-up stage is closed and the {FINAL_SCORE} has been published, so no more documents can be added to this assessment. New evidence needs a new assessment.</Notice>
      )}
      {can('sprint.manage') && !closed && (
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
                        <input type="checkbox" checked={picked.includes(area.code)} onChange={() => toggle(area.code)} /> <b>{DEMO_MODE ? pillarName(area.code) : area.code}</b> (whole area)
                      </label>
                    </summary>
                    {(result?.indicators || []).filter((i) => i.pillar === area.code).map((i) => (
                      <label key={i.code} className="field inline">
                        <input type="checkbox" checked={picked.includes(i.code)} onChange={() => toggle(i.code)} /> {DEMO_MODE ? areaTitle(i.code, i.name) : `${i.code} · ${i.name}`}
                      </label>
                    ))}
                  </details>
                ))}
              </div>
            </fieldset>
{!DEMO_MODE && (            <label className="field"><span>Specific requirements (optional, e.g. AIQIF-C4.1-a)</span>
              <input value={requirements} onChange={(e) => setRequirements(e.target.value)} placeholder="Comma-separated requirement ids" />
            </label>)}
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
