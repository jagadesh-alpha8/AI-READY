import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, Award, BarChart3, Info, RefreshCw, TrendingUp,
} from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { getScore, recalculateScore } from '../../api/scoring';
import { listSprintGaps } from '../../api/gaps';
import { listRecommendations } from '../../api/recommendations';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { PageHeader, TabStrip } from '../../components/PageHeader';
import type {
  Gap, GapPriority, PillarScore, PillarStatus, Recommendation, Scorecard, Sprint,
} from '../../types';
import { useAccess } from '../../utils/access';

/**
 * CRI & Benchmark Intelligence — the institution's readiness score, the gaps
 * behind it, and the roadmap that closes them.
 *
 * Every figure is REAL: it comes from `apps/scoring`'s deterministic engine,
 * the gap engine, and the recommendation generators. Nothing is seeded.
 *
 * ⚠ On the name: this reads the platform's **pillar-based** CRI — eight
 * pillars scored from confirmed facts. Scores against the approved
 * *benchmark library* (spec §13) live on the Benchmark Assessment page
 * (apps/assessments), which scores a college against a published release.
 */

type Tab = 'score' | 'gaps' | 'roadmap';

const PILLAR_STATUS_BADGE: Record<PillarStatus, string> = {
  not_started: 'badge-neutral',
  at_risk: 'badge-danger',
  developing: 'badge-warning',
  strong: 'badge-success',
};

const PILLAR_STATUS_LABEL: Record<PillarStatus, string> = {
  not_started: 'Not started',
  at_risk: 'At risk',
  developing: 'Developing',
  strong: 'Strong',
};

const PRIORITY_BADGE: Record<GapPriority, string> = {
  blocking: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
  optional: 'badge-neutral',
};

