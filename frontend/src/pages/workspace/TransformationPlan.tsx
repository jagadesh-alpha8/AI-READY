import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, ChevronDown, ChevronUp, RefreshCw, Target, TrendingUp,
} from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { getScore } from '../../api/scoring';
import { generateRecommendations, listRecommendations } from '../../api/recommendations';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { PageHeader } from '../../components/PageHeader';
import type { Recommendation, RecommendationPriority, Scorecard, Sprint } from '../../types';

/**
 * Transformation Plan — the audit's recommendations sequenced into dated
 * horizons, with the score movement each one is expected to produce.
 *
 * Real data throughout: the recommendations come from `apps/recommendations`'
 * three generators, and the current score from the CRI engine. The phases are
 * not invented here either — the generators already stamp each recommendation
 * with a timeline derived from its priority, so this page groups by that
 * rather than inventing a schedule of its own.
 */

/** The horizons the generators actually emit, in order. Grouping by the
 * stored string keeps this page honest: if the generator's mapping changes,
 * the plan follows rather than silently disagreeing with it. */
const HORIZONS: { timeline: string; name: string; note: string }[] = [
  { timeline: '0-30 days', name: 'Immediate', note: 'Blocking items. A baseline cannot be approved while these are open.' },
  { timeline: '30-60 days', name: 'Near term', note: 'High priority — the largest score movement sits here.' },
  { timeline: '60-90 days', name: 'Consolidate', note: 'Medium priority, once the urgent work is underway.' },
  { timeline: '90+ days', name: 'Longer term', note: 'Optional and structural improvements.' },
];

const PRIORITY_BADGE: Record<RecommendationPriority, string> = {
  blocking: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
  optional: 'badge-neutral',
};

const PRIORITY_DOT: Record<RecommendationPriority, string> = {
  blocking: 'bg-danger-solid',
  high: 'bg-warning',
  medium: 'bg-info',
  optional: 'bg-ink-500/40',
};

