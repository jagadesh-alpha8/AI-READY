import { useMemo, useRef, useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat, Tabs } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import {
  addAdditionalEvidence, answerFollowUp, answerQuestion, getNextQuestion, getResponse, listAdditionalEvidence,
  type AdditionalEvidenceItem, type Layer2Next, type Layer2Progress, type Layer2Response,
} from '../services/capability';
import { startExtraction, uploadDocument } from '../services/documents';
import { decideReviewCase, getReviewBatch, startReviewBatch } from '../services/facts';
import type { Sprint } from '../types/api';
import type { Run } from '../types/capability';
import type { ReviewBatch, ReviewCase } from '../types/workflow';
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

export function Questionnaire() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const [tab, setTab] = useState<Tab>('line1');
  const cap = useCapability(sprint.id);
  return (
    <>
      <PageHeading page="questionnaire" />
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Questionnaire" />
      {tab === 'line1' && <LineOne sprint={sprint} />}
      {tab !== 'line1' && (cap.loading ? <Loading /> : cap.error ? <ErrorState error={cap.error} /> : !cap.run.data ? (
        <Empty title="No provisional score yet" action={<PageLink to="assessment" className="primary-action">Go to the assessment</PageLink>}>
          The follow-up questions and additional evidence belong to a completed assessment run. Finish the evidence review, then run the assessment.
        </Empty>
      ) : tab === 'line2' ? <LineTwo sprint={sprint} run={cap.run.data} /> : <AdditionalEvidence sprint={sprint} run={cap.run.data} />)}
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

function LineTwo({ sprint, run }: { sprint: Sprint; run: Run }) {
  const next = useResource<{ next: Layer2Next | null; progress: Layer2Progress }>(() => getNextQuestion(sprint.id, run.id), `l2:${run.id}`);
  const [answered, setAnswered] = useState<Layer2Response[]>([]);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const p = next.data?.progress;
  const pending = answered.filter((r) => r.status === 'pending');

  // Responses come back "pending" until the check has run; refresh them while any is pending.
  usePolling(() => {
    void Promise.all(pending.map((r) => getResponse(sprint.id, run.id, r.id).then((x) => x.data).catch(() => r)))
      .then((fresh) => {
        setAnswered((all) => all.map((r) => fresh.find((f) => f.id === r.id) || r));
        if (fresh.some((f) => f.status === 'checked' && f.follow_up)) void next.refetch();
      });
  }, pending.length > 0, 8000);

  if (next.loading && !next.data) return <Loading />;
  if (next.error) return <ErrorState error={next.error} onRetry={() => void next.refetch()} />;
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="stat-grid">
        <Stat label="Questions" value={p?.questions ?? 0} note={`Run ${run.id.slice(0, 8)} · ${dateTime(run.created_at)}`} />
        <Stat label="Answered or skipped" value={p?.answered ?? 0} note={`${p?.open ?? 0} open`} />
        <Stat label="Checks waiting" value={p?.checks_waiting ?? 0} note="Answers are checked against the documents" />
        <Stat label="Follow-ups open" value={p?.follow_ups_open ?? 0} note="At most one per answer" />
      </div>
      {p && p.questions > 0 && <Panel><ProgressLine done={p.answered} total={p.questions} label="Questions answered" /></Panel>}
      {!p?.questions ? (
        <Empty title="No follow-up questions yet">Questions for this run have not been generated yet. They are created after the provisional score.</Empty>
      ) : !next.data?.next ? (
        <Empty title="All questions answered" action={<PageLink to="cri" className="primary-action">See the report</PageLink>}>
          {p.checks_waiting ? `${p.checks_waiting} answer(s) are still being checked against the documents.` : 'Every question has an answer or was skipped.'}
        </Empty>
      ) : (
        <QuestionItem key={`${next.data.next.type}:${next.data.next.response_id || next.data.next.question.id}`} sprint={sprint} run={run} item={next.data.next}
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
              {r.follow_up && <p><b>Follow-up asked:</b> {r.follow_up}</p>}
            </article>
          ))}
        </Panel>
      )}
    </>
  );
}

function QuestionItem({ sprint, run, item, position, total, onDone }: {
  sprint: Sprint; run: Run; item: Layer2Next; position: number; total: number; onDone: (r: Layer2Response, text: string) => void;
}) {
  const { can } = useAccess();
  const [answer, setAnswer] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const followUp = item.type === 'follow_up';
  const missing = item.question.kind === 'missing';

  const send = async (skip: boolean) => {
    setError('');
    if (!skip && !answer.trim() && !files.length) { setError('Type an answer, attach a document, or skip.'); return; }
    setBusy(true);
    try {
      const document_ids = !skip && files.length ? await uploadAll(sprint.id, files) : [];
      const body = { answer: skip ? '' : answer.trim(), document_ids, skip };
      const res = followUp && item.response_id
        ? await answerFollowUp(sprint.id, run.id, item.response_id, body)
        : await answerQuestion(sprint.id, run.id, item.question.id, body);
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
      sub={`${item.question.indicator_code}${item.question.condition_ids.length ? ` · ${item.question.condition_ids.join(', ')}` : ''}`}
      actions={<Pill status={followUp ? 'pending' : missing ? 'blocked' : 'active'} label={followUp ? 'Follow-up' : missing ? 'Nothing found yet' : 'About credited evidence'} />}>
      <form onSubmit={(e) => { e.preventDefault(); void send(false); }} className="questionnaire-item">
        <h3>{item.text}</h3>
        {missing && !followUp && <p className="muted">We found nothing for this in the documents submitted. If you have anything, attach it here.</p>}
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

function AdditionalEvidence({ sprint, run }: { sprint: Sprint; run: Run }) {
  const { can } = useAccess();
  const list = useResource<{ results: AdditionalEvidenceItem[] }>(() => listAdditionalEvidence(sprint.id, run.id), `ae:${run.id}`);
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
      const res = await addAdditionalEvidence(sprint.id, run.id, { document_ids, note, picked: all });
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
