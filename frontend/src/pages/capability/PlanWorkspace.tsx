import React, { useRef, useState } from 'react';
import * as api from '../../api/capability';
import type { PlanEvaluation, PlanComparison, PlanScore, Result, Run } from '../../api/capability';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import { active, attempt, scoreLabel } from './presentation';
import { useCapabilityRead } from './CapabilityWorkspace';

const areaNames: Record<string, string> = {
  'AIQIF-C1': 'Leadership and investment', 'AIQIF-C2': 'Responsible and safe AI',
  'AIQIF-C3': 'Curriculum and teaching', 'AIQIF-C4': 'Faculty and staff',
  'AIQIF-C5': 'Student skills and careers', 'AIQIF-C6': 'Technology and data',
  'AIQIF-C7': 'Research and innovation', 'AIQIF-C8': 'Services and partnerships',
  'AIQIF-C9': 'Measurement and improvement',
};
export function PlanWorkspace({ sprint, run }: { sprint: string; run: Run }) {
  const { can } = useAccess();
  const [page, setPage] = useState(1);
  const history = useCapabilityRead(() => api.listPlanEvaluations(sprint, run.id, page), [sprint, run.id, page]);
  const [selected, setSelected] = useState('');
  const id = selected || history.data?.results[0]?.id;
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<{ signature: string; key: string } | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    pending.current = attempt(pending.current, text, () => crypto.randomUUID());
    try {
      const response = await api.startPlanEvaluation(sprint, run.id, text, pending.current.key);
      pending.current = null; setSelected(response.data.id); history.reload();
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  }
  return <section className="glass-card p-5 space-y-4" aria-label="Evaluate your institution’s plan">
    <h2 className="text-xl font-bold">Evaluate your institution’s plan</h2>
    <p>See what your proposed actions could establish, what is missing, and how to improve the plan.
      Both versions use this assessment’s scope and method. Your actual assessment stays unchanged.</p>
    {run.assessment?.result.exact_score === null && <p className="text-sm">Your baseline has unresolved evidence. We can review the plan, but a precise score increase may not be established.</p>}
    {can('sprint.manage') && <form onSubmit={submit} className="space-y-3">
      <label className="block">Your proposed plan<textarea className="input block w-full min-h-36" maxLength={30000} required value={text} onChange={(e) => setText(e.target.value)} /></label>
      <p className="text-sm">Include actions, beneficiaries and timing where known. Budget is optional; if stated, suggestions aim to work within roughly that envelope and explain uncosted effort.</p>
      <button className="btn-primary" disabled={busy || !text.trim() || !history.data?.enabled || history.data.results.some(active)}>
        {busy ? 'Starting…' : 'Evaluate plan (uses model credits)'}
      </button>
      {history.data && !history.data.enabled && <p>Plan evaluation is awaiting deployment configuration and validation.</p>}
    </form>}
    {(error || history.error) && <p role="alert">{error || history.error}</p>}
    {history.error && <button className="btn-secondary" onClick={history.reload}>Retry plan history</button>}
    {!!history.data?.results.length && <label className="block">Plan evaluation history<select className="input block w-full" value={id} onChange={(e) => setSelected(e.target.value)}>
      {selected && !history.data.results.some((r) => r.id === selected) && <option value={selected}>Selected evaluation</option>}
      {history.data.results.map((r) => <option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleString()} · {r.status}</option>)}
    </select></label>}
    <div className="flex gap-3"><button className="btn-secondary" disabled={!history.data?.previous} onClick={() => { setSelected(''); setPage(page - 1); }}>Newer plans</button>
      <button className="btn-secondary" disabled={!history.data?.next} onClick={() => { setSelected(''); setPage(page + 1); }}>Older plans</button></div>
    {id && <SavedPlan key={id} sprint={sprint} run={run.id} id={id} refreshHistory={history.reload} />}
  </section>;
}
function SavedPlan({ sprint, run, id, refreshHistory }: { sprint: string; run: string; id: string; refreshHistory: () => void }) {
  const { can } = useAccess();
  const saved = useCapabilityRead(() => api.getPlanEvaluation(sprint, run, id), [sprint, run, id]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  React.useEffect(() => {
    if (!active(saved.data)) return;
    const timer = window.setInterval(saved.reload, 3000);
    return () => window.clearInterval(timer);
  }, [saved.data?.status, saved.reload]);
  React.useEffect(() => { if (saved.data?.status) refreshHistory(); }, [saved.data?.status, refreshHistory]);
  async function action(fn: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(getErrorMessage(e)); } finally { setBusy(false); }
  }
  const data = saved.data;
  return <div className="space-y-4">
    {(saved.error || error) && <p role="alert">{saved.error || error}</p>}
    {!data ? <button className="btn-secondary" onClick={saved.reload}>Retry plan evaluation</button> : <>
      <p>Evaluation: {data.status} · {data.completed_stages.length} processing stages saved</p>
      {data.stalled && <p role="alert">This evaluation may be stalled. Cancel it before requesting a new version.</p>}
      {active(data) && can('sprint.manage') && <button className="btn-secondary" disabled={busy} onClick={() => action(async () => { await api.cancelPlanEvaluation(sprint, run, id); saved.reload(); refreshHistory(); })}>Cancel evaluation</button>}
      {data.error && <p role="alert">Plan review could not be completed. {data.error.next_action}</p>}
      {data.comparison && <PlanComparisonView data={data} />}
      {!data.comparison && data.original_review && <OriginalPlanReview plan={data.original_review} />}
      <details><summary>Original submitted plan</summary><p className="whitespace-pre-wrap">{data.original_text}</p></details>
      <div className="flex gap-3"><button className="btn-secondary" disabled={busy} onClick={() => action(() => api.downloadPlanReport(sprint, run, id, 'html'))}>Download printable plan comparison</button>
      <button className="btn-secondary" disabled={busy} onClick={() => action(() => api.downloadPlanReport(sprint, run, id, 'json'))}>Download plan evidence JSON</button></div>
    </>}
  </div>;
}
type Scenario = { result: Result; paired_change?: { lower: number; upper: number; basis: string }; score?: PlanScore | null };
const signed = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(1)}`;
/** Part-credit plans show one score and its gain; plans evaluated before part credit keep their recorded ranges. */
export const phaseLabel = (s: Scenario) => (s.score ? `${s.score.score.toFixed(1)} / 100 (${signed(s.score.gain)})` : scoreLabel(s.result));
export const standingLabel = (plan: PlanEvaluation) =>
  plan.evaluation.baseline_score != null ? `${plan.evaluation.baseline_score.toFixed(1)} / 100` : scoreLabel(plan.evaluation.baseline);
const scored = (plan: PlanEvaluation) => plan.evaluation.baseline_score != null;

function AreaResults({ scenario }: { scenario: Scenario }) {
  if (scenario.score) {
    return <>{scenario.score.pillars.map((p) => <p key={p.code}>{areaNames[p.code] || p.code}: {p.score} / 100 ({signed(p.gain)})</p>)}</>;
  }
  return <>{scenario.result.pillars.map((p) => <p key={p.code}>{areaNames[p.code] || p.code}: {p.lower}–{p.upper} / 100</p>)}
    {scenario.paired_change && <p>Paired conditional change: {scenario.paired_change.lower}–{scenario.paired_change.upper}. {scenario.paired_change.basis}</p>}</>;
}

export function PriorityCoverageView({ plan }: { plan: PlanEvaluation }) {
  const c = plan.evaluation.priority_coverage;
  if (!c) return null;
  const total = c.covered.length + c.missed.length;
  return <section className="space-y-1" aria-label="Plan against the priority plan">
    <h3 className="font-bold">Your plan against the priority plan</h3>
    <p>Your plan would complete {c.covered.length} of the {total} priority requirements{c.priority_projected_score != null ? `; the full priority plan would take the score to ${c.priority_projected_score} / 100` : ''}.</p>
    {c.missed.length > 0 && <p>{c.missed.length} priority requirements are not addressed by your plan.</p>}
    {c.outside_priority_plan.length > 0 && <p>{c.outside_priority_plan.length} requirements your plan targets are outside the priority plan.</p>}
  </section>;
}

export function OriginalPlanReview({ plan }: { plan: PlanEvaluation }) {
  return <section className="space-y-3" aria-label="Saved original plan review">
    <h3 className="font-bold">Saved original plan review</h3>
    <p>The original review completed before the later comparison stopped. No improved plan is established.</p>
    <p>{scored(plan) ? 'Current score' : 'Current assessed standing'}: {standingLabel(plan)}</p>
    <p className="panel-muted">{plan.evaluation.note}{scored(plan) ? '' : ' An unresolved range is not a predicted score or guaranteed gain.'}</p>
    {(['implementation', 'results'] as const).map((phase) => <div key={phase}>
      <h4 className="font-semibold">{phase === 'implementation' ? 'Delivery only' : 'With results assumptions'}: {phaseLabel(plan.evaluation.scenarios[phase])}</h4>
      <details><summary>Area results</summary><AreaResults scenario={plan.evaluation.scenarios[phase]} /></details>
    </div>)}
    <PriorityCoverageView plan={plan} />
    {plan.evaluation.accepted.map((m) => <p key={m.condition_id}>{m.rationale}. Assumptions: {m.assumptions.join('; ')}</p>)}
    {!plan.evaluation.accepted.length && <p>No complete conditional requirement mappings were established.</p>}
    {plan.evaluation.rejected.map((r, n) => <p key={n}>Not credited: {r.reason}</p>)}
  </section>;
}

export function PlanComparisonView({ data }: { data: PlanComparison }) {
  const comparison = data.comparison!;
  return <div className="space-y-4">
    <p className="panel-muted">Conditional scenarios, not actual scores or predictions. {comparison.comparison_basis}</p>
    <p>{scored(comparison.original) ? 'Current score' : 'Current assessed standing'}: {standingLabel(comparison.original)}</p>
    <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Plan</th><th>Delivery only</th><th>With results assumptions</th></tr></thead><tbody>
      {([['Your original plan', comparison.original], ['Suggested improved plan', comparison.improved]] as [string, PlanEvaluation][]).map(([label, plan]) => <tr key={label}>
        <th className="py-3 pr-3">{label}</th><td>{phaseLabel(plan.evaluation.scenarios.implementation)}</td><td>{phaseLabel(plan.evaluation.scenarios.results)}</td>
      </tr>)}
    </tbody></table></div>
    {scored(comparison.original)
      ? <p className="text-sm">Scores assume the mapped actions are completed and shown; they are not predictions.</p>
      : <p className="text-sm">An unresolved range is not an estimated score. A change in its lower bound is not a guaranteed gain. Partial work may earn no points until the method’s prerequisites are met.</p>}
    <PriorityCoverageView plan={comparison.original} />
    <h3 className="font-bold">Suggested improved plan</h3><p className="whitespace-pre-wrap">{comparison.improved.text}</p>
    <p>{comparison.improvement.constraint_note}</p>
    {comparison.improvement.changes.map((change, n) => <article key={n} className="border-t border-line pt-3 space-y-2">
      <h4 className="font-semibold">{change.operation}: {change.action}</h4><p>{change.why}</p>
      <p>Suggested owner: {change.suggested_owner}</p><p>Dependencies: {change.dependencies.join('; ') || 'None specified'}</p>
      <p>Completion evidence: {change.completion_evidence}</p><p>{change.resource_note}</p>
    </article>)}
    {([['Original', comparison.original], ['Improved', comparison.improved]] as [string, PlanEvaluation][]).map(([label, plan]) => <details key={label}><summary>{label} plan: area results, assumptions and uncredited actions</summary>
      {(['implementation', 'results'] as const).map((phase) => <div key={phase} className="mt-3"><h4 className="font-semibold">{phase === 'implementation' ? 'Delivery only' : 'With results assumptions'}</h4>
        <AreaResults scenario={plan.evaluation.scenarios[phase]} />
      </div>)}
      {plan.evaluation.accepted.map((m) => <p key={m.condition_id} className="mt-3">{m.rationale} · {m.phase}. Assumptions: {m.assumptions.join('; ')}</p>)}
      {!plan.evaluation.accepted.length && <p>No complete conditional requirement mappings established. Qualitative feedback is still available.</p>}
      {plan.evaluation.rejected.map((r, n) => <p key={n} className="mt-2">Not credited: {r.reason}</p>)}
    </details>)}
    {comparison.limitations.map((note, n) => <p key={n} className="text-sm">{note}</p>)}
  </div>;
}
