import React from 'react';
import { Link } from 'react-router-dom';

import { getAIQIFSummary, type AIQIFSummary } from '../../api/facts';
import { useApiResource } from '../../hooks/useApiResource';
import type { Fact } from '../../types';

/** What a fact is for, in words (backend apps/facts/aiqif_tagging.py). No indicator codes: the sales view. */
export const FactKindBadge: React.FC<{ fact: Fact }> = ({ fact }) => {
  if (fact.fact_kind === 'ai_evidence') {
    return <span className="badge-success" title="This fact is about AI at the institution: it can count toward AI-QIF coverage.">AI evidence</span>;
  }
  if (fact.fact_kind === 'context') {
    return <span className="badge-neutral" title="A number or detail AI evidence is read against (intake, enrolment, counts). Not AI evidence itself.">Context</span>;
  }
  if (fact.fact_kind === 'profile') {
    return <span className="badge-neutral" title="Who the institution is (type, approvals, programmes). It decides which indicators apply.">Institution profile</span>;
  }
  return <span className="text-xs text-ink-400" title="Classified when the tagging rules are applied to existing facts.">Not classified yet</span>;
};

/** One line for everyone on the sprint: how many facts are AI evidence / context / profile, and whether
 * AI-QIF coverage is provisional because items wait for the AI-QIF expert (Super Admin). Nothing to choose. */
export const AIQIFSummaryBar: React.FC<{ sprintId: string; reloadKey?: unknown; expert?: boolean }> = ({
  sprintId, reloadKey, expert,
}) => {
  const { data } = useApiResource<AIQIFSummary>(() => getAIQIFSummary(sprintId), [sprintId, reloadKey], !!sprintId);
  if (!data || data.facts === 0) return null;
  const queue = data.expert_queue.total;
  return (
    <div className="mb-4 rounded-lg border border-line-200 bg-surface-50 px-4 py-2 text-sm text-ink-700 flex flex-wrap items-center gap-x-3 gap-y-1"
      data-testid="aiqif-summary">
      <span className="tabular-nums">
        {data.facts} facts · {data.ai_evidence} AI evidence · {data.context} context · {data.profile} profile
        {data.not_classified > 0 && ` · ${data.not_classified} not classified yet`}
      </span>
      {queue > 0 ? (
        <span className="text-warning text-xs">
          AI-QIF coverage is provisional: {queue} item{queue === 1 ? '' : 's'} with the AI-QIF expert.
          {expert && (
            <> <Link to={`/sprint/${sprintId}/aiqif-review`} className="text-brand-800 hover:underline">Open the expert queue</Link></>
          )}
        </span>
      ) : (
        <span className="text-xs text-ink-500">Indicators are assigned automatically; nothing to choose here.</span>
      )}
    </div>
  );
};
