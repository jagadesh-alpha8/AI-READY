import React, { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';

import {
  addFactMapping, autoCheckAIQIFQueue, decideFactKind, getAIQIFExpertQueue, listSprintFactsPage,
  type AIQIFExpertQueue as Queue,
} from '../../api/facts';
import type { Page } from '../../api/pagination';
import { Pagination, useDebounced } from '../../components/Pagination';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import type { Fact } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { FactKindBadge } from './AIQIFSummaryBar';
import { AIQIFTagRow, FactReviewState } from './AIQIFTagRow';

type Relationship = 'direct' | 'supporting' | 'contextual';
const REVIEWED_PAGE_SIZE = 20;

/** Why this fact is in the queue, in words. */
function reasons(fact: Fact): string[] {
  const out: string[] = [];
  if (!fact.fact_kind) out.push('Not classified yet (extracted before automatic tagging).');
  if (fact.kind_needs_check && fact.fact_kind === 'ai_evidence') out.push('AI evidence, but no indicator was accepted: add the indicator it supports.');
  if (fact.kind_needs_check && (fact.fact_kind === 'context' || fact.fact_kind === 'profile')) {
    out.push(`Filed as ${fact.fact_kind}, but it may be AI evidence (its text mentions AI, or it had a confident tag).`);
  }
  const waiting = fact.aiqif_mappings.filter((m) => m.pending);
  const reopened = waiting.filter((m) => m.pending_since);
  if (reopened.length) {
    out.push(`${reopened.length} tag${reopened.length === 1 ? '' : 's'} reopened or edited by an expert: decide again.`);
  }
  if (waiting.length > reopened.length) {
    const n = waiting.length - reopened.length;
    out.push(`${n} AI tag${n === 1 ? '' : 's'} not accepted automatically (low confidence, or outside the fact's criterion).`);
  }
  return out;
}

/**
 * The AI-QIF expert queue (Super Admin only; backend apps/facts/aiqif_tagging.py). Everything the automatic
 * rules could not settle: AI tags to confirm or reject, facts whose kind needs a decision, AI evidence without
 * an indicator. Each decision is recorded in the fact's history and kept by later re-extraction. While the queue
 * is not empty the sprint's AI-QIF coverage is provisional and its baseline cannot be decided.
 */
export const AIQIFExpertQueue: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const { data, loading, error, refetch } = useApiResource<Queue>(() => getAIQIFExpertQueue(sprintId!), [sprintId], !!sprintId);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [autoMessage, setAutoMessage] = useState('');
  const [autoBusy, setAutoBusy] = useState(false);
  // Earlier expert decisions now, the AI second opinion in the background; the queue refreshes after both.
  const decideAutomatically = async () => {
    setAutoBusy(true); setActionError(''); setAutoMessage('');
    try {
      const { data: r } = await autoCheckAIQIFQueue(sprintId!);
      setAutoMessage(`${r.precedent_decisions} tag${r.precedent_decisions === 1 ? '' : 's'} decided from earlier expert `
        + `decisions. ${r.ai_check === 'queued' ? 'The AI second opinion is checking the rest -- refresh in a minute.'
          : r.ai_check === 'off' ? 'The AI second opinion is switched off.' : 'The AI second opinion could not start.'} `
        + `${r.expert_queue.total} item${r.expert_queue.total === 1 ? '' : 's'} still waiting.`);
      refetch(); reviewed.refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Automatic decisions could not run.'));
    } finally { setAutoBusy(false); }
  };
  const [adding, setAdding] = useState<Record<string, { code: string; relationship: Relationship }>>({});
  // Pending (the queue) or Reviewed (decided tags, to edit or reopen); Extracted Facts Review links here.
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'reviewed' ? 'reviewed' : 'pending';
  const setTab = (next: 'pending' | 'reviewed') => setParams(next === 'reviewed' ? { tab: next } : {});
  const [search, setSearch] = useState(params.get('q') || '');
  const q = useDebounced(search.trim());
  const [pageState, setPageState] = useState({ key: q, page: 1 });
  const page = pageState.key === q ? pageState.page : 1;
  const setPage = (next: number) => setPageState({ key: q, page: next });
  const reviewed = useApiResource<Page<Fact>>(
    () => listSprintFactsPage(sprintId!, { tag_review: 'reviewed', q, page, page_size: REVIEWED_PAGE_SIZE }),
    [sprintId, q, page, tab], !!sprintId && tab === 'reviewed');

  const act = async (factId: string, run: () => Promise<unknown>) => {
    setBusy(factId); setActionError('');
    try { await run(); refetch(); reviewed.refetch(); } catch (err) { setActionError(getErrorMessage(err, 'The decision could not be saved.')); }
    finally { setBusy(null); }
  };

  // One fact's card -- the same in both tabs.
  const card = (fact: Fact, indicators: Queue['indicators']) => {
    const add = adding[fact.id] || { code: '', relationship: 'supporting' as Relationship };
    const isBusy = busy === fact.id;
    return (
      <div key={fact.id} className="glass-card p-4 space-y-2 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-bold text-ink-900">{fact.field_name} <span className="font-mono text-xs text-ink-500">{fact.field_key}</span></p>
            <p className="text-ink-800">Value: {typeof fact.value_json === 'object' ? JSON.stringify(fact.value_json) : String(fact.value_json)}</p>
            <p className="text-xs text-ink-500 mt-0.5">“{fact.source_snippet}” — {fact.source_document_filename || 'document'}{fact.source_page ? `, p. ${fact.source_page}` : ''}{fact.naac_metric ? ` · NAAC ${fact.naac_metric}` : ''}</p>
          </div>
          <FactKindBadge fact={fact} />
        </div>
        <ul className="text-xs text-warning list-disc pl-4">{reasons(fact).map((r) => <li key={r}>{r}</li>)}</ul>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-ink-500">This fact is:</span>
          {(['ai_evidence', 'context', 'profile'] as const).map((kind) => (
            <button key={kind} disabled={isBusy} className={fact.fact_kind === kind && fact.kind_reviewed_at ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
              onClick={() => act(fact.id, () => decideFactKind(fact.id, kind))}>
              {kind === 'ai_evidence' ? 'AI evidence' : kind === 'context' ? 'Context' : 'Institution profile'}
            </button>
          ))}
        </div>
        <FactReviewState fact={fact} />
        {fact.aiqif_mappings.length > 0 && (
          <div className="space-y-2">
            {fact.aiqif_mappings.map((m) => (
              <AIQIFTagRow key={m.indicator_code} fact={fact} mapping={m} indicators={indicators}
                onChanged={() => { refetch(); reviewed.refetch(); }} onError={setActionError} />
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select className="input text-xs py-1 max-w-xs" value={add.code}
            onChange={(e) => setAdding({ ...adding, [fact.id]: { ...add, code: e.target.value } })}>
            <option value="">Add an indicator…</option>
            {indicators.map((i) => <option key={i.code} value={i.code}>{i.code.replace(/^AIQIF-/, '')} {i.name}</option>)}
          </select>
          <select className="input text-xs py-1" value={add.relationship}
            onChange={(e) => setAdding({ ...adding, [fact.id]: { ...add, relationship: e.target.value as Relationship } })}>
            <option value="direct">Direct</option>
            <option value="supporting">Supporting</option>
            <option value="contextual">Contextual (does not count)</option>
          </select>
          <button className="btn-secondary btn-sm" disabled={isBusy || !add.code}
            onClick={() => act(fact.id, () => addFactMapping(fact.id, add.code, add.relationship))}>Add</button>
        </div>
      </div>
    );
  };

  const tabClass = (active: boolean) => `px-3 py-1.5 rounded-lg text-sm font-semibold ${
    active ? 'bg-brand-500 text-on-brand' : 'bg-surface border border-line-200 text-ink-600 hover:border-line-300'}`;
  const indicators = data?.indicators || [];

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-brand-800" /> AI-QIF expert queue
        </h1>
        <p className="text-sm text-ink-500 mt-1">
          Pending: what the automatic tagging could not settle -- until it is empty the sprint's AI-QIF coverage is
          provisional and its baseline cannot be decided. Reviewed: tags already confirmed or rejected, to edit or
          reopen. Tag decisions never change the facts themselves. The sales team never sees this page.
        </p>
        <Link to={`/sprint/${sprintId}/facts`} className="text-xs text-brand-800 hover:underline">Back to Extracted Facts Review</Link>
      </div>
      <div className="flex gap-2">
        <button type="button" className={tabClass(tab === 'pending')} onClick={() => setTab('pending')}>
          Pending{data ? ` (${data.count})` : ''}
        </button>
        <button type="button" className={tabClass(tab === 'reviewed')} onClick={() => setTab('reviewed')}
          title="Decided by an expert, or automatically (earlier expert decision / AI second opinion) -- to edit or reopen">
          Reviewed{reviewed.data ? ` (${reviewed.data.count})` : ''}
        </button>
        <button type="button" className="btn-secondary btn-sm ml-auto" disabled={autoBusy} onClick={decideAutomatically}
          title="Apply earlier expert decisions on the same fields, then ask the AI for a second opinion on the rest">
          {autoBusy ? 'Deciding…' : 'Decide automatically'}
        </button>
      </div>
      {autoMessage && <p className="text-xs text-ink-600">{autoMessage}</p>}
      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {tab === 'pending' ? (
        loading && !data ? <LoadingState message="Loading the expert queue..." />
          : error ? <ErrorState message={error} onRetry={refetch} />
          : !data || data.count === 0 ? (
            <div className="panel-muted"><p className="text-sm text-ink-500">Nothing is waiting: AI-QIF coverage for this sprint is final.</p></div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-ink-500">{data.count} fact{data.count === 1 ? '' : 's'} waiting.</p>
              {data.facts.map((fact) => card(fact, indicators))}
            </div>
          )
      ) : (
        <div className="space-y-3">
          <input className="input text-sm w-full sm:w-96" placeholder="Search field ID, value, quote or indicator…"
            value={search} onChange={(e) => setSearch(e.target.value)} />
          {reviewed.loading && !reviewed.data ? <LoadingState message="Loading reviewed tags..." />
            : reviewed.error ? <ErrorState message={reviewed.error} onRetry={reviewed.refetch} />
            : !reviewed.data || reviewed.data.count === 0 ? (
              <div className="panel-muted"><p className="text-sm text-ink-500">No confirmed or rejected tag{q ? ' matches this search' : ' yet'}.</p></div>
            ) : (
              <>
                {reviewed.data.results.map((fact) => card(fact, indicators))}
                <Pagination page={page} pageSize={REVIEWED_PAGE_SIZE} count={reviewed.data.count} onPage={setPage} />
              </>
            )}
        </div>
      )}
    </div>
  );
};
