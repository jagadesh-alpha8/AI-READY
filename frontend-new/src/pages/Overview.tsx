import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { ErrorState, Loading, Pill } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { achievedTier, bandTier, headlineScore, pillarName, scoreLabel, stageLabel, stateCounts, TIER_BANDS, tierShown } from '../utils/capability';
import { DEMO_MODE } from '../config/env';
import type { PriorityPlan, Result } from '../types/capability';
import { getSprintOverview } from '../services/sprints';
import type { Sprint, SprintOverview } from '../types/api';
import { date, num } from '../utils/format';
import { TIERS, institutionLevel, levelRank, nextTier, tierName } from '../utils/maturity';
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
  // The tier comes with the final AI-READY Score only (23 Nov); a Stage 1 result shows none.
  const capTier = capResult && tierShown(cap.stage) ? achievedTier(capResult) : null;
  const capLevel = capTier ? TIERS.find((t) => t.name === capTier)?.level ?? null : null;
  const level = capLevel ?? (detail.data ? institutionLevel(detail.data.benchmarks) : null);
  const target = nextTier(level);

  // Demo mode: the workspace design's overview (Harsha's preview, 23 Nov), built from the capability result.
  if (DEMO_MODE && capResult) {
    return <WorkspaceOverview result={capResult} stage={cap.stage} plan={cap.plan?.priority_plan || null}
      requirements={cap.assessment?.records?.length || 0} />;
  }

  const actions = nextActions(o);
  // Without an audit CRI, the hero shows the AI-READY Score (Stage 1 result or final) instead of an empty CRI.
  const capScore = !score && capResult ? headlineScore(capResult) : null;

  return (
    <>
      <div className="roadmap-hero">
        <div className="roadmap-copy">
          <span className="eyebrow">Institution transformation map</span>
          <h1>Your route from capable<br />to AI-leading.</h1>
          <p>
            {sprint.institution_name} is {level ? <>at <b>{tierName(level)}</b></> : <>not yet <b>verified</b> at a maturity level</>}.
            {' '}{score ? interpretation(score.overall_cri, score.weaknesses.map((w) => w.label))
              : capResult ? `${stageLabel(cap.stage)}: ${scoreLabel(capResult)}.` : 'No CRI has been calculated for this sprint yet.'}
          </p>
          <div className="button-row">
            <Link className="primary-action" to={pathOf('plan')}>Build the {target?.name || 'next'} plan</Link>
            <Link className="secondary-button" to={pathOf('cri')}>Explain our position</Link>
          </div>
        </div>
        <div className="readiness-stamp" role="group" aria-label="Readiness score">
          <span className="stamp-label">{capScore != null ? (cap.stage === 'final' ? 'Final AI-READY Score' : 'Stage 1 result') : approved ? 'Approved baseline' : 'Live CRI'}</span>
          <strong className={score || capScore != null ? '' : 'empty'}>{score ? num(score.overall_cri) : capScore != null ? capScore.toFixed(1) : '—'}</strong>
          <span className="stamp-tier">{capScore == null ? tierName(level) : !tierShown(cap.stage) ? 'Tier after follow-ups' : level ? tierName(level) : 'No tier yet'}</span>
          <small>{score?.calculated_at ? date(score.calculated_at) : capScore != null ? 'out of 100' : 'Not scored yet'}</small>
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
            <dt>Capability score</dt><dd>{capResult ? (
              <>
                <Pill tone={tierShown(cap.stage) ? 'good' : 'neutral'} label={stageLabel(cap.stage)} />{' '}
                {scoreLabel(capResult)} · {capResult.condition_decision_coverage}% conditions decided
              </>
            ) : 'No completed assessment'}</dd>
            <dt>Evidence confidence</dt><dd>{score ? `${num(score.overall_confidence)}%` : '—'}</dd>
            <dt>Coverage-adjusted CRI</dt><dd>{score?.coverage_adjusted_cri != null ? num(score.coverage_adjusted_cri, 1) : '—'}</dd>
            <dt>Critical blockers</dt><dd>{o.gaps.blocking_open} blocking gap{o.gaps.blocking_open === 1 ? '' : 's'} open</dd>
            <dt>Facts verified</dt><dd>{o.facts.confirmed + o.facts.corrected} of {o.facts.total}</dd>
            <dt>Target level</dt><dd>{target ? `${target.name} (${target.level})` : 'Platinum achieved'}</dd>
          </dl>
        </section>
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


/** The overview in the workspace design: where the institution stands, the one next step, the nine areas, what to
 * focus on, and the tier bands. Everything comes from the latest completed capability run. */
function WorkspaceOverview({ result, stage, plan, requirements }: {
  result: Result; stage: string | null; plan: PriorityPlan | null; requirements: number;
}) {
  const final = stage === 'final';
  const score = headlineScore(result) ?? 0;
  const band = bandTier(score);
  const pillars = [...(result.documented?.pillars || [])];
  const ranked = [...pillars].sort((a, b) => b.score - a.score);
  const strongest = ranked.filter((p) => p.score > 0).slice(0, 2).map((p) => pillarName(p.code));
  const weakest = [...ranked].reverse().slice(0, 2).map((p) => pillarName(p.code));
  const counts = stateCounts(result);
  const total = counts.met + counts.not_met + counts.unknown + counts.conflicting;
  const headline = score >= 60 ? 'A strong, evidenced position.' : score >= 35 ? 'A foundation to build on.' : 'An early start, with clear next steps.';
  const summary = strongest.length
    ? `The documents show most in ${strongest.join(' and ')}. ${weakest.join(' and ')} ${weakest.length > 1 ? 'are' : 'is'} where evidence is thinnest.`
    : 'The documents show little AI-specific practice yet. The areas below show where to start.';
  const ring = `conic-gradient(var(--brand) 0deg ${Math.max(0, Math.min(100, score)) * 3.6}deg, #edf1e9 ${Math.max(0, Math.min(100, score)) * 3.6}deg 360deg)`;
  const focus = (plan?.actions || []).slice(0, 3);

  return (
    <>
      <div className="ws-heading">
        <div>
          <span className="eyebrow">Campus workspace</span>
          <h1>Your AI readiness, in focus.</h1>
          <p>A clear view of your baseline, priorities and the road ahead.</p>
        </div>
        <Link className="secondary-button" to={pathOf('reports')}>View report</Link>
      </div>

      <div className="ws-grid">
        <section className="ws-standing" aria-label="Current readiness">
          <div className="ws-standing-top">
            <h2>Current readiness</h2>
            <span className={`ws-tag ${final ? '' : 'amber'}`}>{final ? 'Final AI-READY Score' : 'Stage 1 · Document review'}</span>
          </div>
          <div className="ws-standing-body">
            <div className="ws-ring" style={{ background: ring }}>
              <div className="ws-ring-inner">
                <b>{num(score, 1)}</b>
                <small>AI-READY score / 100</small>
                <span>{final ? (band.current ? `${band.current} tier` : 'No tier yet') : 'Before the follow-up questions'}</span>
              </div>
            </div>
            <div className="ws-copy">
              <h3>{headline}</h3>
              <p>{summary}</p>
              <Link className="ws-text-link" to={pathOf('cri')}>Explore your result →</Link>
            </div>
          </div>
          <div className="ws-meta">
            <div><small>Requirements shown in full</small><strong>{counts.met} of {total}</strong><div className="ws-meter"><i style={{ width: `${total ? (counts.met / total) * 100 : 0}%` }} /></div></div>
            <div><small>Readiness areas</small><strong>{pillars.length || 9} assessed</strong></div>
            <div><small>Requirements</small><strong>{requirements} reviewed</strong></div>
          </div>
        </section>

        <section className="ws-next" aria-label="Your next best step">
          <span className="eyebrow">Your next best step</span>
          {final ? (
            <>
              <h2>Plan the road to {band.next || 'the next level'}.</h2>
              <p>Your Final AI-READY Score is published. The pathway shows which requirements move it most.</p>
              <Link className="ws-olive" to={pathOf('pathway')}>See the pathway</Link>
              <div className="ws-mini">
                <div><b>{band.current || 'None yet'}</b><small>Tier now</small></div>
                {band.next && <div><b>{num(band.pointsToNext, 1)}</b><small>Points to {band.next}</small></div>}
              </div>
            </>
          ) : (
            <>
              <h2>Complete your assessment picture.</h2>
              <p>Answer the follow-up questions and send any documents we missed. Only documents change the score; the final score and tier come when you finish.</p>
              <Link className="ws-olive" to={pathOf('questionnaire')}>Continue questionnaire</Link>
              <div className="ws-mini">
                <div><b>{num(score, 1)}</b><small>Stage 1 result</small></div>
                {plan && <div><b>{num(plan.projected_score, 1)}</b><small>With the priority actions</small></div>}
              </div>
            </>
          )}
        </section>
      </div>

      <div className="ws-grid">
        <section className="ws-surface">
          <div className="ws-section-head">
            <div><h2>Your readiness across nine areas</h2><p>Out of 100 in each area: what the documents show</p></div>
            <Link className="ws-text-link" style={{ marginTop: 0 }} to={pathOf('cri')}>View detail →</Link>
          </div>
          <div className="ws-areas">
            {pillars.map((p) => (
              <div className="ws-area-row" key={p.code}>
                <span>{pillarName(p.code)}</span>
                <div className="ws-meter"><i style={{ width: `${Math.max(0, Math.min(100, p.score))}%` }} /></div>
                <b>{num(p.score, 0)}</b>
              </div>
            ))}
          </div>
        </section>
        <section className="ws-surface">
          <div className="ws-section-head"><div><h2>Focus on what matters next</h2><p>The requirements that would add most</p></div></div>
          {focus.length === 0 ? <p className="muted">Nothing within reach changes the score yet.</p> : (
            <div className="ws-focus">
              {focus.map((a, i) => (
                <div className="ws-focus-item" key={a.indicator}>
                  <span className="ws-focus-mark">{i + 1}</span>
                  <div>
                    <h3>{a.name}</h3>
                    <p>{pillarName(a.indicator.split('.')[0])} · up to +{num(a.score_gain, 1)} points</p>
                  </div>
                </div>
              ))}
              <Link className="ws-text-link" to={pathOf('pathway')}>See the pathway →</Link>
            </div>
          )}
        </section>
      </div>

      <section className="ws-surface">
        <div className="ws-section-head">
          <div><h2>A clear destination for your campus</h2><p>Tiers are score bands on the Final AI-READY Score, provisional until calibrated across colleges</p></div>
        </div>
        <div className="ws-areas">
          <div className="ws-area-row"><span><b style={{ textAlign: 'left' }}>Today</b></span><div className="ws-meter"><i style={{ width: `${Math.min(100, score)}%` }} /></div><b>{num(score, 1)}</b></div>
          {TIER_BANDS.map(([name, at]) => (
            <div className="ws-area-row" key={name}>
              <span>{name}{final && band.current === name ? ' · reached' : !final ? '' : score < at && band.next === name ? ' · next' : ''}</span>
              <div className="ws-meter"><i style={{ width: `${at}%`, background: final && score >= at ? 'var(--brand)' : '#d4dfbd' }} /></div>
              <b>{at}</b>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