export const CriBenchmarkIntelligence: React.FC = () => {
  const { can } = useAccess();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('score');
  // The selected sprint is shared by every page (context/SelectedSprintContext.tsx).
  const { sprintId: selectedSprintId } = useSelectedSprint();
  const [recalculating, setRecalculating] = useState(false);
  const [actionError, setActionError] = useState('');

  const { data: sprints, loading: sprintsLoading, error: sprintsError, refetch: refetchSprints } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = selectedSprintId;

  const {
    data: scorecard, setData: setScorecard, loading: scoreLoading, error: scoreError, refetch: refetchScore,
  } = useApiResource<Scorecard>(() => getScore(activeSprintId), [activeSprintId], !!activeSprintId);

  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const { data: recommendations } = useApiResource<Recommendation[]>(
    () => listRecommendations(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const openGaps = useMemo(
    () => (gaps ?? []).filter((g) => g.status === 'open' || g.status === 'in_progress'),
    [gaps],
  );

  const visibleRecommendations = useMemo(
    () => (recommendations ?? []).filter((r) => r.status !== 'hidden'),
    [recommendations],
  );

  const handleRecalculate = async () => {
    if (!activeSprintId || recalculating) return;
    setRecalculating(true);
    setActionError('');
    try {
      const { data } = await recalculateScore(activeSprintId);
      setScorecard(data);
    } catch (err) {
      // A baseline-locked sprint refuses recalculation on purpose — the
      // server's own message explains why far better than a generic one.
      setActionError(getErrorMessage(err, 'Could not recalculate the score.'));
    } finally {
      setRecalculating(false);
    }
  };

  if (sprintsLoading) return <LoadingState message="Loading sprints…" />;
  if (sprintsError) return <ErrorState message={sprintsError} onRetry={refetchSprints} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Award}
          title="CRI & Benchmark Intelligence"
          description="The institution's readiness score, the gaps behind it, and the roadmap that closes them."
        />
        <EmptyState
          message="No sprints yet. A readiness score is produced by a discovery sprint — start one to see it here."
          action={can('sprint.manage') ? { label: 'Start a sprint', onClick: () => navigate('/sprint/setup') } : undefined}
        />
      </div>
    );
  }

  if (!activeSprintId) return <SelectSprintPrompt />;

  return (
    <div className="space-y-6">
      <PageHeader
        dataTour="benchmark-intel-header"
        icon={Award}
        title="CRI & Benchmark Intelligence"
        description="The institution's readiness score, the gaps behind it, and the roadmap that closes them."
        actions={
          <button
            type="button"
            onClick={handleRecalculate}
            disabled={recalculating || !activeSprintId}
            className="btn-primary btn-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${recalculating ? 'animate-spin' : ''}`} />
            <span>{recalculating ? 'Recalculating…' : 'Recalculate'}</span>
          </button>
        }
      />


      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      <div data-tour="benchmark-intel-tabs">
        <TabStrip
          tabs={[
            { id: 'score', label: 'Score card', icon: BarChart3 },
            { id: 'gaps', label: 'Gaps', icon: AlertTriangle, count: openGaps.length },
            { id: 'roadmap', label: 'Roadmap', icon: TrendingUp, count: visibleRecommendations.length },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {scoreError && <ErrorState message={scoreError} onRetry={refetchScore} />}
      {scoreLoading && <LoadingState message="Loading the score…" />}

      {!scoreLoading && !scoreError && scorecard && (
        <>
          {tab === 'score' && <ScoreCard scorecard={scorecard} sprintId={activeSprintId} />}
          {tab === 'gaps' && <Gaps gaps={openGaps} sprintId={activeSprintId} />}
          {tab === 'roadmap' && <Roadmap recommendations={visibleRecommendations} sprintId={activeSprintId} />}
        </>
      )}
    </div>
  );
};

// ===== SCORE CARD =====
const ScoreCard: React.FC<{ scorecard: Scorecard; sprintId: string }> = ({ scorecard, sprintId }) => {
  const navigate = useNavigate();
  const m = scorecard.evidence_metrics;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass-card p-6 flex flex-col items-center justify-center text-center" data-tour="benchmark-intel-meter">
          <span className="text-xs font-bold uppercase tracking-wide text-ink-500">
            Campus Readiness Index
          </span>
          <p className="text-5xl font-bold text-brand-800 mt-2 tabular-nums">
            {scorecard.overall_cri.toFixed(1)}
            <span className="text-xl text-ink-500 font-normal"> / 100</span>
          </p>
          <p className="text-sm text-ink-500 mt-2">
            Confidence {(scorecard.overall_confidence * 100).toFixed(0)}%
          </p>
          <span className="badge badge-neutral mt-3" title="The scoring rubric this result was produced by">
            Engine {scorecard.calculation_version}
          </span>
        </div>

        <div className="lg:col-span-2 glass-card p-6 space-y-3">
          <h2 className="eyebrow">What the score was built from</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Figure label="Documents processed" value={m.documents_processed} />
            <Figure label="Facts confirmed" value={m.confirmed_facts} />
            <Figure label="Facts corrected" value={m.corrected_facts} />
            <Figure label="Facts extracted" value={m.total_extracted_facts} />
            <Figure
              label="Gaps unresolved"
              value={m.unresolved_gaps}
              tone={m.unresolved_gaps > 0 ? 'danger' : 'success'}
            />
            <Figure
              label="Blocking gaps"
              value={scorecard.unresolved_blocking_gaps.length}
              tone={scorecard.unresolved_blocking_gaps.length > 0 ? 'danger' : 'success'}
            />
          </div>
          <p className="text-xs text-ink-500">
            Every point traces back to a confirmed fact from an uploaded document. The engine is
            deterministic — the same inputs and the same rubric version always produce the same score.
          </p>
        </div>
      </div>

      {scorecard.unresolved_blocking_gaps.length > 0 && (
        <div className="rounded-lg border border-danger-line bg-danger-bg p-4 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
          <div className="text-sm text-ink-600 min-w-0">
            <p>
              <strong className="text-danger">
                {scorecard.unresolved_blocking_gaps.length} blocking gap
                {scorecard.unresolved_blocking_gaps.length === 1 ? '' : 's'} open.
              </strong>{' '}
              A baseline cannot be approved until these are resolved.
            </p>
          </div>
        </div>
      )}

      <div className="glass-card p-6 space-y-4" data-tour="benchmark-intel-pillars">
        <h2 className="eyebrow">Readiness by pillar</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {scorecard.pillar_scores.map((pillar) => (
            <PillarCard key={pillar.pillar} pillar={pillar} />
          ))}
        </div>
      </div>

      {(scorecard.strengths.length > 0 || scorecard.weaknesses.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {scorecard.strengths.length > 0 && (
            <div className="glass-card p-5 space-y-2">
              <h2 className="eyebrow">Strongest</h2>
              {scorecard.strengths.map((s) => (
                <div key={s.pillar} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-ink-700 min-w-0 truncate">{s.label}</span>
                  <span className="text-sm font-bold text-success tabular-nums shrink-0">
                    {s.raw_score.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {scorecard.weaknesses.length > 0 && (
            <div className="glass-card p-5 space-y-2">
              <h2 className="eyebrow">Weakest</h2>
              {scorecard.weaknesses.map((w) => (
                <div key={w.pillar} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-ink-700 min-w-0 truncate">{w.label}</span>
                  <span className="text-sm font-bold text-danger tabular-nums shrink-0">
                    {w.raw_score.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Honest about what the module's name promises but does not yet do. */}
      <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600 min-w-0">
          <strong className="text-info">Scored on the 9 AI-QIF criteria. </strong>
          The CRI pillars are the criteria of InGage AI-QIF v1.0, weighted out of 1000. Scoring each
          key indicator against its L3 / L2 / L1 levels is done in Benchmark Assessment once experts
          have finished the benchmark library.
        </p>
      </div>

      <button
        type="button"
        onClick={() => navigate(`/sprint/${sprintId}/score`)}
        className="btn-secondary btn-sm"
      >
        <span>Open the full scoring workspace</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

const PillarCard: React.FC<{ pillar: PillarScore }> = ({ pillar }) => (
  <div className="rounded-lg border border-line-200 bg-surface p-4 space-y-2">
    <div className="flex items-start justify-between gap-2">
      <span className="text-sm font-bold text-ink-900 min-w-0">{pillar.label}</span>
      <span className={`badge ${PILLAR_STATUS_BADGE[pillar.status]} shrink-0`}>
        {PILLAR_STATUS_LABEL[pillar.status]}
      </span>
    </div>

    <div className="flex items-baseline gap-2">
      <span className="text-lg font-bold text-brand-800 tabular-nums">
        {pillar.raw_score.toFixed(1)}
      </span>
      <span className="text-xs text-ink-500">/ 100</span>
    </div>

    <div
      className="h-2 rounded-full bg-line-200 overflow-hidden"
      role="progressbar"
      aria-valuenow={Math.round(pillar.raw_score)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`${pillar.label} score`}
    >
      <div
        className="h-full rounded-full bg-brand-500"
        style={{ width: `${Math.min(100, Math.max(0, pillar.raw_score))}%` }}
      />
    </div>

    <div className="flex flex-wrap justify-between gap-x-3 text-[11px] text-ink-500">
      <span>Weight {(pillar.weight * 100).toFixed(0)}%</span>
      <span>{pillar.evidence_count} evidence</span>
      <span>{pillar.gap_count} gaps</span>
      <span>Confidence {(pillar.confidence * 100).toFixed(0)}%</span>
    </div>
  </div>
);

const Figure: React.FC<{
  label: string;
  value: number;
  tone?: 'default' | 'danger' | 'success';
}> = ({ label, value, tone = 'default' }) => (
  <div className="rounded-lg border border-line-200 bg-surface p-3">
    <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    <p
      className={`text-xl font-bold mt-0.5 tabular-nums ${
        tone === 'danger' ? 'text-danger' : tone === 'success' ? 'text-success' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);

// ===== GAPS =====
const Gaps: React.FC<{ gaps: Gap[]; sprintId: string }> = ({ gaps, sprintId }) => {
  const navigate = useNavigate();

  if (gaps.length === 0) {
    return <EmptyState message="No open gaps on this sprint." />;
  }

  // Blocking first — that is the order someone works them in.
  const order: GapPriority[] = ['blocking', 'high', 'medium', 'optional'];
  const sorted = [...gaps].sort(
    (a, b) => order.indexOf(a.priority) - order.indexOf(b.priority),
  );

  // A processed sprint routinely carries hundreds of gaps — this one has 306,
  // which rendered as 306 cards and a page 37,000 pixels tall. Nobody reads
  // that. This is a summary view; the gap dashboard is the work queue, so
  // show the counts and the few that actually block a baseline, then link out.
  const SHOWN = 12;
  const visible = sorted.slice(0, SHOWN);
  const remaining = sorted.length - visible.length;

  const byPriority = order
    .map((p) => ({ priority: p, count: gaps.filter((g) => g.priority === p).length }))
    .filter((row) => row.count > 0);

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-500">
        Generated by the gap engine from the sprint's own facts and documents — five detectors plus
        AI conflict checking. Each carries the score impact of leaving it open.
      </p>

      <div className="glass-card p-5 space-y-3">
        <h2 className="eyebrow">{gaps.length} open gaps</h2>
        <div className="flex flex-wrap gap-2">
          {byPriority.map((row) => (
            <span key={row.priority} className={`badge ${PRIORITY_BADGE[row.priority]}`}>
              {row.count} {row.priority}
            </span>
          ))}
        </div>
      </div>

      {visible.map((gap) => (
        <div key={gap.id} className="glass-card p-5 space-y-2">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-ink-900">{gap.title}</h3>
              <p className="text-xs text-ink-500 mt-0.5">
                {gap.pillar_label || gap.pillar} · {gap.gap_type.replace(/_/g, ' ')}
                {gap.owner_role ? ` · ${gap.owner_role.replace(/_/g, ' ').toLowerCase()}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {gap.score_impact > 0 && (
                <span className="badge badge-warning">−{gap.score_impact.toFixed(1)} pts</span>
              )}
              <span className={`badge ${PRIORITY_BADGE[gap.priority]}`}>{gap.priority}</span>
            </div>
          </div>

          {gap.description && <p className="text-sm text-ink-600">{gap.description}</p>}
        </div>
      ))}

      {remaining > 0 && (
        <p className="text-sm text-ink-500">
          Showing the {SHOWN} highest-priority of {gaps.length}. The other {remaining} are in the gap
          dashboard, where they can be filtered, assigned and resolved.
        </p>
      )}

      <button
        type="button"
        onClick={() => navigate(`/sprint/${sprintId}/gaps`)}
        className="btn-secondary btn-sm"
      >
        <span>Work all {gaps.length} in the gap dashboard</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

// ===== ROADMAP =====
const Roadmap: React.FC<{ recommendations: Recommendation[]; sprintId: string }> = ({
  recommendations, sprintId,
}) => {
  const navigate = useNavigate();

  if (recommendations.length === 0) {
    return (
      <EmptyState
        message="No recommendations generated yet. They are produced from the sprint's gaps and confirmed facts."
        action={{
          label: 'Open recommendations',
          onClick: () => navigate(`/sprint/${sprintId}/recommendations`),
        }}
      />
    );
  }

  const totalLift = recommendations.reduce((sum, r) => sum + (r.expected_cri_lift || 0), 0);

  return (
    <div className="space-y-3">
      <div className="glass-card p-5 flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <h2 className="eyebrow">Expected lift if all are actioned</h2>
          <p className="text-sm text-ink-500 mt-0.5">
            Derived per recommendation from the gap it closes.
          </p>
        </div>
        <span className="badge badge-success shrink-0">
          <TrendingUp className="w-3 h-3" />
          +{totalLift.toFixed(1)} CRI
        </span>
      </div>

      {recommendations.map((rec) => (
        <div key={rec.id} className="glass-card p-5 space-y-2.5">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <h3 className="text-sm font-bold text-ink-900 min-w-0">{rec.title}</h3>
            <div className="flex items-center gap-2 shrink-0">
              {rec.expected_cri_lift > 0 && (
                <span className="badge badge-success">+{rec.expected_cri_lift.toFixed(1)} CRI</span>
              )}
              <span className={`badge ${PRIORITY_BADGE[rec.priority]}`}>{rec.priority}</span>
            </div>
          </div>

          {rec.description && (
            <p className="text-sm text-ink-600 rounded-lg bg-surface border border-line-200 p-3">
              {rec.description}
            </p>
          )}

          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-500">
            {rec.pillar_label && <span>Pillar: <strong className="text-ink-900">{rec.pillar_label}</strong></span>}
            {rec.owner_role && (
              <span>
                Owner: <strong className="text-ink-900">{rec.owner_role.replace(/_/g, ' ').toLowerCase()}</strong>
              </span>
            )}
            {rec.timeline && <span>Timeline: <strong className="text-ink-900">{rec.timeline}</strong></span>}
            <span>Status: <strong className="text-ink-900">{rec.status}</strong></span>
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={() => navigate(`/sprint/${sprintId}/recommendations`)}
        className="btn-secondary btn-sm"
      >
        <span>Edit in the recommendations workspace</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
