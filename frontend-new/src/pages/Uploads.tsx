import { useRef, useState, type DragEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, CheckItem, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { usePolling, useResource } from '../hooks/useResource';
import {
  cancelExtractionJob, cancelSprintExtraction, confirmDocumentCategory, deleteDocument, deleteExtractionJob, downloadDocument, listExtractionJobs,
  listSprintDocuments, processExtractionJob, processIncomplete, startExtraction, updateDocument, uploadDocument,
} from '../services/documents';
import type { ExtractionJob, Sprint, SprintDocument } from '../types/api';
import { errorMessage } from '../utils/errors';

/** The evidence-pack checklist slugs the backend classifies against (apps.documents.constants.DRIVE_IMPORT_CHECKLIST). */
const DOCUMENT_TYPES = [
  { type: 'naac_ssr', label: 'NAAC SSR / Self-Study Report' },
  { type: 'aqar_report', label: 'AQAR / Annual Quality Assurance Report' },
  { type: 'aicte_approval', label: 'AICTE Approval / University Affiliation' },
  { type: 'faculty_master', label: 'Faculty Master List & Qualifications' },
  { type: 'student_strength', label: 'Student Enrolment & Strength Report' },
  { type: 'placement_report', label: 'Placement & Internship Report' },
  { type: 'syllabi_curriculum', label: 'Syllabi & BOS Curriculum Minutes' },
  { type: 'lab_inventory', label: 'Lab Infrastructure & Software Inventory' },
  { type: 'research_publications', label: 'Research Publications & Patents' },
  { type: 'ai_policy_doc', label: 'Institutional AI Strategy & Policy' },
  { type: 'unclassified', label: 'Other / let the AI classify' },
];

const ACTIVE_JOB = new Set(['pending', 'running', 'retrying']);

export function Uploads() {
  return <RequireSprint>{(sprint) => <UploadsBody sprint={sprint} />}</RequireSprint>;
}

function UploadsBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const docs = useResource<SprintDocument[]>(() => listSprintDocuments(sprint.id), sprint.id);
  const jobs = useResource<ExtractionJob[]>(() => listExtractionJobs(sprint.id), sprint.id);
  const [docType, setDocType] = useState('unclassified');
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<{ doc: SprintDocument; kind: 'edit' | 'category' | 'delete' } | null>(null);
  const typeOptions = DOCUMENT_TYPES.map((t) => ({ value: t.type, label: t.label }));

  const active = (jobs.data || []).filter((j) => ACTIVE_JOB.has(j.status));
  usePolling(() => { void jobs.refetch(); void docs.refetch(); }, active.length > 0);
  const waiting = (docs.data || []).filter((d) => d.status === 'uploaded' || d.status === 'failed').length;

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy('upload');
    setMsg(null);
    const failures: string[] = [];
    for (const file of Array.from(files)) {
      try { await uploadDocument(sprint.id, file, docType); } catch (e) { failures.push(`${file.name}: ${errorMessage(e)}`); }
    }
    setBusy('');
    await docs.refetch();
    setMsg(failures.length
      ? { tone: 'error', text: `${files.length - failures.length} uploaded, ${failures.length} failed. ${failures.join(' ')}` }
      : { tone: 'success', text: `${files.length} file(s) uploaded. Start processing to extract facts.` });
    if (input.current) input.current.value = '';
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (can('documents.contribute')) void upload(e.dataTransfer.files);
  };

  const run = async (fn: () => Promise<unknown>, ok: string, key: string) => {
    setBusy(key);
    setMsg(null);
    try { await fn(); setMsg({ tone: 'success', text: ok }); await Promise.all([jobs.refetch(), docs.refetch()]); }
    catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
    finally { setBusy(''); }
  };

  return (
    <>
      <PageHeading page="uploads" actions={can('documents.contribute') && (
        <>
          <PageLink to="processing">Processing control</PageLink>
          {active.length > 0 && <button className="secondary-button" disabled={!!busy} onClick={() => void run(() => cancelSprintExtraction(sprint.id), 'Processing stopped.', 'stop')}>Stop processing</button>}
          <button className="secondary-button" disabled={!!busy || active.length > 0} title="Re-run every document that is not completed"
            onClick={() => void run(() => processIncomplete(sprint.id), 'Incomplete documents queued again.', 'incomplete')}>Re-run incomplete</button>
          <button className="primary-action" disabled={!!busy || waiting === 0} onClick={() => void run(() => startExtraction(sprint.id), 'Processing started. Progress updates every few seconds.', 'start')}>
            {busy === 'start' ? 'Starting…' : `Process ${waiting || ''} document${waiting === 1 ? '' : 's'}`}
          </button>
        </>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="content-grid">
        <Panel>
          {can('documents.contribute') ? (
            <div className={`upload-zone ${drag ? 'drag' : ''}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}>
              <div>
                <div className="upload-icon" aria-hidden="true">⇧</div>
                <strong>Drop institutional evidence here</strong>
                <span>PDF, DOCX, XLSX, CSV and images</span>
                <div className="upload-controls">
                  <label className="field inline"><span>Document type</span>
                    <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                      {DOCUMENT_TYPES.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
                    </select>
                  </label>
                  <input ref={input} type="file" multiple className="sr-only" id="file-input" onChange={(e) => void upload(e.target.files)} />
                  <label htmlFor="file-input" className="primary-action as-button">{busy === 'upload' ? 'Uploading…' : 'Choose files'}</label>
                </div>
              </div>
            </div>
          ) : <p className="muted">Your role can view documents but not upload.</p>}
        </Panel>
        <Panel title="Processing safeguards">
          <div className="check-list">
            <CheckItem done>Original file preserved with its checksum</CheckItem>
            <CheckItem done>Pages and source locations retained on every fact</CheckItem>
            <CheckItem done>Extraction never changes the source file</CheckItem>
            <CheckItem done>Duplicate files are refused per sprint</CheckItem>
            <CheckItem done>Every AI suggestion requires human review</CheckItem>
          </div>
        </Panel>
      </div>
      {active.length > 0 && (
        <Panel title="Processing now" sub={`${active.length} document(s) in the pipeline`}>
          {active.map((j) => (
            <div key={j.id} className="bar-row">
              <span title={j.document_filename}>{j.document_filename}</span>
              <div className="bar-track" role="progressbar" aria-valuenow={j.progress_percentage} aria-valuemin={0} aria-valuemax={100}><div className="bar-fill" style={{ width: `${j.progress_percentage}%` }} /></div>
              <b>{j.progress_percentage}%</b>
            </div>
          ))}
        </Panel>
      )}
      <h2 className="section-title">Documents</h2>
      {docs.loading && !docs.data ? <Loading /> : docs.error ? <ErrorState error={docs.error} onRetry={() => void docs.refetch()} /> :
        !docs.data?.length ? <Empty title="No documents uploaded">Upload the evidence pack above to begin.</Empty> : (
          <Table columns={['File', 'Type', 'Pages', 'Extraction', 'Status', '']}>
            {docs.data.map((d) => {
              const job = (jobs.data || []).find((j) => j.document_id === d.id);
              return (
                <tr key={d.id}>
                  <td><strong>{d.original_filename}</strong><small className="cell-sub">{d.file_size_display}</small></td>
                  <td>{d.ai_document_type_label || d.document_type_label}</td>
                  <td>{d.page_count ?? '—'}</td>
                  <td>{job ? (job.status === 'failed' ? job.error_message || 'Failed' : job.current_step_label || job.status) : d.processing_status || '—'}</td>
                  <td><Pill status={d.status} /></td>
                  <td>
                    <div className="row-actions">
                      <button className="secondary-button" onClick={() => void downloadDocument(d.id, d.original_filename).catch((e) => setMsg({ tone: 'error', text: errorMessage(e) }))}>Download</button>
                      {can('documents.contribute') && <>
                        <button className="secondary-button" onClick={() => setEditing({ doc: d, kind: 'edit' })}>Edit</button>
                        <button className="secondary-button" title={`AI category: ${d.ai_document_type_label || 'none'} · ${d.classification_status || ''}`} onClick={() => setEditing({ doc: d, kind: 'category' })}>Category</button>
                        {job && job.status === 'failed' && <button className="secondary-button" disabled={!!busy} onClick={() => void run(() => processExtractionJob(job.id), `${d.original_filename}: processing again.`, `retry:${job.id}`)}>Retry</button>}
                        {job && ACTIVE_JOB.has(job.status) && <button className="secondary-button" disabled={!!busy} onClick={() => void run(() => cancelExtractionJob(job.id), `${d.original_filename}: stopped.`, `cancel:${job.id}`)}>Stop</button>}
                        {job && !ACTIVE_JOB.has(job.status) && job.status !== 'completed' && <button className="secondary-button" disabled={!!busy} title="Remove this job record; the document stays" onClick={() => void run(() => deleteExtractionJob(job.id), 'Job record removed.', `deljob:${job.id}`)}>Clear job</button>}
                        <button className="secondary-button" onClick={() => setEditing({ doc: d, kind: 'delete' })}>Delete</button>
                      </>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      {editing?.kind === 'edit' && (
        <ActionDialog title={`Edit ${editing.doc.original_filename}`} confirmLabel="Save"
          fields={[
            { name: 'title', label: 'Title', initial: editing.doc.title },
            { name: 'document_type', label: 'Document type', type: 'select', required: true, options: typeOptions, initial: editing.doc.document_type },
          ]}
          onSubmit={async (v) => { await updateDocument(editing.doc.id, { title: v.title, document_type: v.document_type }); await docs.refetch(); setMsg({ tone: 'success', text: 'Document updated.' }); }}
          onClose={() => setEditing(null)} />
      )}
      {editing?.kind === 'category' && (
        <ActionDialog title="Confirm the checklist category" confirmLabel="Confirm category"
          description={<p>AI suggestion: <b>{editing.doc.ai_document_type_label || 'none'}</b> ({editing.doc.classification_status || 'not classified'}). A person's choice settles it.</p>}
          fields={[{ name: 'category', label: 'Category', type: 'select', required: true, initial: editing.doc.document_type,
            options: [...typeOptions.filter((t) => t.value !== 'unclassified'), { value: '__none__', label: 'Not a checklist document' }] }]}
          onSubmit={async (v) => { await confirmDocumentCategory(editing.doc.id, v.category === '__none__' ? null : v.category); await docs.refetch(); setMsg({ tone: 'success', text: 'Category confirmed.' }); }}
          onClose={() => setEditing(null)} />
      )}
      {editing?.kind === 'delete' && (
        <ActionDialog title={`Delete ${editing.doc.original_filename}?`} danger confirmLabel="Delete document"
          description="The record and its stored file are removed. Facts already extracted from it may lose their source."
          fields={[]}
          onSubmit={async () => { await deleteDocument(editing.doc.id); await Promise.all([docs.refetch(), jobs.refetch()]); setMsg({ tone: 'success', text: 'Document deleted.' }); }}
          onClose={() => setEditing(null)} />
      )}
    </>
  );
}
