import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';

import { getScore, recalculateScore } from '../../api/scoring';
import { useApiResource } from '../../hooks/useApiResource';
import type { Scorecard } from '../../types';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import { confidenceBand } from './scoreExplain.ts';

/**
 * The sprint's CRI Evidence Confidence as a small tile for Extracted Facts Review, where the facts behind it
 * are confirmed. The value is the score API's overall_confidence from the latest scoring run (backend
 * cri_engine.py); confirming facts does not rescore, so sprint managers can recalculate from here.
 */
export const CriConfidenceTile: React.FC<{ sprintId: string }> = ({ sprintId }) => {
  const { can } = useAccess();
  const { data: scorecard, setData, loading, error } = useApiResource<Scorecard>(() => getScore(sprintId), [sprintId]);
  const [recalculating, setRecalculating] = useState(false);
  const [actionError, setActionError] = useState('');

  const recalculate = async () => {
    setRecalculating(true);
    setActionError('');
    try {
      setData((await recalculateScore(sprintId)).data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to recalculate the CRI score.'));
    } finally {
      setRecalculating(false);
    }
  };

  const confidence = scorecard ? scorecard.overall_confidence : null;
  return (
    <div className="glass-card px-4 py-3 space-y-1" aria-label="CRI Evidence Confidence">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-[11px] font-bold uppercase tracking-wide text-accent">CRI Evidence Confidence</span>
        <span className="text-2xl font-bold tabular-nums text-accent leading-none">
          {loading ? '…' : confidence == null ? '—' : `${Math.round(confidence * 100)}%`}
        </span>
        {confidence != null && <span className="badge-accent">{confidenceBand(confidence)}</span>}
        <span className="flex items-center gap-3 text-xs ml-auto">
          {can('sprint.manage') && (
            <button type="button" onClick={recalculate} disabled={recalculating} className="btn-secondary btn-sm">
              <RefreshCw className={`w-3.5 h-3.5 ${recalculating ? 'animate-spin' : ''}`} />
              <span>{recalculating ? 'Recalculating...' : 'Recalculate'}</span>
            </button>
          )}
          <Link to={`/sprint/${sprintId}/score`} className="font-semibold text-brand-800 hover:underline">Live CRI Preview</Link>
        </span>
      </div>
      <p className="text-xs text-ink-600">
        {error || actionError
          ? <span className="text-warning">{actionError || error}</span>
          : <>{confidence === 0 && <strong className="text-warning">No confirmed or corrected fact backs any factor yet. </strong>}
            Average AI confidence of the confirmed and corrected facts behind each CRI factor, weighted by factor
            weight. Calculated {scorecard?.calculated_at ? new Date(scorecard.calculated_at).toLocaleString() : '—'};
            confirming facts here does not update it until the CRI is recalculated.</>}
      </p>
    </div>
  );
};
