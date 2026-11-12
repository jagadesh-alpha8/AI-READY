import { useState } from 'react';
import { AuditRecommendationTable } from '../components/AuditRecommendations';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { generatePlan, getPlan } from '../services/assessments';
import { generateRecommendations, listRecommendations } from '../services/recommendations';
import type { ImprovementPlan, Recommendation, Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { humanize } from '../utils/format';
import { ROUTES } from '../utils/maturity';

export function TransformationPlan() {
  return <RequireSprint>{(sprint) => <PlanBody sprint={sprint} />}</RequireSprint>;
}

function PlanBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const { cycleId, detail } = useCycle(sprint.institution_id);
  const plan = useResource<ImprovementPlan>(() => getPlan(cycleId), `plan:${cycleId}`, !!cycleId);
  const recs = useResource<Recommendation[]>(() => listRecommendations(sprint.id), sprint.id);
  const { foundation } = useCapability(sprint.id);
  const [route, setRoute] = useState<string>('');
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const run = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    setMsg(null);
    try { await fn(); setMsg({ tone: 'success', text: ok }); } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(''); }
  };
  const finalized = detail.data?.status === 'finalized';
  const initiatives = (plan.data?.gaps || []).flatMap((g) => g.initiatives.map((i) => ({ gap: g, initiative: i })));

  return (
    <>
      <PageHeading page="plan" />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {foundation ? (
        <Panel title="Transformation routes" sub={`${foundation.destination} · from the capability foundation plan`}>
          <div className="pace-grid" role="radiogroup" aria-label="Transformation pace">
            {foundation.routes.map((r) => (
              <article key={r.name} className={`pace-card ${route === r.name ? 'recommended' : ''}`}>
                <span className="eyebrow">Route</span>
                <strong>{r.name}</strong>
                <p>{r.assumptions.join(' ')}</p>
                <div className="pace-stats"><div><span>Indicative</span><b>{r.indicative_duration}</b></div><div><span>Goals</span><b>{r.outcomes.length}</b></div></div>
                <button role="radio" aria-checked={route === r.name} className={route === r.name ? 'primary-action' : 'secondary-button'} onClick={() => setRoute(r.name)}>
                  {route === r.name ? 'Selected for review' : 'Explore route'}
                </button>
              </article>
            ))}
          </div>
          <p className="muted">{foundation.baseline.message} Same goals on every route; only sequencing changes.</p>
        </Panel>
      ) : (
        <Dummy code="D-03" title="Transformation routes" note="Real routes come from the capability foundation plan once a recommendation is generated for a completed assessment. Until then these are the handoff's sample routes.">
          <div className="pace-grid">
            {ROUTES.map((r) => (
              <article key={r.key} className={`pace-card ${r.key === 'progressive' ? 'recommended' : ''}`}>
                <span className="eyebrow">{r.eyebrow}</span>
                <strong>{r.name}</strong>
                <p>{r.text}</p>
                <div className="pace-stats"><div><span>Next level</span><b>{r.period}</b></div><div><span>Effort</span><b>{r.effort}</b></div></div>
              </article>
            ))}
          </div>
        </Dummy>
      )}
      <Dummy code="R-05" title="Route approval" note="The backend has no programme approval model yet: the selected route is not saved. The route changes time and resourcing, never the evidence a level requires.">
        <div className="button-row"><span className="muted">Selected: {route || 'none'}</span><button className="primary-action" disabled>Request sponsor approval</button></div>
      </Dummy>

      {foundation && foundation.goals.length > 0 && (
        <Panel title="Foundation goals" sub="From the capability assessment: what to establish, then what to improve">
          <Table columns={['Goal', 'Suggested lead', 'Conditions', 'Depends on', 'Status']}>
            {foundation.goals.map((g) => (
              <tr key={g.id}>
                <td><strong>{g.title}</strong><small className="cell-sub">{g.improvement_condition}</small></td>
                <td>{g.suggested_role || '—'}</td>
                <td>{g.target_condition_ids.length}</td>
                <td>{g.depends_on.map((id) => foundation.goals.find((x) => x.id === id)?.title || id).join('; ') || '—'}</td>
                <td><Pill status={g.status === 'verify_before_implementation' ? 'needs_review' : 'open'} label={humanize(g.status)} /></td>
              </tr>
            ))}
          </Table>
        </Panel>
      )}

      <Panel title="Transformation goals" sub="Generated from the benchmark assessment: gap → initiative → tasks"
        actions={can('assessments.manage') && cycleId && (
          <button className="primary-action" disabled={!finalized || !!busy} title={finalized ? '' : 'Only a finalized assessment cycle can generate a plan'}
            onClick={() => void run('plan', async () => { plan.setData((await generatePlan(cycleId)).data); }, 'Plan generated from the finalized assessment.')}>
            {busy === 'plan' ? 'Generating…' : plan.data?.has_plan ? 'Regenerate plan' : 'Generate plan'}
          </button>
        )}>
        {!cycleId ? <p className="muted">No benchmark assessment cycle yet.</p> : plan.loading ? <Loading /> : plan.error ? <ErrorState error={plan.error} onRetry={() => void plan.refetch()} /> :
          initiatives.length === 0 ? <Empty title="No plan yet">{finalized ? 'Generate the plan from the finalized assessment.' : 'The plan is generated once the assessment cycle is finalized.'}</Empty> : (
            <Table columns={['Transformation goal', 'Benefit', 'Tasks', 'Owner', 'Requirement', 'Status']}>
              {initiatives.map(({ gap, initiative }) => (
                <tr key={initiative.id}>
                  <td><strong>{initiative.title}</strong><small className="cell-sub">{initiative.description}</small></td>
                  <td>{initiative.expected_outcome || '—'}</td>
                  <td>{initiative.tasks.length}</td>
                  <td>{initiative.owner || 'Unassigned'}</td>
                  <td>{gap.benchmark_code}<small className="cell-sub">{gap.type_label} · {gap.severity_label}</small></td>
                  <td><Pill status={initiative.status} label={initiative.status_label} /></td>
                </tr>
              ))}
            </Table>
          )}
      </Panel>

      <Panel title="Audit recommendations" sub="From open high-priority gaps, low-confidence facts and weak pillars"
        actions={can('recommendations.generate') && (
          <button className="secondary-button" disabled={!!busy} onClick={() => void run('recs', async () => { await generateRecommendations(sprint.id); await recs.refetch(); }, 'Recommendations refreshed.')}>
            {busy === 'recs' ? 'Generating…' : 'Generate recommendations'}
          </button>
        )}>
        <AuditRecommendationTable recs={recs} />
      </Panel>
    </>
  );
}
