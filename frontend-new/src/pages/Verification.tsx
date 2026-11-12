import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, KeyValues, Loading, Notice, PageHeading, Panel, Pill, Stat, Table, Tabs } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import {
  bulkConfirmFacts, decideCorrection, decideReviewCase, getShadowReport, getVerificationSummary, listSprintCorrections,
  listSprintFactsPage, reverifySprint, startReviewBatch, getReviewBatch,
} from '../services/facts';
import type { Fact, Page, Sprint } from '../types/api';
import type { CorrectionProposal, ReviewAction, ReviewBatch, ReviewCase, VerificationSummary } from '../types/workflow';
import { dateTime, humanize, tidyText, valueText } from '../utils/format';

const TABS = [
  { key: 'review', label: 'Guided review' },
  { key: 'summary', label: 'Verification' },
  { key: 'corrections', label: 'Proposed corrections' },
  { key: 'bulk', label: 'Bulk confirm' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export function Verification() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const [tab, setTab] = useState<Tab>('review');
  return (
    <>
      <PageHeading page="verification" />
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Verification views" />
      {tab === 'review' && <GuidedReview sprint={sprint} />}
      {tab === 'summary' && <Summary sprint={sprint} />}
      {tab === 'corrections' && <Corrections sprint={sprint} />}
      {tab === 'bulk' && <BulkConfirm sprint={sprint} />}
    </>
  );
}

// --- guided review: at most 25 prioritised questions ------------------------------------------------------

function GuidedReview({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const batch = useResource<ReviewBatch>(() => getReviewBatch(sprint.id), `rb:${sprint.id}`);
  const { busy, msg, setMsg, run } = useRunner();
  const [deciding, setDeciding] = useState<{ c: ReviewCase; action: ReviewAction } | null>(null);
  const b = batch.data;
  const start = (followUp: boolean) => run('start', async () => { const res = await startReviewBatch(sprint.id, followUp); batch.setData(res.data); },
    followUp ? 'Optional follow-up questions added.' : 'Guided review started: the extracted facts were verified and the questions prioritised.');

  const open = (b?.cases || []).filter((c) => c.state !== 'decided' && !b?.decisions[c.id]);
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {batch.loading && !b ? <Loading /> : batch.error ? <ErrorState error={batch.error} onRetry={() => void batch.refetch()} /> : !b?.started ? (
        <Empty title="Guided review not started" action={can('facts.review') && (
          <button className="primary-action" disabled={!!busy} onClick={() => void start(false)}>{busy === 'start' ? 'Preparing…' : 'Start guided review'}</button>
        )}>
          Instead of checking every fact, answer at most {b?.initial_limit ?? 25} questions chosen for their effect on the assessment.
        </Empty>
      ) : (
        <>
          <div className="stat-grid">
            <Stat label="Questions" value={b.cases.length} note={`${b.overflow.length} more held back`} />
            <Stat label="Answered" value={Object.keys(b.decisions).length} />
            <Stat label="Still open" value={open.length} />
            <Stat label="New since start" value={b.new_material_case_count ?? 0} note={`${b.new_unbatched_fact_count ?? 0} new facts`} />
          </div>
          {b.note && <Notice tone="info">{b.note}</Notice>}
          {can('facts.review') && b.overflow.length > 0 && (
            <div className="button-row"><button className="secondary-button" disabled={!!busy} onClick={() => void start(true)}>Add optional follow-up questions</button></div>
          )}
          {b.cases.map((c) => {
            const decision = b.decisions[c.id];
            return (
              <Panel key={c.id} title={c.question} sub={c.reason}
                actions={<Pill status={decision ? 'active' : c.conflict ? 'blocked' : 'pending'} label={decision ? humanize(decision.action) : c.conflict ? 'Contradiction' : 'Open'} />}>
                {c.suggestion && <p><b>Suggested:</b> {tidyText(c.suggestion)}</p>}
                {c.affected_requirements.length > 0 && <p className="muted">Affects {c.affected_requirements.join(', ')}</p>}
                {c.alternatives.map((alt, i) => (
                  <article key={i} className="condition">
                    <div><b>Value {String.fromCharCode(65 + i)}:</b> {valueText(alt.value)}</div>
                    {alt.excerpts.map((e) => (
                      <blockquote key={e.fact_id}><p>{tidyText(e.quote)}</p><cite>{e.filename}{e.page && `, page ${e.page}`}{e.verification && ` · ${humanize(e.verification)}`}</cite></blockquote>
                    ))}
                  </article>
                ))}
                {decision ? <p className="muted">Decided {dateTime(decision.timestamp)}: {decision.rationale}</p> : can('facts.review') && (
                  <div className="row-actions">
                    {c.kind === 'identity'
                      ? <button className="primary-action small" onClick={() => setDeciding({ c, action: 'identity' })}>Confirm identity</button>
                      : c.alternatives.length > 1
                        ? <button className="primary-action small" onClick={() => setDeciding({ c, action: 'choose' })}>Choose a value</button>
                        : <button className="primary-action small" onClick={() => setDeciding({ c, action: 'confirm' })}>Confirm</button>}
                    <button className="secondary-button" onClick={() => setDeciding({ c, action: 'correct' })}>Correct</button>
                    <button className="secondary-button" onClick={() => setDeciding({ c, action: 'defer' })}>Defer</button>
                    <button className="secondary-button" onClick={() => setDeciding({ c, action: 'cannot_establish' })}>Cannot establish</button>
                  </div>
                )}
              </Panel>
            );
          })}
        </>
      )}
      {deciding && (
        <ActionDialog title={humanize(deciding.action)} confirmLabel="Record answer" description={deciding.c.question}
          fields={[
            ...((deciding.action === 'choose' || deciding.action === 'correct' || deciding.action === 'confirm') && deciding.c.alternatives.length > 0 ? [{
              name: 'fact_id', label: deciding.action === 'correct' ? 'Value being corrected' : 'The correct value', type: 'select' as const, required: true,
              initial: deciding.c.alternatives.length === 1 ? deciding.c.alternatives[0].fact_ids[0] : '',
              options: deciding.c.alternatives.map((a, i) => ({ value: a.fact_ids[0], label: `${String.fromCharCode(65 + i)}: ${valueText(a.value)}` })),
            }] : []),
            ...(deciding.action === 'correct' ? [{ name: 'value', label: 'Correct value', required: true }] : []),
            ...(deciding.action === 'identity' ? [{
              name: 'source_institution', label: 'Institution the documents belong to', type: 'select' as const, required: true,
              options: deciding.c.alternatives.map((a) => ({ value: String(a.value), label: valueText(a.value) })),
            }] : []),
            { name: 'reason', label: 'Basis or reason for this decision', type: 'textarea' as const, required: true },
          ]}
          onSubmit={async (v) => {
            const res = await decideReviewCase(sprint.id, deciding.c.id, {
              action: deciding.action,
              fact_id: v.fact_id || undefined,
              value: deciding.action === 'correct' ? v.value : undefined,
              reason: v.reason,
              source_institution: v.source_institution || undefined,
              optional_follow_up: !deciding.c.initial || undefined,
            });
            batch.setData(res.data);
            setMsg({ tone: 'success', text: 'Answer recorded.' });
          }}
          onClose={() => setDeciding(null)} />
      )}
    </>
  );
}

// --- verification summary, shadow report, re-verify ---------------------------------------------------------

function Summary({ sprint }: { sprint: Sprint }) {
  const { can, staff } = useAccess();
  const summary = useResource<VerificationSummary>(() => getVerificationSummary(sprint.id), `vs:${sprint.id}`);
  const [shadow, setShadow] = useState<Record<string, unknown> | null>(null);
  const { busy, msg, setMsg, run } = useRunner();
  const s = summary.data;
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {summary.loading && !s ? <Loading /> : summary.error ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : s && (
        <>
          <div className="stat-grid">
            <Stat label="Facts" value={s.workload.facts} note={`${s.workload.verified_once} verified at least once`} />
            <Stat label="Confirmed by the rules" value={s.workload.auto_verified} note={s.mode === 'enforce' ? 'Enforce mode: confirmed automatically' : 'Shadow mode: recorded only'} />
            <Stat label="Sent to people" value={s.workload.sent_to_review} note="Facts the rules could not settle" />
            <Stat label="Reviewer overrides" value={s.workload.reviewer_overrides} note={`Policy ${s.policy_version}`} />
          </div>
          <Panel title="Outcomes" actions={(
            <div className="row-actions">
              {can('sprint.manage') && <button className="secondary-button" disabled={!!busy} onClick={() => void run('reverify', async () => {
                const res = await reverifySprint(sprint.id); await summary.refetch();
                return res.data;
              }, (r) => { const d = r as { checked: number; mode: string }; return `${d.checked} facts verified again (${d.mode} mode).`; })}>Verify again</button>}
              {staff && <button className="secondary-button" disabled={!!busy} onClick={() => void run('shadow', async () => { setShadow((await getShadowReport(sprint.id)).data); })}>Shadow report</button>}
            </div>
          )}>
            <KeyValues data={s.workload.outcomes} />
          </Panel>
          <Table columns={['Group', 'Facts', 'High risk']}>
            {s.groups.map((g) => <tr key={g.code}><td>{g.label}</td><td>{g.count}</td><td>{g.high_risk}</td></tr>)}
          </Table>
          {shadow && <Panel title="Shadow report" sub="What the policy would do compared with what reviewers did"><KeyValues data={shadow} /></Panel>}
        </>
      )}
    </>
  );
}

