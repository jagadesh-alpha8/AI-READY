import { CyclePicker } from '../components/CyclePicker';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import type { CycleBenchmarkRow, Sprint } from '../types/api';
import { KIND_LABEL } from '../utils/benchmark';
import { achievedTier, capabilityTone, tierLabel } from '../utils/capability';
import type { PriorityPlan } from '../types/capability';
import { num } from '../utils/format';
import { TIERS, institutionLevel, levelRank, meetsLevel, nextTier, tierName } from '../utils/maturity';

export function Pathway() {
  return <RequireSprint>{(sprint) => <PathwayBody sprint={sprint} />}</RequireSprint>;
}

/**
 * Achieved, next and future level. Two real sources: the capability run (tier eligibility, pathways with their
 * requirements, foundation-plan routes) and the benchmark assessment cycle (per-benchmark level vs target).
 */
function PathwayBody({ sprint }: { sprint: Sprint }) {
  const cap = useCapability(sprint.id);
  const { cycles, cyclesState, cycleId, choose, detail } = useCycle(sprint.institution_id);

  if (cap.loading && cyclesState.loading) return <Loading label="Loading the pathway…" />;
  const result = cap.assessment?.result;
  const priority = cap.plan?.priority_plan || null;

  return (
    <>
      <PageHeading page="pathway" actions={<CyclePicker cycles={cycles} value={cycleId} onChange={choose} />} />
      {!!cap.error && <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} title="Could not load the capability assessment" />}

      {priority ? <PriorityPathway plan={priority} /> : result ? (
        <Panel title="Silver to Platinum eligibility" sub={`From the latest capability assessment · achieved: ${achievedTier(result) || 'none demonstrated yet'}`}>
          {result.badge_policy === 'not_calibrated' ? <p className="muted">Silver, Gold and Platinum standards are being calibrated; no badge is awarded yet.</p> : (
            <div className="tier-grid">
              {result.tiers.map((t) => {
                const p = cap.assessment!.pathways.find((x) => x.target === t.name);
                return (
                  <article key={t.name} className={`tier-card ${t.name.toLowerCase()}`}>
                    <span>{t.eligibility === 'demonstrated' ? 'Achieved stage' : 'Stage requirements'}</span>
                    <h2>{t.name}</h2>
                    <Pill tone={capabilityTone(t.eligibility)} label={tierLabel(t.eligibility)} />
                    <ul>
                      <li>Threshold {t.threshold ?? '—'} · pillar floor {t.pillar_floor ?? '—'}</li>
                      <li>{Object.keys(t.gates).length} indicator gates</li>
                      {p && <li>{p.already_demonstrated ? 'Already demonstrated' : `${p.requirement_ids.length} requirements remaining`}</li>}
                      {p && !p.already_demonstrated && <li>Projected minimum {num(p.projected_minimum, 1)} if met</li>}
                    </ul>
                    {p?.note && <p className="muted">{p.note}</p>}
                  </article>
                );
              })}
            </div>
          )}
          <p className="muted">Pathways are sufficient scenarios, not guaranteed score increases: evidence must be reassessed before a tier changes.</p>
        </Panel>
      ) : !cap.loading && (
        <Empty title="No completed capability assessment" action={<PageLink to="assessment">Go to the assessment</PageLink>}>
          Tier eligibility and pathways appear after the first completed evidence-based assessment.
        </Empty>
      )}

      {cycleId && detail.data && <BenchmarkTiers all={detail.data.benchmarks} />}
      {cycleId && !!detail.error && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}

      {cap.foundation ? (
        <Panel title="Progression routes" sub={cap.foundation.destination}>
          <div className="route-timeline">
            {cap.foundation.routes.map((r) => (
              <div key={r.name} className="route-row">
                <span>{r.name}</span>
                <div className="route-track"><i style={{ width: `${Math.min(100, 30 + r.batches.length * 15)}%` }} /></div>
                <b>{r.indicative_duration}</b>
              </div>
            ))}
          </div>
          <p className="muted">{cap.foundation.baseline.message} Durations are illustrative.</p>
        </Panel>
      ) : (
        <p className="muted">The progression timeline comes from the foundation plan once grounded advice exists for a completed assessment.</p>
      )}
    </>
  );
}

