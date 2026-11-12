import { CapabilityStanding } from '../components/Capability';
import { RequireSprint } from '../components/RequireSprint';
import { ScoreHistory } from '../components/ScoreHistory';
import { CheckItem, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { achievedTier } from '../utils/capability';
import { useResource } from '../hooks/useResource';
import { getSprintOverview } from '../services/sprints';
import type { CycleBenchmarkRow, Sprint, SprintOverview } from '../types/api';
import { dateTime, num } from '../utils/format';
import { institutionLevel, meetsLevel, nextTier, tierName } from '../utils/maturity';

const APPROVED = new Set(['baseline_approved', 'report_ready', 'completed']);

export function CriStanding() {
  return <RequireSprint>{(sprint) => <CriBody sprint={sprint} />}</RequireSprint>;
}

/** Average of one assessment component over the scored benchmarks, labelled as such (never a hidden composite). */
function mean(rows: CycleBenchmarkRow[], key: 'compliance_score' | 'maturity_score' | 'evidence_confidence_score' | 'outcome_score'): { value: number | null; n: number } {
  const vals = rows.map((r) => r.assessment?.[key]).filter((v): v is string => v !== null && v !== undefined && v !== '').map(Number).filter(Number.isFinite);
  return { value: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null, n: vals.length };
}

function CriBody({ sprint }: { sprint: Sprint }) {
  const overview = useResource<SprintOverview>(() => getSprintOverview(sprint.id), sprint.id);
  const { detail } = useCycle(sprint.institution_id);
  const cap = useCapability(sprint.id);

  if (overview.loading) return <Loading label="Loading the CRI…" />;
  // The evidence-based capability standing (A1 capability runs) comes first; the audit CRI follows it.
  const capability = cap.loading ? <Loading label="Loading the capability standing…" />
    : cap.error ? <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} title="Could not load the capability assessment" />
      : cap.run.data?.assessment ? (
        <>
          <h2 className="section-title">Evidence-based capability standing{achievedTier(cap.run.data.assessment.result) ? ` · ${achievedTier(cap.run.data.assessment.result)} achieved` : ''}</h2>
          <CapabilityStanding result={cap.run.data.assessment.result} run={cap.run.data} />
        </>
      ) : <Notice tone="info">No completed capability assessment yet. Start one on the AI readiness assessment screen.</Notice>;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />;
  const s = overview.data!.scorecard;
  if (!s) {
    return (
      <>
        <PageHeading page="cri" />
        {capability}
        <Empty title="No audit CRI yet" action={<PageLink to="assessment" className="primary-action">Go to the assessment</PageLink>}>
          No CRI has been calculated for this sprint. An unscored institution is shown as unverified, not as failing.
        </Empty>
        <ScoreHistory sprint={sprint} onReassessed={() => void overview.refetch()} />
      </>
    );
  }
  const rows = (detail.data?.benchmarks || []).filter((b) => b.included !== false);
  const level = detail.data ? institutionLevel(detail.data.benchmarks) : null;
  const next = nextTier(level);
  // Benchmarks scored below the next tier's level (unscored ones are counted separately, never as failures).
  const scored = rows.filter((b) => b.assessment?.current_level);
  const blocking = next ? scored.filter((b) => !meetsLevel(b.assessment!.current_level, next.level)) : [];
  const unscored = rows.length - scored.length;
  const comp = mean(rows, 'compliance_score');
  const mat = mean(rows, 'maturity_score');
  const ev = mean(rows, 'evidence_confidence_score');
  const out = mean(rows, 'outcome_score');
  const cri = s.overall_cri;

  return (
    <>
      <PageHeading page="cri" />
      {capability}
      <h2 className="section-title">Audit CRI</h2>
      <div className="stat-grid">
        <Stat label="Composite CRI" value={`${num(cri)} / 100`} note={APPROVED.has(sprint.status) ? 'Approved baseline' : 'Live, not yet approved'} />
        <Stat label="Coverage-adjusted CRI" value={s.coverage_adjusted_cri != null ? num(s.coverage_adjusted_cri, 1) : '—'} note="CRI × evidence coverage" />
        <Stat label="Evidence confidence" value={`${num(s.overall_confidence)}%`} note={`${s.evidence_metrics.confirmed_facts + s.evidence_metrics.corrected_facts} verified facts`} />
        <Stat label="Maturity level" value={tierName(level)} note={level ? `Benchmark level ${level}` : 'No scored benchmark assessment'} />
      </div>
      <div className="content-grid">
        <Panel title="Current AI readiness" sub={`Calculation ${s.calculation_version} · ${dateTime(s.calculated_at)}`} actions={<Pill status={APPROVED.has(sprint.status) ? 'approved' : 'pending'} label={APPROVED.has(sprint.status) ? 'Evidence-based, approved' : 'Awaiting baseline approval'} />}>
          <div className="score-visual">
            <div className="score-ring" style={{ background: `conic-gradient(var(--brand) 0 ${cri}%, var(--ring-track) ${cri}% 100%)` }}>
              <div><strong>{num(cri)}</strong><span>of 100 CRI</span></div>
            </div>
            <div className="score-copy">
              <span className="tier-pill"><i /> {level ? `${tierName(level)} achieved` : 'Level not yet verified'}</span>
              <h3>{next ? `Next: ${next.name}` : 'Platinum achieved'}</h3>
              <p>
                {s.strengths.length > 0 && <>Strongest: {s.strengths.slice(0, 2).map((x) => `${x.label} (${num(x.raw_score)})`).join(', ')}. </>}
                {s.weaknesses.length > 0 && <>The constraints most likely to hold the institution back are {s.weaknesses.slice(0, 2).map((x) => `${x.label} (${num(x.raw_score)})`).join(' and ')}.</>}
              </p>
              <PageLink to="gaps">See what blocks the next level</PageLink>
            </div>
          </div>
        </Panel>
        <Panel title="What this means">
          <div className="check-list">
            <CheckItem done={!!level}>{level ? `${tierName(level)} requirements achieved` : 'No maturity level verified yet'}</CheckItem>
            <CheckItem done={blocking.length === 0} mark={blocking.length ? '!' : undefined}>
              {!detail.data ? 'No benchmark assessment cycle yet'
                : next ? `${blocking.length} benchmark(s) below ${next.name}${unscored ? `, ${unscored} not scored yet` : ''}` : 'Every scored benchmark is at Platinum'}
            </CheckItem>
            <CheckItem done={s.unresolved_blocking_gaps.length === 0} mark={s.unresolved_blocking_gaps.length ? '!' : undefined}>
              {s.unresolved_blocking_gaps.length} blocking evidence gap(s) open
            </CheckItem>
            <CheckItem done={false} mark="→">What can change the result: verified evidence for open gaps, then a new assessment run</CheckItem>
          </div>
        </Panel>
      </div>
      <Panel title="Component scores" sub={rows.length ? 'Averages across the scored benchmarks of the latest assessment cycle; each benchmark keeps its own scores' : 'Shown once a benchmark assessment cycle is scored'}>
        <div className="stat-grid">
          <Stat label="Compliance" value={comp.value === null ? '—' : num(comp.value, 1)} note={`${comp.n} scored`} />
          <Stat label="Capability maturity" value={mat.value === null ? '—' : num(mat.value, 1)} note={`${mat.n} scored`} />
          <Stat label="Evidence confidence" value={ev.value === null ? '—' : num(ev.value, 1)} note={`${ev.n} scored`} />
          <Stat label="Outcome" value={out.value === null ? '—' : num(out.value, 1)} note={`${out.n} scored`} />
        </div>
      </Panel>
      <ScoreHistory sprint={sprint} onReassessed={() => void overview.refetch()} />
    </>
  );
}
