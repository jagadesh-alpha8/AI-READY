import React from 'react';

import { getScore } from '../../api/scoring';
import { useApiResource } from '../../hooks/useApiResource';
import type { Scorecard } from '../../types';
import { confidenceBand } from './scoreExplain.ts';

/**
 * The sprint's CRI Evidence Confidence as one inline line in the Extracted Facts Review header: the score API's
 * overall_confidence from the latest scoring run (backend cri_engine.py) and its band. Recalculating the CRI,
 * and how the value is calculated, live on the Live CRI Preview page (reached from the sidebar).
 */
export const CriConfidenceTile: React.FC<{ sprintId: string }> = ({ sprintId }) => {
  const { data: scorecard, loading, error } = useApiResource<Scorecard>(() => getScore(sprintId), [sprintId]);
  const confidence = scorecard ? scorecard.overall_confidence : null;
  return (
    <p className="mt-2 flex flex-wrap items-center gap-2 text-sm" aria-label="CRI Evidence Confidence">
      <span className="text-ink-500">CRI Evidence Confidence:</span>
      <span className="font-bold tabular-nums text-accent">
        {loading ? '…' : confidence == null ? '—' : `${Math.round(confidence * 100)}%`}
      </span>
      {confidence != null && <span className="badge-accent">{confidenceBand(confidence)}</span>}
      {error && <span className="text-xs text-warning">{error}</span>}
    </p>
  );
};
