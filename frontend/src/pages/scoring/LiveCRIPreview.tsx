import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getScore, recalculateScore } from '../../api/scoring';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Scorecard } from '../../types';
import { BarChart3, ArrowRight, RefreshCw } from 'lucide-react';

export const LiveCRIPreview: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const [recalculating, setRecalculating] = useState(false);
  const [actionError, setActionError] = useState('');

  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';
  const {
    data: scorecard,
    setData: setScorecard,
    loading,
    error,
    refetch,
  } = useApiResource<Scorecard>(() => getScore(sprintId!), [sprintId], isRealSprint);

  const handleRecalculate = async () => {
    if (!isRealSprint) {
      setActionError('No active sprint is selected. Set up a sprint first.');
      return;
    }
    setRecalculating(true);
    setActionError('');
    try {
      const res = await recalculateScore(sprintId!);
      setScorecard(res.data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to recalculate the CRI score.'));
    } finally {
      setRecalculating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-brand-800" /> Screen 7: Live CRI Score Preview
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Config-driven CRI score calculation aggregated across all eight pillars with confidence weighting and penalties.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={handleRecalculate} disabled={recalculating} className="btn-secondary">
              <RefreshCw className={`w-3.5 h-3.5 ${recalculating ? 'animate-spin' : ''}`} />
              <span>{recalculating ? 'Recalculating...' : 'Recalculate Scores'}</span>
            </button>
            <button onClick={() => navigate(`/sprint/${sprintId}/approval`)} className="btn-primary shrink-0">
              <span>Proceed to Baseline Approval</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {loading ? (
        <LoadingState message="Calculating CRI score..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !scorecard ? (
        <LoadingState message="No score available for this sprint yet." />
      ) : (
        <>
          {/* Main Score Overview Header */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="glass-card p-6 sm:p-8 bg-gradient-to-br from-brand-50 to-card text-center">
              <span className="text-xs font-bold text-brand-800 uppercase tracking-wide">Overall CRI Baseline Score</span>
              <div className="text-4xl sm:text-5xl font-bold text-ink-900 my-3 tracking-tight tabular-nums">
                {scorecard.cri_score} <span className="text-lg font-normal text-ink-500">/ 100</span>
              </div>
              <span className="badge-brand">Confidence-Weighted Baseline</span>
            </div>

            <div className="glass-card p-6 sm:p-8 text-center">
              <span className="text-xs font-bold text-accent uppercase tracking-wide">CRI Evidence Confidence</span>
              <div className="text-4xl sm:text-5xl font-bold text-accent my-3 tracking-tight tabular-nums">
                {(scorecard.cri_confidence * 100).toFixed(0)}%
              </div>
              <span className="badge-accent">
                {scorecard.cri_confidence >= 0.8 ? 'Confidence Band: High (>=80%)' : 'Confidence Band: Building'}
              </span>
            </div>
          </div>

          {/* 8 Pillar Scorecards */}
          <div className="glass-card p-5 sm:p-6">
            <h2 className="eyebrow mb-4">Eight Pillar Scorecard Breakdown</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {(scorecard.pillar_scores || []).map((p) => (
                <div key={p.pillar} className="p-4 bg-surface rounded-xl border border-line-200 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold text-ink-900">{p.label || p.pillar}</span>
                    <span className="text-xs font-mono font-bold text-brand-800 tabular-nums">{p.score} / 100</span>
                  </div>
                  <div className="w-full bg-line-200 h-2 rounded-full overflow-hidden">
                    <div
                      className="bg-brand-500 h-full rounded-full transition-all duration-500"
                      style={{ width: `${p.score}%` }}
                    ></div>
                  </div>
                  <div className="flex items-center justify-between text-xs text-ink-500">
                    <span>Weight: {(p.weight * 100).toFixed(0)}%</span>
                    <span>Confidence: {(p.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
