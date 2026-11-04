import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Bar, CheckItem, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Stat } from '../components/ui';
import { CapabilityEvidence, CapabilityRunControl } from '../components/Capability';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getScoringConfig, recalculateScore } from '../services/scoring';
import { getSprintOverview } from '../services/sprints';
import type { PillarConfig, Scorecard, Sprint, SprintOverview } from '../types/api';
import { errorMessage } from '../utils/errors';
import { dateTime, num } from '../utils/format';

export function Assessment() {
  return <RequireSprint>{(sprint) => <AssessmentBody sprint={sprint} />}</RequireSprint>;
}

/** Runs the deterministic CRI engine over verified evidence (POST /sprints/{id}/score): each run is a new, frozen record. */
function AssessmentBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const overview = useResource<SprintOverview>(() => getSprintOverview(sprint.id), sprint.id);
  const rubric = useResource<PillarConfig[]>(getScoringConfig, 'rubric');
  const { detail: cycle } = useCycle(sprint.institution_id);
  const cap = useCapability(sprint.id);
  const [score, setScore] = useState<Scorecard | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  if (overview.loading) return <Loading label="Loading assessment inputs…" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />;
  const o = overview.data!;
  const s = score || o.scorecard;
  const active = (rubric.data || []).filter((p) => p.is_active);
  const criteria = active.reduce((n, p) => n + p.criteria.filter((c) => c.is_active).length, 0);
  const cov = s?.evidence_coverage || {};
  const verified = o.facts.confirmed + o.facts.corrected;

  const run = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await recalculateScore(sprint.id);
      setScore(res.data);
      setMsg({ tone: 'success', text: `Assessment recorded: CRI ${num(res.data.overall_cri, 1)} at ${dateTime(res.data.calculated_at)}.` });
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  const runButton = can('sprint.manage') && (
    <button className="primary-action" disabled={busy || verified === 0} onClick={() => void run()}>{busy ? 'Recalculating…' : 'Recalculate audit CRI'}</button>
  );

  return (
    <>
      <PageHeading page="assessment" actions={runButton} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <CapabilityRunControl sprintId={sprint.id} cap={cap} />
      {!!cap.error && <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} title="Could not load the capability assessment" />}
      {cap.run.data?.assessment && <CapabilityEvidence run={cap.run.data} />}
      <h2 className="section-title">Audit CRI (rubric over verified facts)</h2>
      <div className="stat-grid">
        <Stat label="Pillars" value={rubric.data ? active.length : '—'} note={`${criteria} criteria in the rubric`} />
        <Stat label="Indicators" value={cov.applicable_count ?? '—'} note={cov.excluded_count ? `${cov.excluded_count} not applicable` : 'Applicable AI-QIF indicators'} />
        <Stat label="Evidence coverage" value={cov.ratio != null ? `${num(cov.ratio * 100)}%` : '—'} note={cov.covered_count != null ? `${cov.covered_count} of ${cov.applicable_count} covered` : 'Not yet calculated'} />
        <Stat label="Verified evidence" value={verified} note={`${o.facts.extracted} still unreviewed`} />
      </div>
      <div className="content-grid">
        <Panel title="Readiness by pillar" sub={s ? `Calculation ${s.calculation_version} · ${dateTime(s.calculated_at)}` : 'Not yet assessed'}>
          {!s ? <Empty title="No assessment yet">Approve evidence in Evidence review, then run the assessment.</Empty> : (
            <div className="bar-list">{s.pillar_scores.map((p) => <Bar key={p.pillar} label={p.label} value={p.raw_score} />)}</div>
          )}
        </Panel>
        <Panel title="Assessment controls">
          <div className="check-list">
            <CheckItem done={!!(cov.release_label || cycle.data?.release_label)}>Benchmark release {cov.release_label || cycle.data?.release_label || 'not selected'}</CheckItem>
            <CheckItem done={!cov.unresolved_applicability_count}>Applicability rules confirmed{cov.unresolved_applicability_count ? ` (${cov.unresolved_applicability_count} unresolved)` : ''}</CheckItem>
            <CheckItem done={verified > 0}>{verified} evidence items verified</CheckItem>
            <CheckItem done={!cov.mappings_awaiting_review}>{cov.mappings_awaiting_review ? `${cov.mappings_awaiting_review} indicator tags await review` : 'Indicator tags reviewed'}</CheckItem>
            <CheckItem done mark="i">Unknown evidence stays unknown: it is never scored as a pass or a fail</CheckItem>
            <CheckItem done mark="i">Scoring inputs are frozen with each run</CheckItem>
          </div>
          {runButton && <div className="panel-foot">{runButton}</div>}
          {verified === 0 && <p className="muted">Nothing is verified yet, so there is nothing to assess.</p>}
        </Panel>
      </div>
    </>
  );
}