/** Provisional score bands on the part-credit score and the priority actions that move it (priority_plan). */
function PriorityPathway({ plan }: { plan: PriorityPlan }) {
  const t = plan.tier;
  return (
    <>
      <Panel title="Requirements pathway" sub={`Score ${num(plan.score, 1)} · ${t.current ? `${t.current} band` : 'below the first band'}${t.next ? ` · ${num(t.points_to_next, 1)} points to ${t.next}` : ''}`}>
        <div className="tier-grid">
          {t.thresholds.map((b) => {
            const reached = plan.score >= b.score;
            const projected = !reached && plan.projected_score >= b.score;
            return (
              <article key={b.name} className={`tier-card ${b.name.toLowerCase()}`}>
                <span>{reached ? 'Reached' : b.name === t.next ? 'Next band' : 'Later band'}</span>
                <h2>{b.name}</h2>
                <strong>{b.score} points</strong>
                <ul>
                  <li>{reached ? 'At or above this score' : `${num(b.score - plan.score, 1)} points to go`}</li>
                  {projected && <li>Reached if the priority actions are shown</li>}
                </ul>
              </article>
            );
          })}
        </div>
        <p className="muted">{t.note} Target {plan.target ?? '—'} · projected {num(plan.projected_score, 1)}{plan.projected_tier ? ` (${plan.projected_tier})` : ''}{plan.reaches_target ? ' · reaches the target' : ''}.</p>
      </Panel>
      {plan.follow_up && plan.follow_up.points > 0 && (
        <Panel title={`Answer the follow-up questions: up to ${num(plan.follow_up.points, 1)} points`}
          sub="Credit already in your documents, held until your answers show how far the evidence goes"
          actions={<PageLink to="questionnaire" className="primary-action">Answer questions</PageLink>}>
          <Table columns={['Key indicator', 'Requirements', 'Points']}>
            {plan.follow_up.indicators.map((i) => (
              <tr key={i.indicator}>
                <td><b>{i.indicator}</b><small className="cell-sub">{i.name}</small></td>
                <td>{i.requirements}</td>
                <td>up to {num(i.points, 2)}</td>
              </tr>
            ))}
          </Table>
          <p className="muted">{plan.follow_up.note}</p>
        </Panel>
      )}
      <Panel title="Priority actions" sub="Per key indicator: each requirement's gap and the parts not yet shown">
        {!plan.actions.length ? <p className="muted">No priority actions: nothing within reach changes the score.</p> : (
          <Table columns={['Key indicator', 'Requirement', 'Gap', 'Missing parts', 'Gain']}>
            {plan.actions.flatMap((a) => a.conditions.map((c, i) => (
              <tr key={`${a.indicator}:${c.condition_id}`}>
                <td>{i === 0 ? <><b>{a.indicator}</b><small className="cell-sub">{a.name}</small></> : ''}</td>
                <td>{c.requirement}<small className="cell-sub">{c.condition_id} · {c.level}</small></td>
                <td><Pill tone={c.gap === 'complete' ? 'warn' : c.gap === 'establish' ? 'bad' : 'neutral'} label={c.gap === 'establish' ? 'Establish' : c.gap === 'complete' ? 'Complete' : c.gap} /></td>
                <td>{c.missing_parts.length ? c.missing_parts.join('; ') : '—'}</td>
                <td>{i === 0 ? `+${num(a.score_gain, 1)}` : ''}</td>
              </tr>
            )))}
          </Table>
        )}
        {plan.strengths.length > 0 && <p className="muted">{plan.strengths.length} requirement(s) already shown and built on.</p>}
        <p className="muted">{plan.note}</p>
      </Panel>
    </>
  );
}

function BenchmarkTiers({ all }: { all: CycleBenchmarkRow[] }) {
  const rows = all.filter((b) => b.included !== false);
  const level = institutionLevel(all);
  const next = nextTier(level);
  const remainingFor = (lvl: string) => rows.filter((b) => !meetsLevel(b.assessment?.current_level, lvl));
  return (
    <>
      <h2 className="section-title">Benchmark assessment by level</h2>
      <div className="tier-grid">
        {TIERS.map((t) => {
          const achieved = levelRank(level) >= levelRank(t.level);
          const remaining = remainingFor(t.level);
          return (
            <article key={t.tier} className={`tier-card ${t.tier}`}>
              <span>{achieved ? 'Achieved stage' : next?.tier === t.tier ? 'Recommended target' : 'Future aspiration'}</span>
              <h2>{t.name}</h2>
              <strong>Level {t.level}</strong>
              <ul>
                <li>{rows.length - remaining.length} of {rows.length} benchmarks satisfied</li>
                <li>{remaining.filter((b) => !b.assessment?.current_level).length} not scored yet</li>
              </ul>
            </article>
          );
        })}
      </div>
      {next && remainingFor(next.level).length > 0 && (
        <Table columns={['Requirement', 'Source class', 'Current', 'Needed', 'Evidence accepted']}>
          {remainingFor(next.level).map((b) => (
            <tr key={b.benchmark_code}>
              <td><strong>{b.title}</strong><small className="cell-sub">{b.benchmark_code}</small></td>
              <td>{KIND_LABEL[b.kind] || b.kind}</td>
              <td>{b.assessment?.current_level ? tierName(b.assessment.current_level) : 'Unknown'}</td>
              <td>{next.name} ({next.level})</td>
              <td>{b.accepted} of {b.evidence}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
