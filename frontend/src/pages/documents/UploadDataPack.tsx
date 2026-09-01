import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { deleteDocument, listSprintDocuments, uploadDocument } from '../../api/documents';
import { startExtraction } from '../../api/extraction';
import { listDriveImportJobs, startDriveImport } from '../../api/driveImport';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import {
  ACTIVE_DRIVE_IMPORT_STATUSES,
  type DriveImportChecklistResult,
  type DriveImportJob,
  type DriveImportSkippedFile,
  type SprintDocument,
} from '../../types';
import { Upload, CheckCircle2, AlertCircle, Play, File, Trash2, Link2, Loader2 } from 'lucide-react';

const POLL_INTERVAL_MS = 3000; // matches AIProcessingMonitor.tsx

const REQUIRED_CHECKLIST = [
  { type: 'naac_ssr', label: 'NAAC SSR / Latest Self-Study Report', cat: 'Required Core', owner: 'IQAC_COORDINATOR' },
  { type: 'aqar_report', label: 'AQAR / Annual Quality Assurance Report', cat: 'Required Core', owner: 'IQAC_COORDINATOR' },
  { type: 'aicte_approval', label: 'AICTE Approval / University Affiliation', cat: 'Required Core', owner: 'REGISTRAR' },
  { type: 'faculty_master', label: 'Faculty Master List & Qualifications', cat: 'Required Core', owner: 'HR_OFFICER' },
  { type: 'student_strength', label: 'Student Enrolment & Strength Report', cat: 'Required Core', owner: 'REGISTRAR' },
  { type: 'placement_report', label: 'Placement & Industry Internship Report', cat: 'Required Core', owner: 'PLACEMENT_OFFICER' },
  { type: 'syllabi_curriculum', label: 'Syllabi & BOS Curriculum Minutes', cat: 'Recommended AI Readiness', owner: 'HOD' },
  { type: 'lab_inventory', label: 'Lab Infrastructure & Software Inventory', cat: 'Recommended AI Readiness', owner: 'LAB_ADMIN' },
  { type: 'research_publications', label: 'Research Publications & Patents Log', cat: 'Recommended AI Readiness', owner: 'RESEARCH_CELL' },
  { type: 'ai_policy_doc', label: 'Institutional AI Strategy & Policy', cat: 'Optional Deep Evidence', owner: 'INSTITUTION_ADMIN' },
];

