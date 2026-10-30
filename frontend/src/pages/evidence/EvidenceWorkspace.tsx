import React from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { EvidenceIntelligence } from './EvidenceIntelligence';
import { FactsReview } from '../facts/FactsReview';
import { GapDashboard } from '../gaps/GapDashboard';
import { ComplianceMapping } from '../compliance/ComplianceMapping';
import { UploadDataPack } from '../documents/UploadDataPack';
import { AIProcessingMonitor } from '../documents/AIProcessingMonitor';
import { getRun } from '../../api/capability';
import { useApiResource } from '../../hooks/useApiResource';

const evidenceTabs = [
  ['documents', 'Documents'], ['review', 'Review exceptions'],
  ['gaps', 'Missing evidence & conflicts'], ['accreditation', 'Accreditation evidence'],
] as const;

function Tabs({ tabs, value, onChange }: {
  tabs: readonly (readonly [string, string])[]; value: string; onChange: (tab: string) => void;
}) {
  return <nav aria-label="Workspace sections" className="flex flex-wrap gap-2">
    {tabs.map(([id, label]) => <button key={id} className={id === value ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
      aria-current={id === value ? 'page' : undefined} onClick={() => onChange(id)}>{label}</button>)}
  </nav>;
}

export function EvidenceWorkspace() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('tab') || 'documents';
  const tab = evidenceTabs.some(([id]) => id === selected) ? selected : 'documents';
  return <div className="space-y-6" data-tour="evidence-workspace">
    <h1 className="text-2xl font-bold">Evidence & Review</h1>
    <p className="text-sm text-ink-600">Inspect sources and review exceptions in one place. Missing evidence does not establish a capability shortfall.</p>
    <Tabs tabs={evidenceTabs} value={tab} onChange={(next) => setParams({ tab: next })} />
    {tab === 'documents' && <EvidenceIntelligence />}
    {tab === 'review' && <FactsReview />}
    {tab === 'gaps' && <GapDashboard />}
    {tab === 'accreditation' && <ComplianceMapping />}
  </div>;
}

export function UploadWorkspace() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'processing' ? 'processing' : 'upload';
  const { sprintId } = useParams();
  const runId = params.get('run');
  const conditionId = params.get('condition');
  return <div className="space-y-6">
    <h1 className="text-2xl font-bold">Upload & Processing</h1>
    {sprintId && runId && conditionId && <UploadRequirement key={`${sprintId}:${runId}:${conditionId}`} sprint={sprintId} runId={runId} conditionId={conditionId} />}
    <Tabs tabs={[["upload", "Upload documents"], ["processing", "Processing status"]]} value={tab}
      onChange={(next) => setParams((previous) => { const p = new URLSearchParams(previous); p.set('tab', next); return p; })} />
    {tab === 'upload' ? <UploadDataPack /> : <AIProcessingMonitor />}
  </div>;
}

function UploadRequirement({ sprint, runId, conditionId }: { sprint: string; runId: string; conditionId: string }) {
  const { data: run, error } = useApiResource(() => getRun(sprint, runId), [sprint, runId]);
  const condition = run?.assessment?.result.indicators.flatMap((i) => i.conditions).find((c) => c.id === conditionId);
  return <div className="panel-muted text-sm">
    {condition ? <><strong>Supporting evidence for {condition.id}</strong><p>{condition.text}</p><p>{condition.completion_evidence}</p></>
      : <p>{error ? 'Unable to load the selected assessment requirement.' : run ? 'This requirement was not found in the selected assessment.' : 'Loading selected requirement…'}</p>}
    <p className="mt-2">Uploads add evidence to this sprint. Start a new assessment to evaluate it; the pinned result stays unchanged.</p>
  </div>;
}

/** Old bookmarks resolve to the single workspace, retaining pinned version selections. */
export function WorkspaceRedirect({ tab, upload, actions }: { tab?: string; upload?: boolean; actions?: boolean }) {
  const { sprintId: routeId } = useParams();
  const { sprintId } = useSelectedSprint();
  const [params] = useSearchParams();
  const id = routeId || sprintId;
  if (!id) return <SelectSprintPrompt />;
  const next = new URLSearchParams(params);
  if (!actions) next.set('tab', upload ? 'processing' : tab || 'documents');
  return <Navigate replace to={`/sprint/${id}/${actions ? 'recommendations' : upload ? 'upload' : 'evidence'}?${next}`} />;
}
