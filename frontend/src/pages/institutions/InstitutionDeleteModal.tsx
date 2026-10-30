import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileText,
  FolderArchive,
  Layers,
  Loader2,
  Lock,
  RefreshCw,
  ShieldAlert,
  Trash2,
  X,
} from 'lucide-react';
import type { Institution } from '../../types';
import {
  archiveInstitution,
  deleteInstitution,
  getInstitutionDeletionPreview,
  type InstitutionDeletionPreview,
} from '../../api/institutions';
import { getErrorMessage } from '../../utils/errors';

export interface InstitutionDeleteModalProps {
  institution: Institution | null;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const InstitutionDeleteModal: React.FC<InstitutionDeleteModalProps> = ({
  institution,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<InstitutionDeletionPreview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [confirmedName, setConfirmedName] = useState('');

  useEffect(() => {
    if (!isOpen || !institution) {
      setPreview(null);
      setPreviewError('');
      setActionError('');
      setConfirmedName('');
      return;
    }

    let active = true;
    setLoading(true);
    setPreviewError('');
    setActionError('');
    setConfirmedName('');

    getInstitutionDeletionPreview(institution.id)
      .then((res) => {
        if (active) {
          setPreview(res.data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setPreviewError(getErrorMessage(err, 'Could not inspect institution dependencies.'));
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isOpen, institution]);

  if (!isOpen || !institution) return null;

  const handleArchive = async () => {
    setActionBusy(true);
    setActionError('');
    try {
      await archiveInstitution(institution.id);
      onSuccess();
      onClose();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to archive institution.'));
    } finally {
      setActionBusy(false);
    }
  };

  const handleDelete = async () => {
    setActionBusy(true);
    setActionError('');
    try {
      await deleteInstitution(institution.id);
      onSuccess();
      onClose();
    } catch (err: any) {
      // If 409 Conflict occurred (e.g. race condition), update error and refresh preview
      const errorMsg = getErrorMessage(err, `Could not delete "${institution.name}".`);
      setActionError(errorMsg);
      // Reload preview to display the updated blockers
      try {
        const refreshed = await getInstitutionDeletionPreview(institution.id);
        setPreview(refreshed.data);
      } catch {
        // preserve existing view
      }
    } finally {
      setActionBusy(false);
    }
  };

  const isBlocked = preview ? preview.is_blocked || !preview.can_delete : true;
  const isNameConfirmed = preview && !isBlocked ? confirmedName.trim() === institution.name.trim() : false;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/60 backdrop-blur-xs overflow-y-auto"
    >
      <div className="relative w-full max-w-xl bg-card border border-line-200 rounded-2xl shadow-xl overflow-hidden transition-all my-8">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-line-200 bg-surface/50">
          <div className="flex items-center gap-2.5">
            <div className={`p-2 rounded-lg ${isBlocked ? 'bg-amber-500/10 text-amber-600' : 'bg-danger-bg text-danger'}`}>
              {isBlocked ? <ShieldAlert className="w-5 h-5" /> : <Trash2 className="w-5 h-5" />}
            </div>
            <div>
              <h2 id="delete-dialog-title" className="text-base sm:text-lg font-bold text-ink-900">
                {isBlocked ? 'Institution Deletion Policy' : 'Confirm Permanent Deletion'}
              </h2>
              <p className="text-xs text-ink-500 truncate max-w-sm sm:max-w-md">
                {institution.name}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={actionBusy}
            className="btn-icon text-ink-500 hover:text-ink-900"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 sm:p-6 space-y-4">
          {actionError && (
            <div role="alert" className="p-3 rounded-lg border border-danger-line bg-danger-bg text-danger text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">{actionError}</div>
            </div>
          )}

          {loading ? (
            <div className="py-8 flex flex-col items-center justify-center gap-3 text-ink-500">
              <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
              <span className="text-sm">Inspecting institution dependencies and audit history…</span>
            </div>
          ) : previewError ? (
            <div className="p-4 rounded-xl border border-danger-line bg-danger-bg text-danger text-sm flex flex-col gap-2">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle className="w-4 h-4" />
                <span>Unable to load dependency preview</span>
              </div>
              <p className="text-xs">{previewError}</p>
              <button
                type="button"
                onClick={() => {
                  setLoading(true);
                  setPreviewError('');
                  getInstitutionDeletionPreview(institution.id)
                    .then((res) => {
                      setPreview(res.data);
                      setLoading(false);
                    })
                    .catch((err) => {
                      setPreviewError(getErrorMessage(err));
                      setLoading(false);
                    });
                }}
                className="btn-secondary btn-sm self-start mt-1 flex items-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry</span>
              </button>
            </div>
          ) : preview && isBlocked ? (
            /* BLOCKED STATE */
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-amber-300 dark:border-amber-800/60 bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 text-sm space-y-2">
                <div className="flex items-center gap-2 font-bold text-amber-800 dark:text-amber-300">
                  <Lock className="w-4 h-4" />
                  <span>Permanent Deletion Blocked</span>
                </div>
                <p className="text-xs sm:text-sm text-ink-700 dark:text-ink-300 leading-relaxed">
                  {preview.block_reason ||
                    'This institution is linked to active discovery sprints, uploaded evidence, or historical audit records. Permanent deletion is blocked to protect historical audit lineage and evidence records.'}
                </p>
              </div>

              {/* Dependency Counts Breakdown */}
              <div className="border border-line-200 rounded-xl p-4 bg-surface/30 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink-600">
                  Protected Dependency Records
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Discovery Sprints</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.sprints}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Sprint Documents</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.documents}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Extracted Facts</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.facts}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Evidence Submissions</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.evidence_submissions}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Gaps & Baselines</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.gaps + preview.dependencies.baselines}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-line-200 bg-card">
                    <span className="text-ink-500 block text-[11px]">Benchmark & Audit Logs</span>
                    <span className="text-base font-bold text-ink-900">
                      {preview.dependencies.audit_records + preview.dependencies.benchmark_cycles}
                    </span>
                  </div>
                </div>
              </div>

              {/* Supported Alternative */}
              <div className="p-4 rounded-xl border border-brand-500/30 bg-brand-50/50 dark:bg-brand-950/20 text-xs text-ink-700 dark:text-ink-300 space-y-1.5">
                <span className="font-bold text-brand-800 dark:text-brand-300 flex items-center gap-1.5">
                  <Archive className="w-3.5 h-3.5" />
                  Supported Alternative: Archive / Deactivate
                </span>
                <p className="leading-relaxed">
                  Deactivating "{institution.name}" hides it from active discovery workflows and institution selectors while preserving all historical documents, audit records, and scores.
                </p>
              </div>
            </div>
          ) : preview && !isBlocked ? (
            /* SAFE TO DELETE STATE */
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-success-line bg-success-bg text-success text-sm space-y-1.5">
                <div className="flex items-center gap-2 font-bold">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>No Protected Records Found — Safe to Delete</span>
                </div>
                <p className="text-xs text-ink-700 leading-relaxed">
                  This institution has no sprints, uploaded documents, extracted facts, or assessment evidence.
                </p>
              </div>

              {/* Removable DNA records */}
              <div className="border border-line-200 rounded-xl p-3.5 bg-surface/30 space-y-2 text-xs">
                <span className="font-semibold text-ink-700 block">
                  The following baseline DNA data will be permanently removed:
                </span>
                <ul className="list-disc pl-5 space-y-1 text-ink-600">
                  <li>{preview.dependencies.departments} Academic Departments</li>
                  <li>{preview.dependencies.leaders} Leadership records</li>
                  <li>{preview.dependencies.systems} IT Systems</li>
                </ul>
              </div>

              <div className="p-3.5 rounded-xl border border-danger-line bg-danger-bg text-xs text-danger space-y-2">
                <span className="font-bold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Explicit Confirmation Required
                </span>
                <p>
                  To confirm permanent deletion, please type the institution name{' '}
                  <strong className="select-all underline font-mono">{institution.name}</strong> below:
                </p>
                <input
                  type="text"
                  value={confirmedName}
                  onChange={(e) => setConfirmedName(e.target.value)}
                  placeholder={`Type "${institution.name}"`}
                  className="input text-xs w-full bg-card"
                  disabled={actionBusy}
                  data-testid="confirm-institution-name-input"
                />
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer Actions */}
        <div className="p-4 sm:p-5 border-t border-line-200 bg-surface/50 flex flex-wrap items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={actionBusy}
            className="btn-secondary text-xs"
          >
            Cancel
          </button>

          {preview && isBlocked && (
            <button
              type="button"
              onClick={handleArchive}
              disabled={actionBusy}
              className="btn-primary text-xs flex items-center gap-1.5 font-semibold"
            >
              {actionBusy ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Archiving…</span>
                </>
              ) : (
                <>
                  <FolderArchive className="w-3.5 h-3.5" />
                  <span>Archive Institution</span>
                </>
              )}
            </button>
          )}

          {preview && !isBlocked && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={actionBusy || !isNameConfirmed}
              className="btn-danger text-xs flex items-center gap-1.5 font-semibold"
              data-testid="execute-permanent-delete-btn"
            >
              {actionBusy ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Deleting Permanently…</span>
                </>
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Permanently Delete</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

