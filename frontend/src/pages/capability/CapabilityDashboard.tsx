import React from 'react';
import { Link } from 'react-router-dom';
import { listRuns, getRun } from '../../api/capability';
import { useCapabilityRead, CapabilitySummary } from './CapabilityWorkspace';

export function CapabilityDashboard({ sprint }: { sprint: string }) {
  const history = useCapabilityRead(() => listRuns(sprint), [sprint]);
  if (!sprint)
    return (
      <p className="panel-muted">
        Select a sprint to see its institutional AI capability.
      </p>
    );
  if (history.error)
    return (
      <div className="panel-muted" role="alert">
        {history.error}
        <button className="btn-secondary ml-3" onClick={history.reload}>
          Retry capability history
        </button>
      </div>
    );
  if (!history.data)
    return <p className="panel-muted">Loading capability standing…</p>;
  const latest = history.data.results[0];
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-bold">
        Selected institution’s AI capability
      </h2>
      {latest ? (
        <DashboardRun key={latest.id} sprint={sprint} runId={latest.id} />
      ) : (
        <p className="panel-muted">
          Not assessed yet. Upload evidence and start an assessment.
        </p>
      )}
      <Link className="btn-primary" to={`/sprint/${sprint}/score`}>
        Open capability assessment
      </Link>
    </section>
  );
}
function DashboardRun({ sprint, runId }: { sprint: string; runId: string }) {
  const run = useCapabilityRead(() => getRun(sprint, runId), [sprint, runId]);
  if (run.error)
    return (
      <div role="alert">
        {run.error}
        <button className="btn-secondary ml-3" onClick={run.reload}>
          Retry standing
        </button>
      </div>
    );
  if (!run.data) return <p>Loading assessment…</p>;
  return run.data.assessment ? (
    <>
      <p>
        {run.data.profile.name} · {run.data.reference_period} · Frozen
        assessment
      </p>
      <CapabilitySummary result={run.data.assessment.result} />
    </>
  ) : (
    <p className="panel-muted">
      Latest assessment: {run.data.status}. No completed score for this run.
      Open assessment history to select an earlier completed run.
    </p>
  );
}
