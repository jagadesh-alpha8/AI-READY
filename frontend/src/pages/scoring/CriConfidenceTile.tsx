import React from 'react';
import { Link } from 'react-router-dom';

import { getScore } from '../../api/scoring';
import { useApiResource } from '../../hooks/useApiResource';
import type { Scorecard } from '../../types';
import { confidenceBand } from './scoreExplain.ts';

/**
 * The sprint's CRI Evidence Confidence as a compact card for Extracted Facts Review: the score API's
 * overall_confidence from the latest scoring run (backend cri_engine.py) and its band. Recalculating the CRI,
 * and how the value is calculated, live on the Live CRI Preview page.
 */
export const CriConfidenceTile: React.FC<{ sprintId: string }> = ({ sprintId }) => {
  const { data: scorecard, loading, error } = useApiResource<Scorecard>(() => getScore(sprintId), [sprintId]);
  const confidence = scorecard ? scorecard.overall_confidence : null;
  return (
    <div className="glass-card px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="CRI Evidence Confidence">
      <span className="text-[11px] font-bold uppercase tracking-wide text-accent">CRI Evidence Confidence</span>
      <span className="text-2xl font-bold tabular-nums text-accent leading-none">
        {loading ? '…' : confidence == null ? '—' : `${Math.round(confidence * 100)}%`}
      </span>
      {confidence != null && <span className="badge-accent">{confidenceBand(confidence)}</span>}
      {error && <span className="text-xs text-warning">{error}</span>}
      <Link to={`/sprint/${sprintId}/score`} className="text-xs font-semibold text-brand-800 hover:underline ml-auto">
        Live CRI Preview
      </Link>
    </div>
  );
};
