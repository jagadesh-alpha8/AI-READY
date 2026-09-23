import React, { useMemo, useState } from 'react';
import {
  AlertTriangle, Award, BarChart3, FileText, RefreshCw, TrendingUp, Zap,
} from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { PageHeader, TabStrip } from '../../components/PageHeader';
import { seedAssessmentSnapshot, seedGaps, seedTransformationMappings } from '../../data/benchmark/seed';
import { MATURITY_LABELS, calculateCRI } from '../../data/benchmark/scoring';
import type { GapResult } from '../../data/benchmark/types';

/**
 * Ported from the InGage prototype's CRI & Benchmark Intelligence page.
 *
 * ⚠ This is a SECOND scoring model, parallel to the platform's own CRI engine
 * (8 pillars scored from confirmed facts). This one scores 8 domains from
 * benchmark maturity levels. The two will not agree, and which is
 * authoritative is an open decision — see the note rendered on the score tab.
 */

type Tab = 'summary' | 'gaps' | 'roadmap';

export const CriBenchmarkIntelligence: React.FC = () => {
  const [tab, setTab] = useState<Tab>('summary');
  const snapshot = seedAssessmentSnapshot;
  const [gaps] = useState<GapResult[]>(seedGaps);

  // Recalculating does NOT overwrite the published snapshot. The prototype's
  // version did, and the result was startling: its seed declares an overall
  // CRI of 43.5 with eight populated domain scores, but ships only three
  // benchmark assessments — which the engine scores at 0.0. One press turned
  // 43.5 into 0 with no explanation.
  //
  // Both numbers are shown instead, because the discrepancy is the useful
  // finding: the seeded figure cannot be reproduced from the assessments it
  // travels with.
  const [recomputed, setRecomputed] = useState<ReturnType<typeof calculateCRI> | null>(null);

  const result = useMemo(() => calculateCRI(snapshot.benchmarkAssessments), [snapshot]);
  const assessedCount = snapshot.benchmarkAssessments.length;

  const recalculate = () => setRecomputed(result);

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="The benchmark library and the assessment behind this score are sample data." />

      <PageHeader
        icon={Award}
        title="CRI & Benchmark Intelligence"
        description="The institution scored against the published benchmark library — the index, the gaps behind it, and the roadmap that closes them."
        actions={
          <button type="button" onClick={recalculate} className="btn-primary btn-sm">
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Recalculate</span>
          </button>
        }
      />

      <TabStrip
        tabs={[
          { id: 'summary', label: 'Score card', icon: BarChart3 },
          { id: 'gaps', label: 'Gap analysis', icon: AlertTriangle, count: gaps.length },
          { id: 'roadmap', label: 'Roadmap', icon: TrendingUp, count: seedTransformationMappings.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'summary' && (
        <ScoreCard
          published={snapshot.overallCRI}
          domainScores={snapshot.domainScores}
          recomputed={recomputed}
          assessedCount={assessedCount}
        />
      )}
      {tab === 'gaps' && <GapAnalysis gaps={gaps} />}
      {tab === 'roadmap' && <Roadmap />}
    </div>
  );
};

// ===== SCORE CARD =====
const ScoreCard: React.FC<{
  published: number;
  domainScores: typeof seedAssessmentSnapshot.domainScores;
  recomputed: ReturnType<typeof calculateCRI> | null;
  assessedCount: number;
}> = ({ published, domainScores, recomputed, assessedCount }) => (
  <div className="space-y-4">
    <div className="rounded-lg border border-warning-line bg-warning-bg p-4 flex items-start gap-3">
      <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
      <p className="text-sm text-ink-600 min-w-0">
        <strong className="text-warning">Two scoring models. </strong>
        This index is computed from benchmark maturity levels. The platform's Live CRI Preview
        computes a different index from confirmed facts against pillar criteria. They will not
        agree — which one is authoritative has not been decided.
      </p>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="glass-card p-6 flex flex-col items-center justify-center text-center">
        <span className="text-xs font-bold uppercase tracking-wide text-ink-500">
          Campus Readiness Index
        </span>
        <p className="text-5xl font-bold text-brand-800 mt-2 tabular-nums">
          {published.toFixed(1)}
          <span className="text-xl text-ink-500 font-normal"> / 100</span>
        </p>
        <span className="badge badge-brand mt-3">Published snapshot</span>
      </div>

      <div className="lg:col-span-2 glass-card p-6 space-y-3">
        <h2 className="eyebrow">Recalculate to see the engine run</h2>
        {recomputed ? (
          <>
            {/* Derived, not hardcoded. The prototype displayed fixed
                "−15 / −5" figures that were never computed; these come from
                the engine. */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Figure label="Before penalties" value={recomputed.baseCRI.toFixed(1)} />
              <Figure
                label="Gate penalties"
                value={recomputed.totalPenalties > 0 ? `−${recomputed.totalPenalties.toFixed(1)}` : '0.0'}
                tone={recomputed.totalPenalties > 0 ? 'danger' : 'default'}
              />
              <Figure label="Recomputed index" value={recomputed.overallCRI.toFixed(1)} tone="brand" />
            </div>
            <p className="text-xs text-ink-500 flex items-start gap-1.5">
              <Zap className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              A hard gate deducts its full penalty when a critical benchmark is unassessed; a soft
              gate deducts half when one sits at the foundational level.
            </p>
          </>
        ) : (
          <p className="text-sm text-ink-500">
            Press <strong className="text-ink-900">Recalculate</strong> to run the deterministic
            engine over the assessments in this snapshot and compare the result with the published
            figure.
          </p>
        )}
      </div>
    </div>

    {recomputed && Math.abs(recomputed.overallCRI - published) > 0.05 && (
      <div className="rounded-lg border border-danger-line bg-danger-bg p-4 flex items-start gap-3">
        <AlertTriangle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
        <div className="text-sm text-ink-600 min-w-0 space-y-1.5">
          <p>
            <strong className="text-danger">
              The published figure cannot be reproduced from this snapshot.
            </strong>{' '}
            Published {published.toFixed(1)}; recomputed {recomputed.overallCRI.toFixed(1)}.
          </p>
          <p>
            The sample data carries eight populated domain scores but only{' '}
            <strong className="text-ink-900">{assessedCount} benchmark assessments</strong>. Every
            other domain therefore scores zero while still carrying its weight, and the gates deduct
            a further {recomputed.totalPenalties.toFixed(1)} points.
          </p>
          <p>
            This is a defect in the prototype's seed data, not in the engine — the prototype's own
            recalculate button had the same effect, silently. Surfacing it rather than overwriting
            the published number, because a score that changes by 40 points on a button press is
            exactly the thing a client would notice.
          </p>
        </div>
      </div>
    )}

    <div className="glass-card p-6 space-y-4">
      <h2 className="eyebrow">Domain readiness — published snapshot</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {domainScores.map((domain) => (
          <div key={domain.domainCode} className="rounded-lg border border-line-200 bg-surface p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-bold text-ink-900 min-w-0 truncate">{domain.domainLabel}</span>
              <span className="text-sm font-bold text-brand-800 tabular-nums shrink-0">
                {domain.normalizedScore.toFixed(1)}
              </span>
            </div>
            <div
              className="h-2 rounded-full bg-line-200 overflow-hidden"
              role="progressbar"
              aria-valuenow={Math.round(domain.normalizedScore)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${domain.domainLabel} score`}
            >
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${Math.min(100, Math.max(0, domain.normalizedScore))}%` }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-ink-500">
              <span>Weight {(domain.weight * 100).toFixed(0)}%</span>
              <span>
                {domain.applicableBenchmarkCount === 0
                  ? 'No benchmarks assessed'
                  : `${domain.applicableBenchmarkCount} assessed`}
              </span>
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-ink-500">
        A domain with no benchmarks assessed scores zero and still carries its weight — which is why
        the headline index sits low while individual domains do not.
      </p>
    </div>
  </div>
);

const Figure: React.FC<{ label: string; value: string; tone?: 'default' | 'danger' | 'brand' }> = ({
  label, value, tone = 'default',
}) => (
  <div className="rounded-lg border border-line-200 bg-surface p-3">
    <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    <p
      className={`text-xl font-bold mt-0.5 tabular-nums ${
        tone === 'danger' ? 'text-danger' : tone === 'brand' ? 'text-brand-800' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);

// ===== GAP ANALYSIS =====
const GapAnalysis: React.FC<{ gaps: GapResult[] }> = ({ gaps }) => (
  <div className="space-y-3">
    <p className="text-sm text-ink-500">
      Every applicable benchmark sitting below its target becomes a gap, generated deterministically
      from current level versus target level.
    </p>

    {gaps.map((gap) => (
      <div key={gap.id} className="glass-card p-5 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-mono text-xs font-bold text-brand-800 bg-brand-500/10 px-2 py-1 rounded">
              {gap.benchmarkCode}
            </span>
            <span className="text-sm font-bold text-ink-900">{gap.benchmarkTitle}</span>
          </div>
          <span
            className={`badge ${
              gap.severity === 'CRITICAL' ? 'badge-danger' : gap.severity === 'HIGH' ? 'badge-warning' : 'badge-info'
            }`}
          >
            {gap.severity}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded-lg bg-surface border border-line-200 p-3">
          <Cell label="Current" value={gap.currentLevel ? MATURITY_LABELS[gap.currentLevel] : 'Not assessed'} />
          <Cell label="Target" value={MATURITY_LABELS[gap.targetLevel]} tone="success" />
          <Cell label="Evidence needed" value={`${gap.evidenceGaps.length} item${gap.evidenceGaps.length === 1 ? '' : 's'}`} />
          <Cell label="CRI at stake" value={`${gap.criImpact.toFixed(1)} pts`} tone="danger" />
        </div>

        {gap.evidenceGaps.length > 0 && (
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500 mb-1.5">
              Missing evidence
            </p>
            <ul className="space-y-1">
              {gap.evidenceGaps.map((item) => (
                <li key={item} className="text-sm text-ink-600 flex items-start gap-2">
                  <FileText className="w-3.5 h-3.5 text-warning shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {gap.recommendedActions.length > 0 && (
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500 mb-1.5">
              Recommended actions
            </p>
            <ul className="space-y-1">
              {gap.recommendedActions.map((item) => (
                <li key={item} className="text-sm text-ink-600 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0 mt-1.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    ))}
  </div>
);

const Cell: React.FC<{ label: string; value: string; tone?: 'default' | 'success' | 'danger' }> = ({
  label, value, tone = 'default',
}) => (
  <div className="min-w-0">
    <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    <p
      className={`text-sm font-bold truncate ${
        tone === 'success' ? 'text-success' : tone === 'danger' ? 'text-danger' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);

// ===== ROADMAP =====
const Roadmap: React.FC = () => (
  <div className="space-y-3">
    <p className="text-sm text-ink-500">
      Each initiative is tied to the gap it closes, with the CRI movement it is expected to produce.
    </p>

    {seedTransformationMappings.map((item) => (
      <div key={item.id} className="glass-card p-5 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <span className="font-mono text-[11px] font-bold text-ink-500">{item.initiativeCode}</span>
            <h3 className="text-sm font-bold text-ink-900">{item.title}</h3>
          </div>
          <span className="badge badge-success shrink-0">
            <TrendingUp className="w-3 h-3" />
            +{item.estimatedCriLift.toFixed(1)} CRI
          </span>
        </div>

        <p className="text-sm text-ink-600 rounded-lg bg-surface border border-line-200 p-3">
          {item.description}
        </p>

        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-500">
          <span>Timeline: <strong className="text-ink-900">{item.timeline}</strong></span>
          <span>Owner: <strong className="text-ink-900">{item.owner}</strong></span>
          <span>Priority: <strong className="text-ink-900">{item.priority}</strong></span>
          <span>Status: <strong className="text-ink-900">{item.status.replace(/_/g, ' ')}</strong></span>
        </div>
      </div>
    ))}
  </div>
);
