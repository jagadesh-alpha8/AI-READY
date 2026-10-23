import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { BarChart3, ArrowRight, RefreshCw } from 'lucide-react';

import { getScore, recalculateScore } from '../../api/scoring';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { ProcessingStatusBanner } from '../../components/ProcessingStatusBanner';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { useApiResource } from '../../hooks/useApiResource';
import type { Scorecard } from '../../types';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import { BenchmarkAssessmentSection } from './BenchmarkAssessmentSection';
import { CoverageIndicatorTable } from './EvidenceCoverageCard';
import { FactorBreakdown } from './FactorBreakdown';
import { ScorecardsNote } from './ScorecardsNote';
import {
  adjustedReason, coverageCounts, coverageReason, hasCoverage, rawCriZeroReason, reportingPeriod,
} from './scoreExplain.ts';

/**
 * Live CRI Preview: the selected sprint's Raw CRI, evidence coverage and coverage-adjusted CRI, each explained,
 * and the college's Benchmark Assessment in its own section (CRI Evidence Confidence is a tile on Extracted
 * Facts Review). Every number is the score API's (backend apps/scoring: cri_engine.py and coverage.py); this
 * page computes none of them. The page is remounted when the selected sprint changes.
 */
export const LiveCRIPreview: React.FC = () => {
  const { can, canSee, step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const { sprint } = useSelectedSprint();
  const [recalculating, setRecalculating] = useState(false);
  const [actionError, setActionError] = useState('');

  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';
  const { data: scorecard, setData: setScorecard, loading, error, refetch } =
    useApiResource<Scorecard>(() => getScore(sprintId!), [sprintId], isRealSprint);

  const handleRecalculate = async () => {
    if (!isRealSprint) {
      setActionError('No active sprint is selected. Set up a sprint first.');
      return;
    }
    setRecalculating(true);
    setActionError('');
    try {
      setScorecard((await recalculateScore(sprintId!)).data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to recalculate the CRI score.'));
    } finally {
      setRecalculating(false);
    }
  };

  const coverage = scorecard && hasCoverage(scorecard.evidence_coverage) ? scorecard.evidence_coverage : null;
  const counts = coverage ? coverageCounts(coverage) : null;
  const period = sprint ? reportingPeriod(sprint) : '';

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-brand-800" /> Step {step('sprint-score')}: Live Campus Readiness Index Score Preview
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              The sprint's CRI values from its own reviewed facts and open gaps, and the college's Benchmark Assessment
              apart from them.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {can('sprint.manage') && (
              <button onClick={handleRecalculate} disabled={recalculating} className="btn-secondary">
                <RefreshCw className={`w-3.5 h-3.5 ${recalculating ? 'animate-spin' : ''}`} />
                <span>{recalculating ? 'Recalculating...' : 'Recalculate Scores'}</span>
              </button>
            )}
            <button
              onClick={() => navigate(`/sprint/${sprintId}/${canSee('sprint-approval') ? 'approval' : 'recommendations'}`)}
              className="btn-primary shrink-0"
            >
              <span>{canSee('sprint-approval') ? 'Proceed to Baseline Approval' : 'Proceed to Recommendations'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {sprintId && <ProcessingStatusBanner sprintId={sprintId} consequence="This CRI can only use facts from what was read, so it may be understated." />}
      <ScorecardsNote here="cri" />

      {loading ? (
        <LoadingState message="Calculating CRI score..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !scorecard ? (
        <div className="glass-card p-5 text-sm text-ink-600">No score is available for this sprint yet.</div>
      ) : (
        <>
          {/* Which sprint, which period, when calculated -- right next to the numbers. */}
          <div className="glass-card px-5 py-3 text-xs text-ink-600 flex flex-wrap gap-x-4 gap-y-1" aria-label="Scored sprint">
            <span>Sprint <strong className="font-mono text-ink-900">{sprint?.sprint_code || '—'}</strong>
              {sprint?.name && sprint.name !== sprint.institution_name ? ` · ${sprint.name}` : ''}</span>
            <span>{sprint?.institution_name || ''}</span>
            <span>{period || 'Reporting period not set'}</span>
            <span>Calculated {scorecard.calculated_at ? new Date(scorecard.calculated_at).toLocaleString() : '—'}</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-6">
            {/* 1. Raw / Sprint CRI */}
            <ScoreTile label="1 · Raw / Sprint CRI" tone="brand" value={`${scorecard.raw_cri}`} suffix="/ 100"
              note={rawCriZeroReason(scorecard)}>
              Calculated across the 9 AI-QIF factors from this sprint's confirmed and corrected facts. Each factor scores
              0-100 (the weighted average of its criteria, minus penalties for its open gaps) and contributes score x
              weight; the contributions add up to the CRI. See the breakdown below.
            </ScoreTile>

            {/* 2. AI-QIF Evidence Coverage (CRI Evidence Confidence is on Extracted Facts Review) */}
            <ScoreTile label="2 · AI-QIF Evidence Coverage" tone="accent"
              value={coverage?.ratio == null ? '—' : `${Math.round(coverage.ratio * 100)}%`}
              badge={counts ? `${counts.covered} of ${counts.applicable} applicable indicators covered` : undefined}
              note={coverageReason(coverage)}>
              The share of the 36 AI-QIF indicators (by weight) that this sprint's evidence reaches. An indicator is
              covered only when a reviewer has confirmed its AI-QIF tag on a confirmed or corrected fact.
              {counts && (
                <span className="flex flex-wrap gap-1.5 mt-2">
                  <span className="badge-success">Covered {counts.covered}</span>
                  <span className="badge-warning">Not covered {counts.uncovered}</span>
                  <span className="badge-neutral">Excluded (not applicable) {counts.excluded}</span>
                  <span className={counts.unresolved ? 'badge-warning' : 'badge-neutral'}>Applicability unresolved {counts.unresolved}</span>
                </span>
              )}
            </ScoreTile>

            {/* 3. Coverage-Adjusted CRI */}
            <ScoreTile label="3 · Coverage-Adjusted CRI" tone="brand"
              value={scorecard.coverage_adjusted_cri == null ? '—' : `${scorecard.coverage_adjusted_cri}`}
              suffix={scorecard.coverage_adjusted_cri == null ? undefined : '/ 100'} note={adjustedReason(scorecard)}>
              {coverage ? (
                <>
                  <span className="block font-mono text-[11px] text-ink-700">{coverage.formula_version}: {coverage.formula}</span>
                  <span className="block mt-1">
                    Used here: Raw CRI {scorecard.raw_cri} x ({coverage.covered_weight} covered weight / {coverage.applicable_weight}{' '}
                    applicable weight){coverage.ratio != null ? ` = ${scorecard.raw_cri} x ${coverage.ratio}` : ''}.
                    Weights: {coverage.weights_note}
                  </span>
                </>
              ) : 'Raw CRI x evidence coverage, once coverage has been calculated.'}
            </ScoreTile>
          </div>

          {coverage?.applicability_note && (
            <p className="text-xs text-ink-600 -mt-2">
              <strong>Why applicability is unresolved:</strong> {coverage.applicability_note} Unresolved indicators stay in the
              denominator (they are never dropped), so they cannot raise coverage.
            </p>
          )}

          <section className="glass-card p-5 sm:p-6 space-y-3">
            <h2 className="eyebrow">Raw CRI breakdown: the 9 AI-QIF factors</h2>
            <FactorBreakdown pillars={scorecard.pillar_scores || []} rawCri={scorecard.raw_cri} />
          </section>

          {coverage && (
            <section className="glass-card p-5 sm:p-6 space-y-2">
              <h2 className="eyebrow">How coverage was counted</h2>
              <p className="text-xs text-ink-500">
                {coverage.release_label ? `Applicability from published release ${coverage.release_label}. ` : ''}
                {coverage.provisional
                  ? `Provisional: ${coverage.expert_queue?.total ?? 0} item(s) are with the AI-QIF expert, so coverage may still change; the baseline can be decided once they are cleared. `
                  : ''}
                Each row's weight is the one used in the coverage-adjusted CRI.
              </p>
              <CoverageIndicatorTable indicators={coverage.indicators} />
            </section>
          )}
        </>
      )}

      {/* Benchmark Assessment -- the college's, not the sprint's. */}
      <BenchmarkAssessmentSection institutionId={sprint?.institution_id || null} institutionName={sprint?.institution_name || ''} />
    </div>
  );
};

const ScoreTile: React.FC<{
  label: string; value: string; suffix?: string; badge?: string; note?: string; tone: 'brand' | 'accent';
  children: React.ReactNode;
}> = ({ label, value, suffix, badge, note, tone, children }) => (
  <div className="glass-card p-5 sm:p-6 space-y-2">
    <span className={`text-xs font-bold uppercase tracking-wide ${tone === 'brand' ? 'text-brand-800' : 'text-accent'}`}>{label}</span>
    <div className={`text-4xl font-bold tracking-tight tabular-nums ${tone === 'brand' ? 'text-ink-900' : 'text-accent'}`}>
      {value} {suffix && <span className="text-lg font-normal text-ink-500">{suffix}</span>}
    </div>
    {badge && <span className={tone === 'brand' ? 'badge-brand' : 'badge-accent'}>{badge}</span>}
    {note && <p className="text-xs font-semibold text-warning">{note}</p>}
    <p className="text-xs text-ink-600">{children}</p>
  </div>
);
