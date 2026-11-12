import { useState } from 'react';
import { AuditRecommendationTable } from '../components/AuditRecommendations';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { generatePlan, getPlan } from '../services/assessments';
import { generateRecommendations, listRecommendations } from '../services/recommendations';
import type { ImprovementPlan, Recommendation, Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { humanize } from '../utils/format';

export function TransformationPlan() {
  return <RequireSprint>{(sprint) => <PlanBody sprint={sprint} />}</RequireSprint>;
}

function PlanBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const { cycleId, detail } = useCycle(sprint.institution_id);
  const plan = useResource<ImprovementPlan>(() => getPlan(cycleId), `plan:${cycleId}`, !!cycleId);
  const recs = useResource<Recommendation[]>(() => listRecommendations(sprint.id), sprint.id);
  const { foundation } = useCapability(sprint.id);
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
          <div className="pace-grid">
            {foundation.routes.map((r) => (
              <article key={r.name} className="pace-card">
                <span className="eyebrow">Route</span>
                <strong>{r.name}</strong>
                <p>{r.assumptions.join(' ')}</p>
                <div className="pace-stats"><div><span>Indicative</span><b>{r.indicative_duration}</b></div><div><span>Goals</span><b>{r.outcomes.length}</b></div></div>
              </article>
            ))}
          </div>
          <p className="muted">{foundation.baseline.message} Same goals on every route; only sequencing changes.</p>
        </Panel>
      ) : (
        <Panel title="Transformation routes" sub="From the capability foundation plan">
          <p className="muted">Routes appear once grounded advice is written for a completed assessment (Recommended actions).</p>
        </Panel>
      )}

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