export const UploadDataPack: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: documentsData,
    loading,
    error,
    refetch,
  } = useApiResource<SprintDocument[]>(() => listSprintDocuments(sprintId!), [sprintId], isRealSprint);
  const documents = documentsData || [];

  const { data: driveJobsData, refetch: refetchDriveJobs } = useApiResource<DriveImportJob[]>(
    () => listDriveImportJobs(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const driveJobs = driveJobsData || [];
  const latestDriveJob = driveJobs[0]; // API orders -created_at, same convention as extraction jobs

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [extractionError, setExtractionError] = useState('');
  const [selectedType, setSelectedType] = useState('naac_ssr');
  const [selectedOwner, setSelectedOwner] = useState('IQAC_COORDINATOR');
  const [dragActive, setDragActive] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<'upload' | 'drive'>('upload');
  const [driveUrl, setDriveUrl] = useState('');
  const [driveSubmitting, setDriveSubmitting] = useState(false);
  const [driveError, setDriveError] = useState('');

  const handleFileUpload = async (file: File) => {
    if (!isRealSprint) {
      setUploadError('No active sprint is selected. Set up a sprint first, then come back to upload.');
      return;
    }
    setUploading(true);
    setUploadError('');
    try {
      await uploadDocument(sprintId!, file, selectedType, selectedOwner);
      refetch();
    } catch (err) {
      setUploadError(getErrorMessage(err, 'File upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (doc: SprintDocument) => {
    if (!window.confirm(`Delete "${doc.original_filename}"? This removes the file and cannot be undone.`)) {
      return;
    }
    setDeletingId(doc.id);
    setUploadError('');
    try {
      await deleteDocument(doc.id);
      refetch();
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Failed to delete document.'));
    } finally {
      setDeletingId(null);
    }
  };

  const handleStartDriveImport = async () => {
    if (!isRealSprint) {
      setDriveError('No active sprint is selected. Set up a sprint first, then come back to import.');
      return;
    }
    if (!driveUrl.trim()) {
      setDriveError('Paste a Google Drive folder link first.');
      return;
    }
    setDriveSubmitting(true);
    setDriveError('');
    try {
      await startDriveImport(sprintId!, driveUrl.trim());
      refetchDriveJobs();
    } catch (err) {
      setDriveError(getErrorMessage(err, 'Failed to start the Drive import.'));
    } finally {
      setDriveSubmitting(false);
    }
  };

  // Poll while the latest Drive import job is still in flight.
  useEffect(() => {
    if (!latestDriveJob || !ACTIVE_DRIVE_IMPORT_STATUSES.includes(latestDriveJob.status)) return;
    const timer = setInterval(refetchDriveJobs, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestDriveJob?.status, refetchDriveJobs]);

  // Once the job completes, refresh the checklist + document table with no
  // manual action needed -- DRIVE_IMPORT_CHECKLIST slugs on the backend
  // equal REQUIRED_CHECKLIST slugs here, so newly-imported documents show
  // up as "found" for free.
  useEffect(() => {
    if (latestDriveJob?.status === 'completed') refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestDriveJob?.status, latestDriveJob?.id]);

  const handleStartExtraction = async () => {
    if (!isRealSprint) {
      setExtractionError('No active sprint is selected. Set up a sprint first, then come back to start extraction.');
      return;
    }
    setExtractionError('');
    try {
      await startExtraction(sprintId!);
      navigate(`/sprint/${sprintId}/monitor`);
    } catch (err) {
      setExtractionError(getErrorMessage(err, 'Failed to start extraction job.'));
    }
  };

  const uploadedTypes = new Set(documents.map((d) => d.document_type));

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Upload className="w-5 h-5 text-brand-800" /> Screen 2: Upload Institution Data Pack
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Upload existing NAAC SSR, AQAR, faculty lists, lab inventory, placement reports, and syllabi for AI processing.
            </p>
          </div>
          <button onClick={handleStartExtraction} className="btn-primary shrink-0">
            <Play className="w-4 h-4 fill-current" />
            <span>Start AI Extraction Run</span>
          </button>
        </div>
      </div>

      {!isRealSprint && (
        <div className="p-4 bg-warning-bg border border-warning-line rounded-lg text-sm text-warning flex items-center justify-between gap-3 flex-wrap">
          <span className="flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4 shrink-0" />
            No active sprint is selected, so uploads and extraction can't run yet. Set up a sprint first.
          </span>
          <button onClick={() => navigate('/sprint/setup')} className="btn-secondary btn-sm shrink-0">
            Go to Sprint Setup
          </button>
        </div>
      )}

      {extractionError && <InlineError message={extractionError} onDismiss={() => setExtractionError('')} />}
      {uploadError && <InlineError message={uploadError} onDismiss={() => setUploadError('')} />}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Document Checklist */}
        <div className="lg:col-span-5 glass-card p-5 sm:p-6 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="eyebrow">Required Data Pack Checklist</h2>
            <span className="badge-brand">{uploadedTypes.size} / {REQUIRED_CHECKLIST.length} Uploaded</span>
          </div>

          <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
            {REQUIRED_CHECKLIST.map((item) => {
              const isUploaded = uploadedTypes.has(item.type);
              return (
                <div
                  key={item.type}
                  onClick={() => {
                    setSelectedType(item.type);
                    setSelectedOwner(item.owner);
                  }}
                  className={`p-3 rounded-lg border text-sm cursor-pointer transition-all flex items-start justify-between gap-2 ${
                    selectedType === item.type
                      ? 'bg-brand-50 border-brand-500 text-ink-900 shadow-card'
                      : isUploaded
                      ? 'bg-card border-line-200 text-ink-700'
                      : 'bg-surface border-line-200 text-ink-500 hover:border-line-300'
                  }`}
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2">
                      {isUploaded ? (
                        <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-warning shrink-0" />
                      )}
                      <span className="font-semibold truncate">{item.label}</span>
                    </div>
                    <p className="text-xs text-ink-500 pl-6">Owner: {item.owner}</p>
                  </div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-line-100 text-ink-600 font-mono shrink-0">
                    {item.cat}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Drag and Drop Upload Area */}
        <div className="lg:col-span-7 glass-card p-5 sm:p-6 flex flex-col justify-between space-y-4">
          <div>
            <h2 className="eyebrow mb-2">Data Source</h2>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div
                onClick={() => setDataSource('upload')}
                className={`p-3 rounded-xl border-2 cursor-pointer transition-all text-center ${
                  dataSource === 'upload'
                    ? 'bg-brand-50 border-brand-500 shadow-card'
                    : 'bg-card border-line-200 hover:border-line-300'
                }`}
              >
                <span className="text-sm font-bold text-ink-900">Upload Files</span>
              </div>
              <div
                onClick={() => setDataSource('drive')}
                className={`p-3 rounded-xl border-2 cursor-pointer transition-all text-center ${
                  dataSource === 'drive'
                    ? 'bg-brand-50 border-brand-500 shadow-card'
                    : 'bg-card border-line-200 hover:border-line-300'
                }`}
              >
                <span className="text-sm font-bold text-ink-900 flex items-center justify-center gap-1.5">
                  <Link2 className="w-4 h-4" /> Google Drive
                </span>
              </div>
            </div>

            {dataSource === 'upload' && (
              <div>
                <h2 className="eyebrow mb-2">Upload Selected Document</h2>
                <p className="text-sm text-ink-500 mb-4">
                  Uploading as <span className="font-semibold text-brand-800">{REQUIRED_CHECKLIST.find((c) => c.type === selectedType)?.label}</span> (Owner: <span className="font-semibold text-ink-700">{selectedOwner}</span>)
                </p>

                <div
                  onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragActive(false);
                    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                      handleFileUpload(e.dataTransfer.files[0]);
                    }
                  }}
                  className={`border-2 border-dashed rounded-xl p-6 sm:p-8 text-center transition-all ${
                    dragActive ? 'border-brand-500 bg-brand-50' : 'border-line-300 bg-surface hover:border-line-300/80'
                  }`}
                >
                  <div className="w-12 h-12 rounded-full bg-brand-500/10 flex items-center justify-center mx-auto text-brand-800 mb-3">
                    <Upload className="w-6 h-6" />
                  </div>
                  <p className="text-sm font-semibold text-ink-900">
                    Drag and drop PDF, DOCX, XLSX, CSV, or ZIP files here
                  </p>
                  <p className="text-xs text-ink-500 mt-1 mb-4">Maximum file size: 50MB per document</p>

                  <label className="btn-primary btn-sm cursor-pointer inline-flex">
                    <span>{uploading ? 'Uploading File...' : 'Browse Files'}</span>
                    <input
                      type="file"
                      className="hidden"
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          handleFileUpload(e.target.files[0]);
                        }
                      }}
                    />
                  </label>
                </div>
              </div>
            )}

            {dataSource === 'drive' && (
              <DriveImportPanel
                driveUrl={driveUrl}
                setDriveUrl={setDriveUrl}
                driveSubmitting={driveSubmitting}
                driveError={driveError}
                setDriveError={setDriveError}
                latestDriveJob={latestDriveJob}
                onStart={handleStartDriveImport}
              />
            )}
          </div>

          {/* Quick Mock Files Upload Button for Instant Demo */}
          <div className="p-4 bg-surface rounded-xl border border-line-200 flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-bold text-ink-900 flex items-center gap-1.5">
                <Upload className="w-4 h-4 text-brand-800" /> Instant Demo Pack Generator
              </p>
              <p className="text-xs text-ink-500 mt-0.5">Populate minimum required 6-file data pack automatically for fast testing.</p>
            </div>
            <button
              onClick={() => setUploadError(
                'Demo pack seeding is disabled: documents are only ever created through a real file upload or the extraction pipeline, never fabricated.',
              )}
              className="btn-secondary btn-sm shrink-0"
            >
              Seed Demo Pack
            </button>
          </div>
        </div>
      </div>

      {/* Uploaded Documents Table */}
      <div className="glass-card p-5 sm:p-6">
        <h2 className="eyebrow mb-4">Uploaded Document Records</h2>
        {loading ? (
          <LoadingState message="Loading uploaded documents..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : documents.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No documents uploaded yet. Upload files above.</p>
          </div>
        ) : (
          <div className="table-shell">
            <table className="table-base">
              <thead>
                <tr>
                  <th>File Name</th>
                  <th>Document Type</th>
                  <th>Owner Role</th>
                  <th>Status</th>
                  <th>Processing Notes</th>
                  <th>Uploaded At</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td className="font-medium text-ink-900">
                      <div className="flex items-center gap-2">
                        <File className="w-4 h-4 text-brand-800 shrink-0" />
                        <span>{doc.original_filename}</span>
                      </div>
                    </td>
                    <td className="text-ink-600 font-mono text-xs">{doc.document_type}</td>
                    <td className="text-ink-600">{doc.owner_role || 'IQAC'}</td>
                    <td>
                      <span className="badge-success">{doc.status}</span>
                    </td>
                    <td>
                      {doc.page_count === null ? (
                        // Not read yet (extraction hasn't run on this document) --
                        // ocr_required is still just the upload-time guess (every
                        // PDF starts out flagged, before any content is read), so
                        // showing it here would be premature, not a real finding.
                        <span className="text-ink-400">Pending extraction</span>
                      ) : doc.ocr_required ? (
                        <span
                          className="badge-warning"
                          title={doc.ocr_warnings?.[0] || 'Little or no extractable text was found on one or more pages.'}
                        >
                          No text found — needs OCR
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="text-ink-500">{new Date(doc.created_at).toLocaleTimeString()}</td>
                    <td className="text-right">
                      <button
                        onClick={() => handleDelete(doc)}
                        disabled={deletingId === doc.id}
                        title="Delete document"
                        className="btn-icon hover:text-danger hover:bg-danger-bg"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

const DRIVE_STATUS_LABELS: Record<string, string> = {
  pending: 'Queued…',
  scanning: 'Scanning folder…',
  downloading: 'Downloading matched files…',
};

const DriveImportPanel: React.FC<{
  driveUrl: string;
  setDriveUrl: (value: string) => void;
  driveSubmitting: boolean;
  driveError: string;
  setDriveError: (value: string) => void;
  latestDriveJob: DriveImportJob | undefined;
  onStart: () => void;
}> = ({ driveUrl, setDriveUrl, driveSubmitting, driveError, setDriveError, latestDriveJob, onStart }) => {
  const jobActive = !!latestDriveJob && ACTIVE_DRIVE_IMPORT_STATUSES.includes(latestDriveJob.status);
  const unmatchedFiles = (latestDriveJob?.results?.unmatched_files as string[] | undefined) || [];
  const skippedFiles = (latestDriveJob?.results?.skipped_files as DriveImportSkippedFile[] | undefined) || [];

  return (
    <div>
      <h2 className="eyebrow mb-2">Import From Google Drive</h2>
      <p className="text-sm text-ink-500 mb-4">
        Paste a folder link and the system scans it, downloads whatever matches the required checklist, and
        imports it automatically — no manual file selection needed.
      </p>

      <div className="space-y-3">
        <div>
          <input
            type="text"
            value={driveUrl}
            onChange={(e) => setDriveUrl(e.target.value)}
            placeholder="https://drive.google.com/drive/folders/..."
            disabled={driveSubmitting || jobActive}
            className="input w-full"
          />
          <p className="text-xs text-ink-500 mt-1.5">
            Folder must be shared as <span className="font-semibold">"Anyone with the link — Viewer"</span>.
          </p>
        </div>

        <button onClick={onStart} disabled={driveSubmitting || jobActive} className="btn-primary btn-sm">
          <Link2 className="w-4 h-4" />
          <span>{driveSubmitting ? 'Starting…' : 'Scan & Import'}</span>
        </button>

        {driveError && <InlineError message={driveError} onDismiss={() => setDriveError('')} />}

        {latestDriveJob && (
          <div className="p-4 bg-surface rounded-xl border border-line-200 space-y-3">
            {jobActive && (
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="w-4 h-4 text-brand-800 animate-spin" />
                <span className="badge-brand">{DRIVE_STATUS_LABELS[latestDriveJob.status] || latestDriveJob.status}</span>
              </div>
            )}

            {latestDriveJob.status === 'failed' && (
              <div className="flex items-start gap-2 text-sm">
                <span className="badge-danger shrink-0">Failed</span>
                <span className="text-ink-700">{latestDriveJob.error_message}</span>
              </div>
            )}

            {latestDriveJob.status === 'completed' && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm">
                  <span className="badge-success">
                    Scanned {latestDriveJob.files_scanned} files, imported {latestDriveJob.files_imported}
                  </span>
                </div>

                <div className="space-y-1.5">
                  {REQUIRED_CHECKLIST.map((item) => {
                    const result = latestDriveJob.results[item.type] as DriveImportChecklistResult | undefined;
                    const found = result?.status === 'found';
                    return (
                      <div key={item.type} className="flex items-center gap-2 text-xs">
                        {found ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-warning shrink-0" />
                        )}
                        <span className={found ? 'text-ink-700' : 'text-ink-500'}>{item.label}</span>
                        {found && result?.filename && (
                          <span className="text-ink-400 truncate">— {result.filename}</span>
                        )}
                      </div>
                    );
                  })}
                </div>

                {unmatchedFiles.length > 0 && (
                  <div className="text-xs text-ink-500">
                    <p className="font-semibold text-ink-600 mb-1">Found in folder but not matched:</p>
                    {unmatchedFiles.map((name) => (
                      <p key={name} className="truncate">{name}</p>
                    ))}
                  </div>
                )}

                {skippedFiles.length > 0 && (
                  <div className="text-xs text-ink-500">
                    <p className="font-semibold text-ink-600 mb-1">Matched but could not be imported:</p>
                    {skippedFiles.map((skipped) => (
                      <p key={skipped.filename} className="truncate">{skipped.filename} — {skipped.reason}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