export const TransformationPlan: React.FC = () => {
  const navigate = useNavigate();
  const [sprintId, setSprintId] = useState('');
  const [expanded, setExpanded] = useState<string | null>(HORIZONS[0].timeline);
  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState('');

  const { data: sprints, loading: sprintsLoading, error: sprintsError, refetch: refetchSprints } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = sprintId || sprints?.[0]?.id || '';

  const {
    data: recommendations, setData: setRecommendations,
    loading: recsLoading, error: recsError, refetch: refetchRecs,
  } = useApiResource<Recommendation[]>(
    () => listRecommendations(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const { data: scorecard } = useApiResource<Scorecard>(
    () => getScore(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const visible = useMemo(
    () => (recommendations ?? []).filter((r) => r.status !== 'hidden'),
    [recommendations],
  );

  const phases = useMemo(
    () => HORIZONS.map((h) => {
      const items = visible.filter((r) => r.timeline === h.timeline);
      return {
        ...h,
        items,
        lift: items.reduce((sum, r) => sum + (r.expected_cri_lift || 0), 0),
        done: items.filter((r) => r.status === 'completed').length,
      };
    }).filter((p) => p.items.length > 0),
    [visible],
  );

  // Anything the generators stamped with a timeline this page does not know
  // about. Shown rather than dropped — silently losing an initiative is worse
  // than an unfamiliar heading.
  const unscheduled = useMemo(
    () => visible.filter((r) => !HORIZONS.some((h) => h.timeline === r.timeline)),
    [visible],
  );

  const totalLift = visible.reduce((sum, r) => sum + (r.expected_cri_lift || 0), 0);
  const currentCri = scorecard?.overall_cri ?? null;
  const projected = currentCri === null ? null : Math.min(100, currentCri + totalLift);

  const handleGenerate = async () => {
    if (!activeSprintId || generating) return;
    setGenerating(true);
    setActionError('');
    try {
      const { data } = await generateRecommendations(activeSprintId);
      setRecommendations(data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Could not generate recommendations.'));
    } finally {
      setGenerating(false);
    }
  };

  if (sprintsLoading) return <LoadingState message="Loading sprints…" />;
  if (sprintsError) return <ErrorState message={sprintsError} onRetry={refetchSprints} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Target}
          title="Transformation Plan"
          description="The audit's findings, sequenced into dated horizons with an owner and an expected score movement."
        />
        <EmptyState
          message="No sprints yet. A plan is generated from a completed discovery sprint."
          action={{ label: 'Start a sprint', onClick: () => navigate('/sprint/setup') }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Target}
        title="Transformation Plan"
        description="The audit's findings, sequenced into dated horizons with an owner and an expected score movement."
        actions={
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating || !activeSprintId}
            className="btn-primary btn-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} />
            <span>{generating ? 'Generating…' : 'Regenerate'}</span>
          </button>
        }
      />

      <div className="glass-card p-4">
        <label className="label" htmlFor="plan-sprint">Sprint</label>
        <select
          id="plan-sprint"
          value={activeSprintId}
          onChange={(e) => setSprintId(e.target.value)}
          className="input"
        >
          {sprints.map((s) => (
            <option key={s.id} value={s.id}>
              {s.institution_name || s.name || 'Institution'} · {s.sprint_code} ({s.status.replace(/_/g, ' ')})
            </option>
          ))}
        </select>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {recsError && <ErrorState message={recsError} onRetry={refetchRecs} />}
      {recsLoading && <LoadingState message="Loading the plan…" />}

      {!recsLoading && !recsError && visible.length === 0 && (
        <EmptyState
          message="No recommendations yet. They are generated from the sprint's gaps and confirmed facts — run the audit's scoring step first, then generate."
          action={{ label: 'Generate recommendations', onClick: handleGenerate }}
        />
      )}

      {!recsLoading && !recsError && visible.length > 0 && (
        <>
          <div className="glass-card p-6 bg-gradient-to-br from-brand-50 to-card space-y-3">
            <h2 className="text-lg font-bold text-ink-900">Where this plan takes the score</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Figure
                label="CRI today"
                value={currentCri === null ? '—' : currentCri.toFixed(1)}
              />
              <Figure label="Expected lift" value={`+${totalLift.toFixed(1)}`} tone="success" />
              <Figure
                label="If all are actioned"
                value={projected === null ? '—' : projected.toFixed(1)}
                tone="brand"
              />
            </div>
            <p className="text-xs text-ink-500">
              {visible.length} initiatives across {phases.length} horizons. Each lift is the score
              impact of the gap that initiative closes — they are estimates from the scoring engine,
              not a guarantee, and they assume no new gaps appear.
            </p>
          </div>

          <div className="space-y-3">
            {phases.map((phase, index) => {
              const isOpen = expanded === phase.timeline;
              return (
                <div key={phase.timeline} className="glass-card overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : phase.timeline)}
                    aria-expanded={isOpen}
                    className="w-full flex items-center gap-4 p-4 text-left hover:bg-surface transition-colors"
                  >
                    <span className="w-8 h-8 rounded-full bg-brand-500 text-on-brand text-sm font-bold flex items-center justify-center shrink-0">
                      {index + 1}
                    </span>

                    <span className="flex-1 min-w-0">
                      <span className="block text-sm font-bold text-ink-900">
                        {phase.name} · {phase.timeline}
                      </span>
                      <span className="block text-xs text-ink-500">
                        {phase.items.length} initiative{phase.items.length === 1 ? '' : 's'}
                        {phase.done > 0 ? ` · ${phase.done} completed` : ''}
                      </span>
                    </span>

                    {phase.lift > 0 && (
                      <span className="badge badge-success shrink-0">
                        <TrendingUp className="w-3 h-3" />
                        +{phase.lift.toFixed(1)}
                      </span>
                    )}

                    {isOpen
                      ? <ChevronUp className="w-4 h-4 text-ink-500 shrink-0" />
                      : <ChevronDown className="w-4 h-4 text-ink-500 shrink-0" />}
                  </button>

                  {isOpen && (
                    <div className="border-t border-line-200 p-4 space-y-2">
                      <p className="text-xs text-ink-500">{phase.note}</p>
                      {phase.items.map((item) => (
                        <Initiative key={item.id} item={item} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {unscheduled.length > 0 && (
              <div className="glass-card p-4 space-y-2">
                <h3 className="eyebrow">Unscheduled</h3>
                <p className="text-xs text-ink-500">
                  These carry a timeline this view does not recognise, so they are listed rather
                  than dropped.
                </p>
                {unscheduled.map((item) => <Initiative key={item.id} item={item} />)}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => navigate(`/sprint/${activeSprintId}/recommendations`)}
            className="btn-secondary btn-sm"
          >
            <span>Edit these in the recommendations workspace</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </>
      )}
    </div>
  );
};

const Initiative: React.FC<{ item: Recommendation }> = ({ item }) => (
  <div className="flex items-start gap-3 p-3 rounded-lg bg-surface border border-line-200">
    <span
      className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${PRIORITY_DOT[item.priority]}`}
      aria-hidden="true"
    />
    <div className="flex-1 min-w-0">
      <p
        className={`text-sm font-medium ${
          item.status === 'completed' ? 'text-ink-500 line-through' : 'text-ink-900'
        }`}
      >
        {item.title}
      </p>
      {item.description && <p className="text-xs text-ink-600 mt-0.5">{item.description}</p>}
      <p className="text-xs text-ink-500 mt-1">
        {[
          item.pillar_label,
          item.owner_role ? item.owner_role.replace(/_/g, ' ').toLowerCase() : '',
          item.support_offering,
        ].filter(Boolean).join(' · ')}
      </p>
    </div>
    <div className="flex items-center gap-2 shrink-0">
      {item.expected_cri_lift > 0 && (
        <span className="badge badge-success">+{item.expected_cri_lift.toFixed(1)}</span>
      )}
      <span className={`badge ${PRIORITY_BADGE[item.priority]}`}>{item.priority}</span>
    </div>
  </div>
);

const Figure: React.FC<{
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'brand';
}> = ({ label, value, tone = 'default' }) => (
  <div className="rounded-lg border border-line-200 bg-card p-3">
    <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    <p
      className={`text-2xl font-bold mt-0.5 tabular-nums ${
        tone === 'success' ? 'text-success' : tone === 'brand' ? 'text-brand-800' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);
