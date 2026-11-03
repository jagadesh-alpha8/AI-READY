import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../../api/client';
import { useApiResource } from '../../hooks/useApiResource';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import { FactsReview } from './FactsReview';

interface Alternative { value: unknown; fact_ids: string[]; excerpts: { filename: string; page: string; quote: string; verification: string }[] }
interface Case { kind?: string; id: string; question: string; scope: unknown; alternatives: Alternative[]; state: string; suggestion: string; reason: string; affected_requirements: string[]; conflict: boolean; initial: boolean }
interface Batch { started: boolean; initial_limit: number; cases: Case[]; overflow: Case[]; mode: string; new_unbatched_fact_count?: number; new_material_case_count?: number; note?: string }

export function ReviewJourney() {
  const { sprintId } = useParams();
  const { can } = useAccess();
  const { data, refetch, error } = useApiResource<Batch>(() => api.get(`/sprints/${sprintId}/review-batch`), [sprintId]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [optional, setOptional] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  async function submit(c?: Case, action?: string, factId?: string, sourceInstitution?: unknown) {
    setBusy(true); setFailure('');
    try {
      const body: Record<string, unknown> = { action, fact_id: factId, source_institution: sourceInstitution, reason: c ? reasons[c.id] || '' : '', optional_follow_up: c ? !c.initial : false };
      if (action === 'correct' && c) body.value = JSON.parse(values[c.id] || 'null');
      await api.post(`/sprints/${sprintId}/review-batch${c ? `/${c.id}` : ''}`, body);
      refetch();
    } catch (e) { setFailure(getErrorMessage(e, 'Unable to save this decision. Enter a corrected value as JSON, for example 42 or "available".')); }
    finally { setBusy(false); }
  }
  const completed = data?.cases.filter(c => !['awaiting', 'stale'].includes(c.state)).length || 0;
  return <div className="space-y-4">
    <h2 className="text-xl font-bold">Review the questions that matter</h2>
    <p className="text-sm">Review up to 25 grouped questions across scope, identity and capability evidence. Each answer applies only to the claims and scope shown. You can finish early with provisional findings.</p>
    {(failure || error) && <p role="alert" className="text-danger">{failure || String(error)}</p>}
    {!data?.started ? <button disabled={busy || !can('facts.review')} className="btn-primary" onClick={() => submit()}>Prepare review questions</button> : <>
      <p role="status">{completed} of {data.cases.length} initial questions settled · {data.overflow.length} optional overflow questions.</p>
      <p className="text-sm">{data.mode === 'shadow' ? 'Automatic checking is in shadow mode: eligible facts are checked but not automatically accepted.' : 'Existing verification rules automatically accept eligible evidence. Source and risk checks still apply.'}</p>
      {data.cases.length === 0 && <p>No material questions were identified. Supporting facts remain available below.</p>}
      {(optional ? [...data.cases, ...data.overflow] : data.cases).map(c => <article key={c.id} className="glass-card p-4 space-y-3">
        <h3 className="font-bold">{c.question}</h3>
        <p className="text-sm">{c.reason} · {c.state.replace(/_/g, ' ')}</p>
        {['awaiting', 'stale'].includes(c.state) && <>
          <p className="text-sm">{c.suggestion}</p>
          {c.alternatives.map((a, i) => <div key={i} className="panel-muted space-y-2">
            <p className="font-semibold">{JSON.stringify(a.value)} · {a.fact_ids.length} linked claim(s)</p>
            {a.excerpts.map((e, j) => <blockquote key={j} className="text-sm"><p>{e.quote || 'No document quotation supplied.'}</p><cite>{e.filename} · page {e.page || 'unspecified'} · source check: {e.verification || 'not checked'}</cite></blockquote>)}
            <button className="btn-secondary btn-sm" disabled={busy || !can('facts.review') || c.state === 'stale'} onClick={() => submit(c, c.kind === 'identity' ? 'identity' : c.conflict ? 'choose' : 'confirm', a.fact_ids[0], c.kind === 'identity' ? a.value : undefined)}>{c.conflict ? 'Choose this alternative' : 'Confirm this scoped value'}</button>
          </div>)}
          <label className="block text-sm">Basis or reason<textarea className="input w-full" value={reasons[c.id] || ''} onChange={e => setReasons({ ...reasons, [c.id]: e.target.value })} /></label>
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary btn-sm" disabled={busy || !can('facts.review') || c.state === 'stale'} onClick={() => submit(c, 'cannot_establish')}>Cannot establish</button>
            <button className="btn-secondary btn-sm" disabled={busy || !can('facts.review') || c.state === 'stale'} onClick={() => submit(c, 'defer')}>Defer</button>
            <Link className="btn-secondary btn-sm" to={`/sprint/${sprintId}/upload`}>Supply evidence</Link>
          </div>
          <details><summary>Correct with a basis</summary><p className="text-sm">A manual answer is recorded as a declaration. It earns no automatic credit and is not a document quotation. Supply supporting evidence for a fresh assessment.</p><input aria-label="Corrected value as JSON" className="input" value={values[c.id] || ''} onChange={e => setValues({ ...values, [c.id]: e.target.value })} placeholder='42 or "available"' /><button className="btn-secondary btn-sm" disabled={busy || !can('facts.review') || c.state === 'stale'} onClick={() => submit(c, 'correct')}>Record correction</button></details>
        </>}
        <details><summary>Scope and affected assessment areas</summary><pre className="text-xs whitespace-pre-wrap">{JSON.stringify(c.scope, null, 2)}</pre><p className="text-sm">{c.affected_requirements.length} potentially affected requirements. This is a relevance link, not a promised score change.</p><p className="text-xs">{c.affected_requirements.join(', ')}</p></details>
      </article>)}
      <p className="text-sm">{data.note}</p>
      {!!data.new_material_case_count && <p role="status">{data.new_material_case_count} new or changed material question(s) are available. Initial questions will not refill. <button className="btn-secondary btn-sm" disabled={busy || !can('facts.review')} onClick={async () => { setBusy(true); setFailure(''); try { await api.post(`/sprints/${sprintId}/review-batch`, { optional_follow_up: true }); setOptional(true); refetch(); } catch (e) { setFailure(getErrorMessage(e)); } finally { setBusy(false); } }}>Prepare optional follow-up</button></p>}
      {data.overflow.length > 0 && <button className="btn-secondary" onClick={() => setOptional(!optional)}>{optional ? 'Hide optional follow-up' : 'Show optional follow-up beyond the initial batch'}</button>}
    </>}
    <Link className="btn-primary inline-block" to={`/sprint/${sprintId}/score`}>Continue to capability assessment</Link>
    <p className="text-sm">Start a fresh assessment to include saved decisions. Unknown or unavailable evidence stays explicit; reviewing a claim does not automatically satisfy a capability requirement.</p>
    <details><summary>Search all supporting facts and technical history</summary><FactsReview /></details>
  </div>;
}
