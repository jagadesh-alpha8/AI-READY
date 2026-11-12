import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, KeyValues, Loading, Notice, PageHeading, Panel, Pill, Stat, Table } from '../components/ui';
import { useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import { usePolling, useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { getExtractionJob, listDriveImports, listExtractionJobs, startDriveImport, stopDriveImport } from '../services/documents';
import { buildVectorIndex, getVectorIndexStatus } from '../services/evidenceSearch';
import { getProcessingSummary, getSprintAIUsage } from '../services/sprints';
import type { ExtractionJob, Page, ProcessingSummary, Sprint } from '../types/api';
import type { DriveImportJob, SprintAIUsage, VectorIndexRow } from '../types/workflow';
import { statusOf } from '../utils/errors';
import { dateTime, humanize, num, rows } from '../utils/format';

const DRIVE_ACTIVE = new Set(['pending', 'scanning', 'downloading']);

export function ProcessingControl() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const summary = useResource<ProcessingSummary>(() => getProcessingSummary(sprint.id), `ps:${sprint.id}`);
  const drive = useResource<DriveImportJob[]>(() => listDriveImports(sprint.id), `drive:${sprint.id}`);
  const jobs = useResource<ExtractionJob[]>(() => listExtractionJobs(sprint.id), `jobs:${sprint.id}`);
  const index = useResource<VectorIndexRow[] | Page<VectorIndexRow>>(() => getVectorIndexStatus(sprint.id), `vi:${sprint.id}`);
  const usage = useResource<SprintAIUsage>(() => getSprintAIUsage(sprint.id), `usage:${sprint.id}`, can('ai.usage'));
  const { busy, msg, setMsg, run } = useRunner();
  const [importing, setImporting] = useState(false);

  const driveActive = (drive.data || []).some((j) => DRIVE_ACTIVE.has(j.status));
  usePolling(() => { void drive.refetch(); void summary.refetch(); }, driveActive);

  const refreshJob = (id: string) => run(`job:${id}`, async () => {
    const res = await getExtractionJob(id);
    jobs.setData((jobs.data || []).map((j) => (j.id === id ? res.data : j)));
  });

  const indexRows = rows(index.data);
  const indexOff = statusOf(index.error) === 503;

  return (
    <>
      <PageHeading page="processing" actions={can('documents.contribute') && (
        <button className="primary-action" onClick={() => setImporting(true)}>Import from Google Drive</button>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}

      <Panel title="Processing summary" sub={summary.data?.description} actions={summary.data && <Pill status={summary.data.complete ? 'active' : 'pending'} label={summary.data.complete ? 'Complete' : 'In progress'} />}>
        {summary.loading && !summary.data ? <Loading /> : summary.error ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : (
          <div className="stat-grid">
            {Object.entries(summary.data!.counts).map(([k, v]) => <Stat key={k} label={humanize(k)} value={v} />)}
          </div>
        )}
      </Panel>

      <Panel title="Google Drive imports" sub="A link-shared folder is scanned and its files are added to this sprint">
        {drive.loading && !drive.data ? <Loading /> : drive.error ? <ErrorState error={drive.error} onRetry={() => void drive.refetch()} /> :
          !drive.data?.length ? <p className="muted">No Drive imports yet.</p> : (
            <Table columns={['Folder', 'Started', 'Scanned', 'Imported', 'Status', '']}>
              {drive.data.map((j) => (
                <tr key={j.id}>
                  <td className="source-cell"><span className="clamp-2" title={j.drive_url}>{j.drive_url}</span>{j.error_message && <small className="cell-sub">{j.error_message}</small>}</td>
                  <td>{dateTime(j.created_at)}</td>
                  <td>{j.files_scanned}{j.scan_limit_reached && <small className="cell-sub">Scan limit reached</small>}</td>
                  <td>{j.files_imported}</td>
                  <td><Pill status={j.status} /></td>
                  <td>{DRIVE_ACTIVE.has(j.status) && can('documents.contribute') && (
                    <button className="secondary-button" disabled={!!busy} onClick={() => void run(`stop:${j.id}`, async () => { await stopDriveImport(sprint.id, j.id); await drive.refetch(); }, 'Import stopped.')}>Stop</button>
                  )}</td>
                </tr>
              ))}
            </Table>
          )}
      </Panel>

      <Panel title="Extraction jobs" sub="One job per document; refresh a row to read its latest step">
        {jobs.loading && !jobs.data ? <Loading /> : jobs.error ? <ErrorState error={jobs.error} /> :
          !jobs.data?.length ? <p className="muted">No extraction jobs yet. Start processing from Upload & processing.</p> : (
            <Table columns={['Document', 'Step', 'Progress', 'Status', '']}>
              {jobs.data.map((j) => (
                <tr key={j.id}>
                  <td>{j.document_filename}{j.error_message && <small className="cell-sub">{j.error_message}</small>}</td>
                  <td>{j.current_step_label || '—'}</td>
                  <td>{j.progress_percentage}%</td>
                  <td><Pill status={j.status} /></td>
                  <td><button className="secondary-button" disabled={!!busy} onClick={() => void refreshJob(j.id)}>Refresh</button></td>
                </tr>
              ))}
            </Table>
          )}
      </Panel>

      <Panel title="Evidence search index" sub="Which processed documents the AI advisor and evidence search can read"
        actions={can('sprint.manage') && !indexOff && (
          <div className="row-actions">
            <button className="secondary-button" disabled={!!busy} onClick={() => void run('index', async () => { await buildVectorIndex(sprint.id); await index.refetch(); }, 'Indexing queued for processed documents.')}>Index new documents</button>
            <button className="secondary-button" disabled={!!busy} onClick={() => void run('reindex', async () => { await buildVectorIndex(sprint.id, true); await index.refetch(); }, 'Re-indexing every processed document.')}>Re-index all</button>
          </div>
        )}>
        {index.loading && !index.data ? <Loading /> : indexOff ? <p className="muted">Evidence search is not configured on this deployment.</p> :
          index.error ? <ErrorState error={index.error} onRetry={() => void index.refetch()} /> :
            !indexRows.length ? <p className="muted">Nothing indexed yet.</p> : (
              <Table columns={['Document', 'Chunks', 'Vectors', 'Indexed', 'Status']}>
                {indexRows.map((r) => (
                  <tr key={r.document}>
                    <td>{r.document_name || r.document}{r.error_message && <small className="cell-sub">{r.error_message}</small>}</td>
                    <td>{r.chunk_count ?? '—'}</td>
                    <td>{r.vector_count ?? '—'}</td>
                    <td>{dateTime(r.indexed_at)}</td>
                    <td><Pill status={r.status} /></td>
                  </tr>
                ))}
              </Table>
            )}
      </Panel>

      {can('ai.usage') && (
        <Panel title="AI usage for this sprint" sub="Tokens and cost recorded for every model call">
          {usage.loading && !usage.data ? <Loading /> : usage.error ? <ErrorState error={usage.error} /> : !usage.data ? <Empty title="No usage" /> : (
            <>
              <div className="stat-grid">
                <Stat label="Model calls" value={num(usage.data.calls)} note={`${usage.data.unpriced_calls} unpriced`} />
                <Stat label="Tokens" value={num(usage.data.total_tokens)} note={`${num(usage.data.input_tokens)} in · ${num(usage.data.output_tokens)} out`} />
                <Stat label="Cost (USD)" value={usage.data.cost_usd} note={`${usage.data.documents} documents`} />
                <Stat label="Period" value={dateTime(usage.data.last_call)} note={`from ${dateTime(usage.data.first_call)}`} />
              </div>
              <Table columns={['Stage', 'Calls', 'Tokens', 'Cost (USD)']}>
                {usage.data.by_stage.map((s) => <tr key={s.stage}><td>{humanize(s.stage)}</td><td>{num(s.calls)}</td><td>{num(s.total_tokens)}</td><td>{s.cost_usd}</td></tr>)}
              </Table>
              <Table columns={['Model', 'Calls', 'Tokens', 'Cost (USD)']}>
                {usage.data.by_model.map((s) => <tr key={s.model}><td>{s.model}</td><td>{num(s.calls)}</td><td>{num(s.total_tokens)}</td><td>{s.cost_usd}</td></tr>)}
              </Table>
              {usage.data.notes.length > 0 && <ul className="plain-list muted">{usage.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
              <KeyValues data={{ top_documents: usage.data.top_documents.map((d) => `${d.filename} (${d.cost_usd})`) }} />
            </>
          )}
        </Panel>
      )}

      {importing && (
        <ActionDialog title="Import from Google Drive" confirmLabel="Start import"
          description="Share the folder as 'Anyone with the link can view'. Files already in the sprint are skipped."
          fields={[{ name: 'url', label: 'Folder link', required: true, placeholder: 'https://drive.google.com/drive/folders/…' }]}
          onSubmit={async (v) => { await startDriveImport(sprint.id, v.url.trim()); await drive.refetch(); setMsg({ tone: 'success', text: 'Import started. This list refreshes while it runs.' }); }}
          onClose={() => setImporting(false)} />
      )}
    </>
  );
}
