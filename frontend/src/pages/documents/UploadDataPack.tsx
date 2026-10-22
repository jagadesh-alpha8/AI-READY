import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { confirmDocumentCategory, deleteDocument, listSprintDocuments, uploadDocument } from '../../api/documents';
import { startExtraction } from '../../api/extraction';
import { listDriveImportJobs, startDriveImport, stopDriveImport } from '../../api/driveImport';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { TableFilters, matchesSearch, optionsFrom } from '../../components/TableFilters';
import {
  ACTIVE_DRIVE_IMPORT_STATUSES,
  type ClassificationStatus,
  type DriveImportAdditionalFile,
  type DriveImportChecklistResult,
  type DriveImportJob,
  type DriveImportProgress,
  type DriveImportSkippedFile,
  type SprintDocument,
} from '../../types';
import {
  Upload, CheckCircle2, AlertCircle, Play, File, Trash2, Link2, Loader2, Square, Clock, HelpCircle, UserCheck, Check,
} from 'lucide-react';
import { useAccess } from '../../utils/access';

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
  const { can, userId, step } = useAccess();
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
  const [driveStopping, setDriveStopping] = useState(false);
  // Every eligible document in the selected sprint is processed together.
  // Records-table filters.
  const [docSearch, setDocSearch] = useState('');
  const [docTypeFilter, setDocTypeFilter] = useState('');
  const [docAiFilter, setDocAiFilter] = useState('');
  const [docOwnerFilter, setDocOwnerFilter] = useState('');
  const [docStatusFilter, setDocStatusFilter] = useState('');
  const [docTextFilter, setDocTextFilter] = useState('');

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

  // A person settles a document's category (resolving "Needs review" /
  // "Unclassified", or overriding the AI). Resolves true once saved.
  const handleConfirmCategory = async (doc: SprintDocument, category: string | null) => {
    setUploadError('');
    try {
      await confirmDocumentCategory(doc.id, category);
      refetch();
      return true;
    } catch (err) {
      setUploadError(getErrorMessage(err, `Failed to save the category for "${doc.original_filename}".`));
      return false;
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

  const handleStopDriveImport = async () => {
    if (!latestDriveJob) return;
    setDriveStopping(true);
    setDriveError('');
    try {
      await stopDriveImport(sprintId!, latestDriveJob.id);
    } catch (err) {
      setDriveError(getErrorMessage(err, 'Failed to stop the Drive import.'));
    } finally {
      setDriveStopping(false);
      refetchDriveJobs();
      refetch();
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
  // The importer saves documents one at a time, so also refresh the
  // records table each time `files_imported` ticks up mid-import -- every
  // file appears in the table as soon as it lands.
  useEffect(() => {
    if (!latestDriveJob) return;
    if (latestDriveJob.status !== 'pending' || latestDriveJob.files_imported > 0) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestDriveJob?.status, latestDriveJob?.id, latestDriveJob?.files_imported]);

  const handleStartExtraction = async () => {
    if (!isRealSprint) {
      setExtractionError('No active sprint is selected. Set up a sprint first, then come back to start extraction.');
      return;
    }
    setExtractionError('');
    try {
      if (documents.length === 0) {
        setExtractionError('Add documents to this sprint before starting extraction.');
        return;
      }
      // No document IDs: the API queues every eligible document in this sprint,
      // including reused content that was processed in a different sprint.
      const { data: jobs } = await startExtraction(sprintId!);
      if (jobs.length === 0) {
        setExtractionError('Every eligible document is already processed or in progress. Check the AI Processing Monitor.');
        return;
      }
      navigate(`/sprint/${sprintId}/monitor`);
    } catch (err) {
      setExtractionError(getErrorMessage(err, 'Failed to start extraction job.'));
    }
  };

  // A checklist slot is filled by the saved category (the AI's, or a person's
  // confirmation), not by the label a document was uploaded/imported with --
  // see checklistSlot().
  const slotByType = new Map(REQUIRED_CHECKLIST.map((item) => [item.type, checklistSlot(item.type, documents)]));
  const slotStates = [...slotByType.values()].map((slot) => slot.state);
  const confirmedCount = slotStates.filter((state) => state === 'confirmed').length;
  const awaitingCount = slotStates.filter((state) => state === 'awaiting').length;
  const reviewCount = slotStates.filter((state) => state === 'review').length;

  // Records-table filters (client-side: every document is already loaded).
  const filteredDocuments = documents.filter((d) =>
    (!docTypeFilter || d.document_type === docTypeFilter)
    && (!docAiFilter || aiCategoryText(d) === docAiFilter)
    && (!docOwnerFilter || (d.owner_role || '') === docOwnerFilter)
    && (!docStatusFilter || d.status === docStatusFilter)
    && (!docTextFilter || textCheck(d) === docTextFilter)
    && matchesSearch(docSearch, d.original_filename, d.title, d.document_type, d.ai_document_type_label));

  // Only count ticks for documents that still exist (one may have been deleted).
  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Upload className="w-5 h-5 text-brand-800" /> Step {step('sprint-upload')}: Upload Institution Data Pack
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Upload existing NAAC SSR, AQAR, faculty lists, lab inventory, placement reports, and syllabi for AI processing.
            </p>
          </div>
          <button onClick={handleStartExtraction} disabled={!isRealSprint || documents.length === 0} className="btn-primary shrink-0">
            <Play className="w-4 h-4 fill-current" />
            <span>Analyze All Sprint Documents ({documents.length})</span>
          </button>
        </div>
      </div>

      {!isRealSprint && (
        <div className="p-4 bg-warning-bg border border-warning-line rounded-lg text-sm text-warning flex items-center justify-between gap-3 flex-wrap">
          <span className="flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4 shrink-0" />
            No active sprint is selected, so uploads and extraction can't run yet.
            {can('sprint.manage') ? ' Set up a sprint first.' : ' Open your sprint from the dashboard.'}
          </span>
          <button onClick={() => navigate(can('sprint.manage') ? '/sprint/setup' : '/dashboard')}
            className="btn-secondary btn-sm shrink-0">
            {can('sprint.manage') ? 'Go to Sprint Setup' : 'Go to the dashboard'}
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
            <span
              className="badge-brand"
              title="Counted from each document's category: detected by AI, or confirmed by a person"
            >
              {confirmedCount} / {REQUIRED_CHECKLIST.length} Confirmed
            </span>
          </div>
          {(awaitingCount > 0 || reviewCount > 0) && (
            <p className="text-xs text-ink-500">
              {[
                awaitingCount > 0 && `${awaitingCount} awaiting AI check`,
                reviewCount > 0 && `${reviewCount} need${reviewCount === 1 ? 's' : ''} review`,
              ].filter(Boolean).join(' · ')}
              {' '}— run AI extraction to confirm each document's category from its content
              {reviewCount > 0 && can('documents.contribute')
                ? ', or resolve it in Uploaded Document Records below.'
                : '.'}
            </p>
          )}

          <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
            {REQUIRED_CHECKLIST.map((item) => {
              const slot = slotByType.get(item.type)!;
              const SlotIcon = SLOT_DISPLAY[slot.state].icon;
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
                      : slot.state === 'confirmed'
                      ? 'bg-card border-line-200 text-ink-700'
                      : 'bg-surface border-line-200 text-ink-500 hover:border-line-300'
                  }`}
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2">
                      <SlotIcon className={`w-4 h-4 shrink-0 ${SLOT_DISPLAY[slot.state].className}`} />
                      <span className="font-semibold truncate">{item.label}</span>
                    </div>
                    <p className="text-xs text-ink-500 pl-6">Owner: {item.owner}</p>
                    {slot.doc && (
                      <p className="text-xs text-ink-500 pl-6 truncate" title={slot.doc.original_filename}>
                        {slot.doc.category_confirmed_at
                          ? `Confirmed by ${slot.doc.category_confirmed_by_name || 'a reviewer'}`
                          : SLOT_DISPLAY[slot.state].note}
                        : {slot.doc.original_filename}
                        {slot.state !== 'awaiting' && !slot.doc.category_confirmed_at && slot.doc.ai_confidence !== null
                          && ` · ${formatConfidence(slot.doc.ai_confidence)}`}
                      </p>
                    )}
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
                  Uploading as <span className="font-semibold text-brand-800">{REQUIRED_CHECKLIST.find((c) => c.type === selectedType)?.label}</span> (Owner: <span className="font-semibold text-ink-700">{selectedOwner}</span>).
                  {' '}AI extraction confirms the category from the document's content.
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
                onStop={handleStopDriveImport}
                driveStopping={driveStopping}
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
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="eyebrow">Uploaded Document Records</h2>
          {documents.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-ink-600 font-semibold">
                {documents.length} document{documents.length === 1 ? '' : 's'} included in this sprint; extraction processes every eligible document.
              </span>
            </div>
          )}
        </div>
        {loading ? (
          <LoadingState message="Loading uploaded documents..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : documents.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No documents uploaded yet. Upload files above.</p>
          </div>
        ) : (
          <>
          <TableFilters
            search={docSearch}
            onSearch={setDocSearch}
            placeholder="Search file name or type…"
            shown={filteredDocuments.length}
            total={documents.length}
            selects={[
              { key: 'ai', label: 'AI category', value: docAiFilter, onChange: setDocAiFilter,
                options: optionsFrom(documents, aiCategoryText) },
              { key: 'type', label: 'Assigned type', value: docTypeFilter, onChange: setDocTypeFilter,
                options: optionsFrom(documents, (d) => d.document_type) },
              { key: 'owner', label: 'Owner', value: docOwnerFilter, onChange: setDocOwnerFilter,
                options: optionsFrom(documents, (d) => d.owner_role) },
              { key: 'status', label: 'Status', value: docStatusFilter, onChange: setDocStatusFilter,
                options: optionsFrom(documents, (d) => d.status) },
              { key: 'text', label: 'Text check', value: docTextFilter, onChange: setDocTextFilter,
                options: optionsFrom(documents, textCheck) },
            ]}
          />
          {filteredDocuments.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No documents match these filters.</p>
            </div>
          ) : (
          <div className="table-shell table-scroll">
            <table className="table-base">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>File Name</th>
                  <th>AI Category</th>
                  <th>Assigned Type</th>
                  <th>Owner Role</th>
                  <th>Status</th>
                  <th>Processing Notes</th>
                  <th>Uploaded At</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((doc, index) => (
                  <tr key={doc.id}>
                    <td className="text-ink-500 tabular-nums">{index + 1}</td>
                    <td className="font-medium text-ink-900">
                      <div className="flex items-center gap-2">
                        <File className="w-4 h-4 text-brand-800 shrink-0" />
                        <span>{doc.original_filename}</span>
                      </div>
                    </td>
                    <td>
                      <AICategoryCell
                        doc={doc}
                        onConfirm={can('documents.contribute') ? (category) => handleConfirmCategory(doc, category) : undefined}
                      />
                    </td>
                    <td className="text-xs">
                      {doc.document_type_source === 'none' ? (
                        <span className="text-ink-400">Not assigned</span>
                      ) : (
                        <>
                          <span className="text-ink-600 font-mono">{doc.document_type}</span>
                          <p className="text-ink-400">
                            {doc.document_type_source === 'filename' ? 'Filename match' : 'Chosen at upload'}
                          </p>
                        </>
                      )}
                    </td>
                    <td className="text-ink-600">{doc.owner_role || 'IQAC'}</td>
                    <td>
                      <span className="badge-success">{doc.status}</span>
                    </td>
                    <td>
                      {doc.processing_status === 'unsupported_format' ? (
                        <span className="badge-warning" title={doc.ocr_warnings?.[0]}>
                          Can't read this file type
                        </span>
                      ) : doc.page_count === null ? (
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
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      {(can('documents.manageAll') || doc.uploaded_by === userId) && (
                        <button
                          onClick={() => handleDelete(doc)}
                          disabled={deletingId === doc.id}
                          title="Delete document"
                          className="btn-icon hover:text-danger hover:bg-danger-bg"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
          </>
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
  onStop: () => void;
  driveStopping: boolean;
}> = ({
  driveUrl, setDriveUrl, driveSubmitting, driveError, setDriveError, latestDriveJob, onStart, onStop, driveStopping,
}) => {
  const jobActive = !!latestDriveJob && ACTIVE_DRIVE_IMPORT_STATUSES.includes(latestDriveJob.status);
  const additionalFiles =
    (latestDriveJob?.results?.additional_files as DriveImportAdditionalFile[] | undefined) || [];
  const skippedFiles = (latestDriveJob?.results?.skipped_files as DriveImportSkippedFile[] | undefined) || [];
  const progress = latestDriveJob?.results?.progress as DriveImportProgress | undefined;

  return (
    <div>
      <h2 className="eyebrow mb-2">Import From Google Drive</h2>
      <p className="text-sm text-ink-500 mb-4">
        Paste a folder link and the system scans the folder and all of its subfolders, then imports every
        supported document automatically. Filenames are only a first hint: AI extraction reads each document
        and confirms its category.
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

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={onStart} disabled={driveSubmitting || jobActive} className="btn-primary btn-sm">
            <Link2 className="w-4 h-4" />
            <span>{driveSubmitting ? 'Starting…' : 'Scan & Import'}</span>
          </button>
          {jobActive && (
            <button
              onClick={onStop}
              disabled={driveStopping}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-danger/40 text-danger hover:bg-danger/10 transition-colors disabled:opacity-60"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{driveStopping ? 'Stopping…' : 'Stop Scan'}</span>
            </button>
          )}
        </div>

        {driveError && <InlineError message={driveError} onDismiss={() => setDriveError('')} />}

        {latestDriveJob && (
          <div className="p-4 bg-surface rounded-xl border border-line-200 space-y-3">
            {jobActive && (
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="w-4 h-4 text-brand-800 animate-spin" />
                <span className="badge-brand">{DRIVE_STATUS_LABELS[latestDriveJob.status] || latestDriveJob.status}</span>
              </div>
            )}

            {jobActive && progress && progress.total > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-ink-600">
                  <span>
                    Imported {latestDriveJob.files_imported} · processed {progress.processed} of {progress.total}
                  </span>
                  <span className="tabular-nums">{Math.round((progress.processed / progress.total) * 100)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-line-200 overflow-hidden">
                  <div
                    className="h-full bg-brand-500 transition-all"
                    style={{ width: `${(progress.processed / progress.total) * 100}%` }}
                  />
                </div>
                {progress.current_file && (
                  <p className="text-xs text-ink-500 truncate" title={progress.current_file}>
                    Reading: {progress.current_file}
                  </p>
                )}
              </div>
            )}

            {latestDriveJob.status === 'failed' && (
              <div className="flex items-start gap-2 text-sm">
                <span className="badge-danger shrink-0">Failed</span>
                <span className="text-ink-700">{latestDriveJob.error_message}</span>
              </div>
            )}

            {(latestDriveJob.status === 'completed' || latestDriveJob.status === 'cancelled') && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm">
                  {latestDriveJob.status === 'cancelled' ? (
                    <span className="badge-warning">
                      Stopped — imported {latestDriveJob.files_imported} file
                      {latestDriveJob.files_imported === 1 ? '' : 's'} before stopping
                    </span>
                  ) : (
                    <span className="badge-success">
                      Scanned {latestDriveJob.files_scanned} files, imported {latestDriveJob.files_imported}
                    </span>
                  )}
                </div>

                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-ink-600">Filename matches (hint only, confirmed by AI extraction):</p>
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

                {additionalFiles.length > 0 && (
                  <div className="text-xs text-ink-500">
                    <p className="font-semibold text-ink-600 mb-1">
                      Also imported, AI will categorize these ({additionalFiles.length}):
                    </p>
                    {additionalFiles.map((file) => (
                      <p key={file.document_id} className="truncate">
                        <span className="text-ink-400">{file.folder ? `${file.folder}/` : 'Root/'}</span>
                        {file.filename}
                      </p>
                    ))}
                  </div>
                )}

                {skippedFiles.length > 0 && (
                  <div className="text-xs text-ink-500">
                    <p className="font-semibold text-ink-600 mb-1">Could not be imported:</p>
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

/** The "Processing Notes" column as a filterable value. */
function textCheck(doc: SprintDocument): string {
  if (doc.page_count === null) return 'Pending extraction';
  return doc.ocr_required ? 'Needs OCR' : 'Text OK';
}

type SlotState = 'confirmed' | 'review' | 'awaiting' | 'missing';

const SLOT_DISPLAY: Record<SlotState, { icon: typeof CheckCircle2; className: string; note: string }> = {
  confirmed: { icon: CheckCircle2, className: 'text-success', note: 'Found by AI' },
  review: { icon: HelpCircle, className: 'text-warning', note: 'Needs review' },
  awaiting: { icon: Clock, className: 'text-ink-400', note: 'Awaiting AI check' },
  missing: { icon: AlertCircle, className: 'text-warning', note: '' },
};

/**
 * Where one checklist slot stands. A confident AI category fills it (the
 * backend's AI_CLASSIFICATION_MIN_CONFIDENCE decides "classified"), and so
 * does a category a person confirmed -- shown first when both exist; a
 * low-confidence AI guess needs review; a document the AI hasn't read yet
 * only counts as "awaiting" on the type it was uploaded/imported as.
 */
function checklistSlot(type: string, documents: SprintDocument[]): { state: SlotState; doc?: SprintDocument } {
  const find = (status: ClassificationStatus, matches: (d: SprintDocument) => boolean) =>
    documents.find((d) => d.classification_status === status && matches(d));
  const confirmed = find('classified', (d) => d.ai_document_type === type && !!d.category_confirmed_at)
    || find('classified', (d) => d.ai_document_type === type);
  if (confirmed) return { state: 'confirmed', doc: confirmed };
  const review = find('needs_review', (d) => d.ai_document_type === type);
  if (review) return { state: 'review', doc: review };
  const awaiting = find('pending', (d) => d.document_type === type);
  if (awaiting) return { state: 'awaiting', doc: awaiting };
  return { state: 'missing' };
}

const formatConfidence = (confidence: number) => `${Math.round(confidence * 100)}%`;

/** The "AI Category" column as a filterable value. */
function aiCategoryText(doc: SprintDocument): string {
  switch (doc.classification_status) {
    case 'classified': return doc.ai_document_type_label || doc.ai_document_type;
    case 'needs_review': return 'Needs review';
    case 'unclassified': return doc.category_confirmed_at ? NOT_A_CHECKLIST_DOCUMENT : 'Unclassified';
    default: return 'Not yet categorized';
  }
}

const NOT_A_CHECKLIST_DOCUMENT = 'Not a checklist document';
/** <select> value standing for "Not a checklist document" (sent as null). */
const NONE_VALUE = '__none__';

/**
 * The document's category once AI extraction has read it: a dropdown
 * pre-set to the AI's category (or its low-confidence guess), with the
 * confidence and reasoning under it. Picking another option saves it as a
 * person's decision straight away; on a "Needs review" row the check button
 * accepts the AI's guess as shown. Without `onConfirm` (viewers) it's read-only.
 */
const AICategoryCell: React.FC<{
  doc: SprintDocument;
  onConfirm?: (category: string | null) => Promise<boolean>;
}> = ({ doc, onConfirm }) => {
  // The option being saved, shown in the dropdown until the refetch lands.
  const [savingValue, setSavingValue] = useState<string | null>(null);

  if (doc.classification_status === 'pending') {
    return <span className="text-xs text-ink-400">Not yet categorized</span>;
  }
  const manual = !!doc.category_confirmed_at;
  // A person's decision has no confidence; the AI's figure was for its own guess.
  const confidence = !manual && doc.ai_confidence !== null ? formatConfidence(doc.ai_confidence) : null;
  const differsFromAssigned = doc.classification_status === 'classified'
    && doc.document_type_source !== 'none' && doc.ai_document_type !== doc.document_type;
  const needsReview = !manual && doc.classification_status === 'needs_review';
  const unclassifiedByAI = !manual && doc.classification_status === 'unclassified';
  const reasoning = manual && doc.ai_reasoning ? `AI's earlier reading: ${doc.ai_reasoning}` : doc.ai_reasoning;
  // '' = no category yet (the placeholder option); NONE_VALUE = a person said "none".
  const current = doc.ai_document_type || (manual ? NONE_VALUE : '');

  const save = async (value: string) => {
    if (!onConfirm || !value) return;
    setSavingValue(value);
    await onConfirm(value === NONE_VALUE ? null : value);
    setSavingValue(null);
  };

  return (
    <div className="min-w-[200px] max-w-[260px] space-y-1" title={reasoning || undefined}>
      {onConfirm ? (
        <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          <select
            value={savingValue ?? current}
            onChange={(e) => save(e.target.value)}
            disabled={savingValue !== null}
            aria-label={`Category for ${doc.original_filename}`}
            className={`input py-1.5 px-2 text-xs w-full ${
              needsReview ? 'border-warning-line' : unclassifiedByAI ? 'text-ink-500' : 'text-ink-900'
            }`}
          >
            <option value="" disabled>Unclassified: choose a category…</option>
            {REQUIRED_CHECKLIST.map((item) => (
              <option key={item.type} value={item.type}>{item.label}</option>
            ))}
            <option value={NONE_VALUE}>{NOT_A_CHECKLIST_DOCUMENT}</option>
          </select>
          {needsReview && doc.ai_document_type && (
            <button
              onClick={() => save(doc.ai_document_type)}
              disabled={savingValue !== null}
              className="btn-icon text-success hover:bg-success-bg shrink-0"
              title={`Accept the AI's guess: ${doc.ai_document_type_label}`}
              aria-label={`Accept ${doc.ai_document_type_label} for ${doc.original_filename}`}
            >
              <Check className="w-4 h-4" />
            </button>
          )}
        </div>
      ) : (
        <span className="text-xs font-semibold text-ink-800">
          {doc.classification_status === 'classified'
            ? doc.ai_document_type_label
            : needsReview ? `Possibly ${doc.ai_document_type_label}` : manual ? NOT_A_CHECKLIST_DOCUMENT : 'Unclassified'}
        </span>
      )}

      <div className="flex items-center gap-1.5 flex-wrap text-xs">
        {savingValue !== null ? (
          <span className="text-ink-500">Saving…</span>
        ) : manual ? (
          <span
            className="text-brand-800 flex items-center gap-1"
            title={`Set on ${new Date(doc.category_confirmed_at!).toLocaleString()}. AI reprocessing keeps it.`}
          >
            <UserCheck className="w-3.5 h-3.5 shrink-0" />
            Confirmed by {doc.category_confirmed_by_name || 'a reviewer'}
          </span>
        ) : needsReview ? (
          <span className="badge-warning">Needs review{confidence && ` · ${confidence}`}</span>
        ) : unclassifiedByAI ? (
          <span className="badge-neutral">Unclassified</span>
        ) : (
          confidence && <span className="badge-success">AI {confidence}</span>
        )}
      </div>
      {differsFromAssigned && <p className="text-xs text-warning">Differs from the assigned type</p>}
      {doc.ai_reasoning && !manual && <p className="text-xs text-ink-400 truncate">{doc.ai_reasoning}</p>}
    </div>
  );
};
