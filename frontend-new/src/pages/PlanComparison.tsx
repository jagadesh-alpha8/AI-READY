import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { cancelPlanEvaluation, downloadPlanEvaluation, getPlanEvaluation, listPlanEvaluations, startPlanEvaluation } from '../services/capability';
import type { Sprint } from '../types/api';
import type { PlanCheckAction, PlanCheckLimits, PlanCheckPage, PlanComparison as Check } from '../types/workflow';
import { newKey } from '../utils/capability';
import { dateTime } from '../utils/format';

/** Check your own plan: a college pastes its AI plan; we say what in it would count, what wouldn't yet, and what we
 * recommend, built on its own plan (plan_mapping.py). A limited number of checks per assessment. */
export function PlanComparison() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

const STATUS: Record<string, [string, string]> = {
  queued: ['pending', 'Starting'], running: ['pending', 'Checking'], completed: ['completed', 'Done'],
  cancelled: ['cancelled', 'Stopped'], failed: ['failed', 'Did not finish'],
};
const PAGES_PER_CHAR = 1 / 3300;   // about 3,300 characters to a page of plan text

function Body({ sprint }: { sprint: Sprint }) {
  const { can, staff } = useAccess();
  const cap = useCapability(sprint.id);
  const runId = cap.run.data?.id || '';
  const list = useResource(() => listPlanEvaluations(sprint.id, runId), `pe:${runId}`, !!runId);
  const [chosen, setChosen] = useState('');
  const checks = list.data?.results || [];
  const shownId = chosen || checks.find((j) => j.status === 'completed')?.id || checks[0]?.id || '';
  const shown = useResource<Check>(() => getPlanEvaluation(sprint.id, runId, shownId), `pe1:${shownId}`, !!shownId);
  const { busy, msg, setMsg, run } = useRunner();
  const [key, setKey] = useState(newKey);
  const [text, setText] = useState('');
  const active = checks.some((j) => j.status === 'queued' || j.status === 'running');
  usePolling(() => { void list.refetch(); if (shownId) void shown.refetch(); }, active, 5000);

  if (cap.loading) return <><PageHeading page="plancompare" /><Loading /></>;
  if (!runId) {
    return (
      <>
        <PageHeading page="plancompare" />
        <Empty title="No result yet" action={<PageLink to="assessment" className="primary-action">Go to the assessment</PageLink>}>
          A plan is checked against your assessment result, so the check opens once you have one.
        </Empty>
      </>
    );
  }
  const limits = list.data?.limits;
  const enabled = list.data?.enabled !== false;
  const max = limits?.max_chars || 40000;
  const tooLong = text.length > max;
  const usedUp = !!limits && limits.remaining <= 0;
  const canStart = can('recommendations.generate') && enabled && !usedUp && !active && !!text.trim() && !tooLong;

  const start = () => run('start', async () => {
    const res = await startPlanEvaluation(sprint.id, runId, text, key);
    setKey(newKey());
    setChosen(res.data.id);
    setText('');
    await list.refetch();
  }, 'Checking your plan. This takes a few minutes; you can leave this page and come back.');

  const download = (id: string, format: 'pdf' | 'docx' | 'html' | 'json') =>
    void run(`d:${id}:${format}`, () => downloadPlanEvaluation(sprint.id, runId, id, format));

  return (
    <>
      <PageHeading page="plancompare" />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Panel title="Check your plan" sub="Paste the actions of your AI plan. We say which would raise your score once done, which wouldn't yet, and what we would change, keeping your budget, timeline and reach.">
        {!enabled && <Notice tone="warn">Plan checks are switched off on this server at the moment.</Notice>}
        {usedUp && <Notice tone="warn"><b>Usage limit reached.</b> This assessment allows {limits!.limit} plan checks and all {limits!.limit} have been used. Your checks below can still be read and downloaded.</Notice>}
        <Usage limits={limits} />
        <label className="field">
          <span>Your plan</span>
          <textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} disabled={!enabled || usedUp}
            placeholder={'1. The Academic Council approves an AI use policy for students by June.\n2. The IQAC runs two AI workshops for teachers, with a short test at the end.\n…'} />
        </label>
        <p className="muted" style={{ margin: '4px 0 10px', color: tooLong ? '#a83c37' : undefined }}>
          {text.length.toLocaleString()} of {max.toLocaleString()} characters (about {Math.max(1, Math.round(text.length * PAGES_PER_CHAR))} of {Math.round(max * PAGES_PER_CHAR)} pages).
          {tooLong ? ' Too long for one check: leave out annexes, budget tables and background, and keep the actions.' : ` Up to ${limits?.max_actions || 40} actions are checked.`}
        </p>
        <button className="primary-action" disabled={!canStart || !!busy} onClick={() => void start()}>
          {active ? 'A check is running' : 'Check this plan'}
        </button>
      </Panel>

      <Panel title="Your checks">
        {list.loading && !list.data ? <Loading /> : list.error ? <ErrorState error={list.error} /> : !checks.length
          ? <p className="muted">No plan checked yet.</p> : (
          <Table columns={['Started', 'Status', '']}>
            {checks.map((j) => {
              const [tone, label] = STATUS[j.status] || ['pending', j.status];
              return (
                <tr key={j.id}>
                  <td>{dateTime(j.created_at)}{j.id === shownId && <small className="cell-sub">Shown below</small>}</td>
                  <td><Pill status={tone} label={label} />{j.stalled && <small className="cell-sub">No progress for a while</small>}</td>
                  <td>
                    <div className="row-actions nowrap">
                      {j.id !== shownId && <button className="secondary-button" onClick={() => setChosen(j.id)}>Show</button>}
                      {(j.status === 'queued' || j.status === 'running') && (
                        <button className="secondary-button" disabled={!!busy} onClick={() => void run(`c:${j.id}`, async () => { await cancelPlanEvaluation(sprint.id, runId, j.id); await list.refetch(); }, 'Check stopped. It counts as one of your plan checks.')}>Stop</button>
                      )}
                      {j.status === 'completed' && j.id === shownId && shown.data && !shown.data.legacy && (
                        <>
                          <button className="secondary-button" disabled={!!busy} onClick={() => download(j.id, 'pdf')}>PDF</button>
                          <button className="secondary-button" disabled={!!busy} onClick={() => download(j.id, 'docx')}>Plan as Word file</button>
                        </>
                      )}
                      {j.status === 'completed' && j.id === shownId && shown.data?.legacy && (
                        <button className="secondary-button" disabled={!!busy} onClick={() => download(j.id, 'html')}>Page</button>
                      )}
                      {staff && j.status === 'completed' && <button className="secondary-button" disabled={!!busy} onClick={() => download(j.id, 'json')}>JSON</button>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Panel>

      {shownId && (shown.loading && !shown.data ? <Loading /> : shown.error ? <ErrorState error={shown.error} /> : shown.data && (
        <Result check={shown.data} />
      ))}
    </>
  );
}

function Usage({ limits }: { limits?: PlanCheckLimits }) {
  if (!limits) return null;
  return (
    <p className="muted" style={{ marginTop: 0 }}>
      <b>{limits.used} of {limits.limit}</b> plan checks used for this assessment. A check that stops because of a problem on our side isn't counted.
    </p>
  );
}

function Result({ check }: { check: Check }) {
  if (check.legacy) {
    return <Notice tone="info">This check was made with an earlier version of the plan check. Download its page from the list above, or check the plan again for the new PDF.</Notice>;
  }
  const p = check.page;
  return (
    <>
      {check.error && <Notice tone={check.status === 'cancelled' ? 'info' : 'error'}>{check.error.next_action}</Notice>}
      {(check.status === 'queued' || check.status === 'running') && <Notice tone="info">Checking your plan. This takes a few minutes.</Notice>}
      {p ? <Page p={p} /> : check.original_review?.actions?.length ? <Partial actions={check.original_review.actions} /> : null}
    </>
  );
}

/** A check that stopped after reading the plan: what each action would do, without recommendations. */
function Partial({ actions }: { actions: PlanCheckAction[] }) {
  return (
    <Panel title="What we checked before the check stopped" sub="The recommendations were not written. Check the plan again for them and for the PDF.">
      <Actions items={actions.map((a) => ({ title: a.title, text: a.text, note: a.note, label: a.status === 'adds' ? 'Counts' : a.label, ok: a.status === 'adds' }))} />
    </Panel>
  );
}

function Page({ p }: { p: PlanCheckPage }) {
  return (
    <>
      <Panel title="What the check found" sub={`Against your ${p.result_kind}, ${p.checked_on}`}>
        <Notice tone="info"><b>How to read this.</b> {p.how_to_read}</Notice>
        {p.score_lines.map((line, i) => <p key={i} style={{ margin: '6px 0', fontWeight: i === 0 ? 600 : 400 }}>{line}</p>)}
        {p.summary && <p style={{ borderLeft: '3px solid var(--accent, #0C4320)', paddingLeft: 10 }}>{p.summary}</p>}
      </Panel>
      <Panel title="What works" sub={`${p.works.length} of ${p.total} actions would raise your score once done and recorded`}>
        {p.works.length ? <Actions items={p.works.map((a) => ({ ...a, label: 'Counts', ok: true }))} />
          : <p className="muted">None of the plan's actions, as written, would leave a record of something your documents do not already show. The recommendations below say what would.</p>}
      </Panel>
      {p.not_yet.length > 0 && (
        <Panel title="What doesn't count yet" sub={`${p.not_yet.length} of ${p.total} actions`}>
          <Actions items={p.not_yet.map((a) => ({ ...a, ok: false }))} />
        </Panel>
      )}
      <Panel title="What we recommend" sub={`${p.kept} action${p.kept === 1 ? '' : 's'} kept as you wrote ${p.kept === 1 ? 'it' : 'them'}`}>
        {p.changes.length ? (
          <ul className="plain-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
            {p.changes.map((c, i) => (
              <li key={i} style={{ marginBottom: 12 }}>
                <Pill status={c.operation === 'drop' ? 'cancelled' : 'completed'} label={c.kind} /> <b>{c.title}</b>
                {c.text && <p style={{ margin: '4px 0' }}>{c.text}</p>}
                {c.why && <p className="muted" style={{ margin: '2px 0' }}><b>Why:</b> {c.why}</p>}
                {c.owner && <p className="muted" style={{ margin: '2px 0' }}><b>Owner:</b> {c.owner}</p>}
                {c.done_when && <p className="muted" style={{ margin: '2px 0' }}><b>Done when:</b> {c.done_when}</p>}
                {c.builds_on.length > 0 && <p className="muted" style={{ margin: '2px 0' }}><b>Builds on:</b> what your documents show at {c.builds_on.join('; ')}</p>}
              </li>
            ))}
          </ul>
        ) : <p className="muted">We recommend no changes: the plan already counts for everything its actions set out to do.</p>}
        {p.outside.length > 0 && <p className="muted">Outside the areas your plan covers, the assessment also found room to grow in {p.outside.join(', ')}. We have not added these to your plan; your Steps page has one for each area.</p>}
        {p.constraints.length > 0 && (
          <>
            <h4 style={{ margin: '14px 0 4px' }}>Kept from your plan</h4>
            <ul className="plain-list">{p.constraints.map((q) => <li key={q}>{q}</li>)}</ul>
          </>
        )}
      </Panel>
      <Panel title="Your plan with our changes" sub="The Word file has this list to edit.">
        <ol style={{ margin: 0, paddingLeft: 22 }}>
          {p.recommended.map((a) => (
            <li key={a.n} style={{ marginBottom: 6 }}>
              {a.text}{a.origin !== 'kept' && <b style={{ marginLeft: 6, fontSize: '0.85em' }}>{a.origin === 'changed' ? 'Changed' : 'Added'}</b>}
              {(a.owner && a.owner !== 'Not stated') || a.done_when ? (
                <small className="cell-sub">{a.owner && a.owner !== 'Not stated' ? `Owner: ${a.owner}. ` : ''}{a.done_when ? `Done when: ${a.done_when}` : ''}</small>
              ) : null}
            </li>
          ))}
        </ol>
      </Panel>
      {(p.unclear.length > 0 || p.warnings.length > 0) && (
        <Panel title="Worth clarifying in your plan">
          <ul className="plain-list">{[...p.unclear, ...p.warnings].map((u) => <li key={u}>{u}</li>)}</ul>
        </Panel>
      )}
      <p className="muted">{p.limits}</p>
    </>
  );
}

function Actions({ items }: { items: { title: string; text: string; note: string; label: string; ok: boolean }[] }) {
  return (
    <ul className="plain-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
      {items.map((a, i) => (
        <li key={i} style={{ marginBottom: 10 }}>
          <Pill status={a.ok ? 'completed' : 'pending'} label={a.label} /> <b>{a.title}</b>
          {a.text && <small className="cell-sub">{a.text}</small>}
          {a.note && <p style={{ margin: '4px 0 0' }}>{a.note}</p>}
        </li>
      ))}
    </ul>
  );
}
