import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { ErrorState, Loading, Pill } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { achievedTier, scoreLabel } from '../utils/capability';
import { getSprintOverview } from '../services/sprints';
import type { Sprint, SprintOverview } from '../types/api';
import { date, num } from '../utils/format';
import { ROUTES, TIERS, institutionLevel, levelRank, nextTier, tierName } from '../utils/maturity';
import { pathOf } from '../navigation';
import type { PageKey } from '../utils/access';

const APPROVED = new Set(['baseline_approved', 'report_ready', 'completed']);

export function Overview() {
  return <RequireSprint>{(sprint) => <OverviewBody sprint={sprint} />}</RequireSprint>;
}

function OverviewBody({ sprint }: { sprint: Sprint }) {
  const overview = useResource<SprintOverview>(() => getSprintOverview(sprint.id), sprint.id);
  const { detail } = useCycle(sprint.institution_id);
  const cap = useCapability(sprint.id);

  if (overview.loading && !overview.data) return <Loading label="Loading the executive overview…" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />;
  const o = overview.data!;
  const score = o.scorecard;
  const approved = APPROVED.has(sprint.status);
  // The evidence-based capability run decides the tier when it has one; otherwise the benchmark assessment cycle.
  const capResult = cap.assessment?.result || null;
  const capTier = capResult ? achievedTier(capResult) : null;
  const capLevel = capTier ? TIERS.find((t) => t.name === capTier)?.level ?? null : null;
  const level = capLevel ?? (detail.data ? institutionLevel(detail.data.benchmarks) : null);
  const target = nextTier(level);

  const actions = nextActions(o);

  return (
    <>
      <div className="roadmap-hero">
        <div className="roadmap-copy">
          <span className="eyebrow">Institution transformation map</span>
          <h1>Your route from capable<br />to AI-leading.</h1>
          <p>
            {sprint.institution_name} is {level ? <>at <b>{tierName(level)}</b></> : <>not yet <b>verified</b> at a maturity level</>}.
            {' '}{score ? interpretation(score.overall_cri, score.weaknesses.map((w) => w.label)) : 'No CRI has been calculated for this sprint yet.'}
          </p>
          <div className="button-row">
            <Link className="primary-action" to={pathOf('plan')}>Build the {target?.name || 'next'} plan</Link>
            <Link className="secondary-button" to={pathOf('cri')}>Explain our position</Link>
          </div>
        </div>
        <div className="readiness-stamp" role="group" aria-label="Readiness score">
          <span className="stamp-label">{approved ? 'Approved baseline' : 'Live CRI'}</span>
          <strong className={score ? '' : 'empty'}>{score ? num(score.overall_cri) : '—'}</strong>
          <span className="stamp-tier">{tierName(level)}</span>
          <small>{score?.calculated_at ? date(score.calculated_at) : 'Not scored yet'}</small>
        </div>
      </div>

      <div className="maturity-landscape">
        <div className="landscape-line" aria-hidden="true"><i style={{ width: `${(levelRank(level) / 3) * 100}%` }} /></div>
        {TIERS.map((t, i) => {
          const achieved = levelRank(level) >= levelRank(t.level);
          const isTarget = target?.tier === t.tier;
          return (
            <article key={t.tier} className={`milestone ${achieved ? 'current' : isTarget ? 'target' : 'future'}`}>
              <span className="milestone-index">{String(i + 1).padStart(2, '0')}</span>
              <div>
                <small>{achieved ? 'ACHIEVED' : isTarget ? 'NEXT DESTINATION' : 'FUTURE ASPIRATION'}</small>
                <h2>{t.name}</h2>
                <strong>Benchmark level {t.level}</strong>
                <p>{t.summary}</p>
                {isTarget && <Link to={pathOf('pathway')} className="link-button">See requirements →</Link>}
              </div>
            </article>
          );
        })}
      </div>

      <div className="overview-grid">
        <section className="panel">
          <div className="panel-head"><div><h2>Next three actions</h2><p>From the sprint's live counts</p></div><Pill status={sprint.status} /></div>
          {actions.length === 0 ? <p className="muted">Nothing is waiting. Continue with the transformation plan.</p> : (
            <div className="sequence-list">
              {actions.slice(0, 3).map((a, i) => (
                <Link key={a.page} className={`sequence-card ${i === 0 ? 'live' : ''}`} to={pathOf(a.page)}>
                  <span className="sequence-number">{String(i + 1).padStart(2, '0')}</span>
                  <span><b>{a.title}</b><small>{a.text}</small></span>
                  <em>Open →</em>
                </Link>
              ))}
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Position</h2><p>Evidence and blockers</p></div></div>
          <dl className="kv">
            <dt>Capability score</dt><dd>{capResult ? `${scoreLabel(capResult)} · ${capResult.condition_decision_coverage}% conditions decided` : 'No completed assessment'}</dd>
            <dt>Evidence confidence</dt><dd>{score ? `${num(score.overall_confidence)}%` : '—'}</dd>
            <dt>Coverage-adjusted CRI</dt><dd>{score?.coverage_adjusted_cri != null ? num(score.coverage_adjusted_cri, 1) : '—'}</dd>
            <dt>Critical blockers</dt><dd>{o.gaps.blocking_open} blocking gap{o.gaps.blocking_open === 1 ? '' : 's'} open</dd>
            <dt>Facts verified</dt><dd>{o.facts.confirmed + o.facts.corrected} of {o.facts.total}</dd>
            <dt>Target level</dt><dd>{target ? `${target.name} (${target.level})` : 'Platinum achieved'}</dd>
          </dl>
        </section>
      </div>

      <div className="route-options">
        <div><span className="eyebrow">Choose the pace</span><h2>Three routes. One verified destination.</h2></div>
        {ROUTES.map((r) => (
          <Link key={r.key} className={`route-card ${r.key === 'progressive' ? 'recommended' : ''}`} to={pathOf('plan')}>
            <span>{r.name}</span><strong>{r.period}</strong><small>{r.effort} effort</small><i aria-hidden="true">→</i>
          </Link>
        ))}
      </div>
    </>
  );
}

function interpretation(cri: number, weak: string[]): string {
  const band = cri >= 75 ? 'strong' : cri >= 50 ? 'developing' : 'early-stage';
  const constraint = weak.length ? ` The weakest pillars are ${weak.slice(0, 2).join(' and ')}.` : '';
  return `The live CRI of ${cri.toFixed(0)} shows ${band} readiness.${constraint}`;
}

function nextActions(o: SprintOverview): { page: PageKey; title: string; text: string }[] {
  const out: { page: PageKey; title: string; text: string }[] = [];
  const toProcess = o.documents.uploaded + o.documents.failed;
  if (o.documents.total === 0) out.push({ page: 'uploads', title: 'Upload evidence', text: 'No documents yet: start the evidence pack' });
  else if (toProcess > 0) out.push({ page: 'uploads', title: 'Process documents', text: `${toProcess} document(s) waiting for extraction` });
  if (o.facts.extracted > 0) out.push({ page: 'review', title: 'Evidence review', text: `${o.facts.extracted} extracted fact(s) need a decision` });
  if (o.gaps.blocking_open > 0) out.push({ page: 'gaps', title: 'Resolve blockers', text: `${o.gaps.blocking_open} blocking gap(s) hold the assessment` });
  if (!o.scorecard && o.facts.confirmed + o.facts.corrected > 0) out.push({ page: 'assessment', title: 'Run the assessment', text: 'Verified evidence is ready to score' });
  if (o.scorecard) out.push({ page: 'cri', title: 'Leadership review', text: 'Understand the CRI, the next-level gap and the pathway' });
  return out;
}