// --- proposed corrections: a different reviewer decides ----------------------------------------------------

function Corrections({ sprint }: { sprint: Sprint }) {
  const { can, user } = useAccess();
  const [status, setStatus] = useState('pending');
  const list = useResource<CorrectionProposal[]>(() => listSprintCorrections(sprint.id, status), `corr:${sprint.id}:${status}`);
  const [deciding, setDeciding] = useState<{ p: CorrectionProposal; decision: 'approve' | 'reject' | 'withdraw' } | null>(null);
  const [done, setDone] = useState('');
  return (
    <>
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      <div className="filter-bar">
        <label className="field inline"><span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {['pending', 'approved', 'rejected', 'withdrawn', 'stale'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
        </label>
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> :
        !list.data?.length ? <Empty title="No corrections here">Corrections are proposed from the full-fact view in Evidence review.</Empty> : (
          <Table columns={['Field', 'Before → proposed', 'Source', 'Proposed by', 'Status', '']}>
            {list.data.map((p) => {
              const mine = p.submitted_by_name === user?.name;
              return (
                <tr key={p.id}>
                  <td><strong>{p.field_name}</strong><small className="cell-sub clamp-2">{tidyText(p.reason)}</small></td>
                  <td>{valueText(p.value_before)} → <b>{valueText(p.proposed_value)}</b>{p.verification?.outcome && <small className="cell-sub">Check: {humanize(p.verification.outcome)}</small>}</td>
                  <td>{p.source_document_name || '—'}{p.source_page && `, p. ${p.source_page}`}</td>
                  <td>{p.submitted_by_name}<small className="cell-sub">{dateTime(p.created_at)}</small></td>
                  <td><Pill status={p.status} /></td>
                  <td>{p.status === 'pending' && (
                    <div className="row-actions nowrap">
                      {can('facts.review') && !mine && <>
                        <button className="primary-action small" onClick={() => setDeciding({ p, decision: 'approve' })}>Approve</button>
                        <button className="secondary-button" onClick={() => setDeciding({ p, decision: 'reject' })}>Reject</button>
                      </>}
                      {mine && <button className="secondary-button" onClick={() => setDeciding({ p, decision: 'withdraw' })}>Withdraw</button>}
                    </div>
                  )}</td>
                </tr>
              );
            })}
          </Table>
        )}
      {deciding && (
        <ActionDialog title={`${humanize(deciding.decision)} correction`} confirmLabel={humanize(deciding.decision)}
          description={<p>{deciding.p.field_name}: {valueText(deciding.p.value_before)} → <b>{valueText(deciding.p.proposed_value)}</b></p>}
          fields={[{ name: 'reason', label: 'Reason', type: 'textarea', required: deciding.decision !== 'approve' }]}
          onSubmit={async (v) => { await decideCorrection(deciding.p.id, deciding.decision, v.reason); setDone(`Correction ${deciding.decision === 'withdraw' ? 'withdrawn' : `${deciding.decision}d`}.`); void list.refetch(); }}
          onClose={() => setDeciding(null)} />
      )}
    </>
  );
}

// --- bulk confirm: facts the rules verified exactly ---------------------------------------------------------

function BulkConfirm({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const facts = useResource<Page<Fact>>(() => listSprintFactsPage(sprint.id, { status: 'extracted', verification_status: 'verified', page_size: 100 }), `bulk:${sprint.id}`);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState('');
  const list = facts.data?.results || [];
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <>
      {msg && <Notice tone="success" onClose={() => setMsg('')}>{msg}</Notice>}
      <p className="muted">Facts still waiting for review whose value the rules found exactly in the source. Each confirmation keeps its own history; high-risk facts are skipped by the server.</p>
      {facts.loading ? <Loading /> : facts.error ? <ErrorState error={facts.error} onRetry={() => void facts.refetch()} /> :
        !list.length ? <Empty title="Nothing to bulk confirm">No unreviewed facts are verified exactly.</Empty> : (
          <>
            {can('facts.review') && (
              <div className="button-row">
                <button className="secondary-button" onClick={() => setSelected(selected.size === list.length ? new Set() : new Set(list.map((f) => f.id)))}>
                  {selected.size === list.length ? 'Clear selection' : `Select all ${list.length}`}
                </button>
                <button className="primary-action" disabled={!selected.size} onClick={() => setConfirming(true)}>Confirm {selected.size} selected</button>
              </div>
            )}
            <Table columns={['', 'Fact', 'Value', 'Source', 'Verification']}>
              {list.map((f) => (
                <tr key={f.id}>
                  <td><input type="checkbox" aria-label={`Select ${f.field_name}`} checked={selected.has(f.id)} onChange={() => toggle(f.id)} disabled={!can('facts.review')} /></td>
                  <td><strong>{f.field_name}</strong><small className="cell-sub">{f.pillar_label}</small></td>
                  <td>{valueText(f.value)}</td>
                  <td>{f.source_document_filename || '—'}{f.source_page && `, p. ${f.source_page}`}</td>
                  <td><Pill status="active" label={f.verification?.status_label || 'Verified'} /></td>
                </tr>
              ))}
            </Table>
          </>
        )}
      {confirming && (
        <ActionDialog title={`Confirm ${selected.size} facts?`} confirmLabel="Confirm"
          fields={[{ name: 'comment', label: 'Comment (kept on every fact)', type: 'textarea', required: true, initial: 'Verified exactly against the source.' }]}
          onSubmit={async (v) => {
            const res = await bulkConfirmFacts(sprint.id, Array.from(selected), v.comment, true);
            setMsg(`${res.data.confirmed_count} confirmed, ${res.data.skipped_count} skipped${res.data.skipped.length ? `: ${res.data.skipped.slice(0, 3).map((s) => s.reason).join('; ')}` : ''}.`);
            setSelected(new Set());
            void facts.refetch();
          }}
          onClose={() => setConfirming(false)} />
      )}
    </>
  );
}
