import { CyclePicker } from '../components/CyclePicker';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, Empty, ErrorState, Loading, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import type { CycleBenchmarkRow, Sprint } from '../types/api';
import { KIND_LABEL } from '../utils/benchmark';
import { achievedTier, capabilityTone, tierLabel } from '../utils/capability';
import { num } from '../utils/format';
import { ROUTES, TIERS, institutionLevel, levelRank, meetsLevel, nextTier, tierName } from '../utils/maturity';

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

  return (
    <>
      <PageHeading page="pathway" actions={<CyclePicker cycles={cycles} value={cycleId} onChange={choose} />} />
      {!!cap.error && <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} title="Could not load the capability assessment" />}

      {result ? (
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
        <Dummy code="R-04" title="Progression timeline" note="Shown from the foundation plan once a capability recommendation exists; until then these are the handoff's typical periods.">
          <div className="route-timeline">
            {ROUTES.map((r) => (
              <div key={r.key} className={`route-row ${r.key} ${r.key === 'progressive' ? 'recommended' : ''}`}>
                <span>{r.name}</span><div className="route-track"><i /></div><b>{r.period}</b>
              </div>
            ))}
          </div>
        </Dummy>
      )}
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
