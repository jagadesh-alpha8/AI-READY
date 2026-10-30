import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, Mail, Plus, RotateCcw, Trash2, User, X } from 'lucide-react';

import {
  createInstitution,
  listInstitutions,
  unarchiveInstitution,
} from '../../api/institutions';
import { useApiResource } from '../../hooks/useApiResource';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { CreateInstitutionPayload, Institution } from '../../types';
import { canDo } from '../../utils/access';
import { InstitutionDeleteModal } from './InstitutionDeleteModal';

// Who may create / delete a college: utils/access.ts ('institution.edit', the
// backend's WRITE_INSTITUTION_ROLES, and the narrower 'institution.delete' --
// deleting a college takes every sprint, document, fact, score and report
// scoped to it down with it).

/** All fields for the "Add new institution" form. coordinator_name and
 * coordinator_email are required by the backend: the create endpoint atomically
 * creates the institution AND sends the coordinator an activation email.
 * The rest of the DNA — headcounts, departments, digital maturity — is filled
 * in on the Institution DNA page, which is where this form navigates after success. */
const BLANK_FORM = {
  name: '',
  coordinator_name: '',
  coordinator_email: '',
  institution_type: '',
  city: '',
  state: '',
  affiliation: '',
  accreditation_status: '',
  website_url: '',
} satisfies Required<CreateInstitutionPayload>;

type FormField = keyof typeof BLANK_FORM;

/** Per-field backend validation errors returned by the create endpoint (DRF format). */
type FieldErrors = Partial<Record<FormField, string>>;

/** Landing page for Institution DNA: pick an institution here before editing
 * anything about it. Creating and deleting both live on this list rather than
 * inside a specific institution's workspace, since they act on the
 * institution as a whole rather than any one field of its profile. */
export const InstitutionList: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canDelete = canDo(user?.role, 'institution.delete');
  // Creating a college names and invites its IQAC Coordinator: InGage staff only (backend CREATE_INSTITUTION_ROLES).
  // A college's own coordinator edits its basic information on the DNA page, never the coordinator or invitations.
  const canCreate = canDo(user?.role, 'institution.create');

  const { data: institutions, loading, error, refetch } =
    useApiResource<Institution[]>(() => listInstitutions(), []);

  const [deleteModalInstitution, setDeleteModalInstitution] = useState<Institution | null>(null);
  const [deleteError, setDeleteError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(BLANK_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const setField = (field: FormField, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    // Clear field-level error as the user corrects the value.
    if (fieldErrors[field]) setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const openForm = () => {
    setForm(BLANK_FORM);
    setCreateError('');
    setFieldErrors({});
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setCreateError('');
    setFieldErrors({});
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name || creating) return;

    // Client-side required-field check for the coordinator fields, so the user
    // gets instant feedback without a round trip.
    const clientErrors: FieldErrors = {};
    if (!form.coordinator_name.trim()) clientErrors.coordinator_name = "Enter the IQAC Coordinator's name.";
    if (!form.coordinator_email.trim()) clientErrors.coordinator_email = "Enter the IQAC Coordinator's email address.";
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setCreating(true);
    setCreateError('');
    setFieldErrors({});
    try {
      // coordinator_name and coordinator_email are always included — they are
      // required by the backend. Blank optional profile fields are omitted so
      // they look identical to fields that were never filled in.
      const payload: CreateInstitutionPayload = {
        name,
        coordinator_name: form.coordinator_name.trim(),
        coordinator_email: form.coordinator_email.trim(),
      };
      (Object.keys(BLANK_FORM) as FormField[]).forEach((field) => {
        if (field === 'name' || field === 'coordinator_name' || field === 'coordinator_email') return;
        const value = form[field].trim();
        if (value) payload[field] = value;
      });

      const { data } = await createInstitution(payload);
      // Straight into the new institution's DNA: creating one here is always
      // the first step of filling it in, never the end of the task.
      navigate(`/institution-dna/${data.id}`);
    } catch (err: unknown) {
      // DRF returns field errors as { coordinator_name: ["msg"], ... }.
      // Surface them next to the correct fields instead of as a banner.
      const resp = (err as { response?: { data?: unknown } })?.response?.data;
      if (resp && typeof resp === 'object' && !Array.isArray(resp)) {
        const drfErrors = resp as Record<string, unknown>;
        const extracted: FieldErrors = {};
        let hasFieldError = false;
        (Object.keys(BLANK_FORM) as FormField[]).forEach((field) => {
          const msgs = drfErrors[field];
          if (Array.isArray(msgs) && msgs.length > 0) {
            extracted[field] = String(msgs[0]);
            hasFieldError = true;
          } else if (typeof msgs === 'string' && msgs) {
            extracted[field] = msgs;
            hasFieldError = true;
          }
        });
        if (hasFieldError) {
          setFieldErrors(extracted);
          setCreating(false);
          return;
        }
      }
      setCreateError(getErrorMessage(err, 'Could not create the institution.'));
      setCreating(false);
    }
  };

  const handleDelete = (inst: Institution) => {
    setDeleteError('');
    setDeleteModalInstitution(inst);
  };

  const handleUnarchive = async (inst: Institution) => {
    setDeleteError('');
    try {
      await unarchiveInstitution(inst.id);
      await refetch();
    } catch (err) {
      setDeleteError(getErrorMessage(err, `Could not reactivate "${inst.name}".`));
    }
  };

  if (loading) return <LoadingState message="Loading institutions…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  // Deletion is a hard delete now, so `is_active` should never go false
  // through this page — the flag only lingers from institutions removed
  // before this change. The Status column stays out of the way once there's
  // nothing left for it to explain.
  const hasInactive = !!institutions?.some((inst) => !inst.is_active);

  return (
    <div className="space-y-6">
      <div data-tour="institution-dna-header" className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-800 shrink-0">
            <Building2 className="w-6 h-6" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 truncate">Institution DNA</h1>
            <p className="text-sm text-ink-500">
              Pick an institution to review or edit the baseline every discovery sprint is measured against.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
          {canCreate && !showForm && (
            <button
              type="button"
              data-tour="institution-add-btn"
              onClick={openForm}
              className="btn-primary btn-sm shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add institution</span>
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-card p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="eyebrow">Add new institution</h2>
              <p className="text-sm text-ink-500 mt-0.5">
                Institution name and IQAC Coordinator details are required. The coordinator will
                receive an email invitation to activate their account. The rest of the DNA is filled
                in on the next screen.
              </p>
            </div>
            <button type="button" onClick={closeForm} aria-label="Cancel" className="btn-icon shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>

          {createError && <InlineError message={createError} onDismiss={() => setCreateError('')} />}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Institution name — full width */}
            <div className="sm:col-span-2">
              <label className="label" htmlFor="new-institution-name">
                Institution name <span className="text-danger">*</span>
              </label>
              <input
                id="new-institution-name"
                type="text"
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
                className={`input${fieldErrors.name ? ' border-danger' : ''}`}
                placeholder="e.g. Sri Venkateswara College of Engineering"
                autoFocus
                required
                aria-describedby={fieldErrors.name ? 'err-name' : undefined}
              />
              {fieldErrors.name && (
                <p id="err-name" className="mt-1 text-xs text-danger">{fieldErrors.name}</p>
              )}
            </div>

            {/* IQAC Coordinator section — required, full width, visually grouped */}
            <div className="sm:col-span-2">
              <div className="rounded-lg border border-brand-500/30 bg-brand-500/5 p-4 space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-ink-700">
                  <User className="w-4 h-4 text-brand-600 shrink-0" />
                  <span>IQAC Coordinator <span className="text-danger">*</span></span>
                  <span className="text-xs font-normal text-ink-400 ml-1">
                    — invited by email immediately after the institution is created
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="label" htmlFor="new-coordinator-name">
                      Full name <span className="text-danger">*</span>
                    </label>
                    <input
                      id="new-coordinator-name"
                      type="text"
                      value={form.coordinator_name}
                      onChange={(e) => setField('coordinator_name', e.target.value)}
                      className={`input${fieldErrors.coordinator_name ? ' border-danger' : ''}`}
                      placeholder="e.g. Dr. S. Meenakshi"
                      required
                      aria-describedby={fieldErrors.coordinator_name ? 'err-coord-name' : undefined}
                    />
                    {fieldErrors.coordinator_name && (
                      <p id="err-coord-name" className="mt-1 text-xs text-danger">
                        {fieldErrors.coordinator_name}
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="label" htmlFor="new-coordinator-email">
                      <Mail className="inline w-3.5 h-3.5 mr-1 align-text-bottom text-ink-400" />
                      Email address <span className="text-danger">*</span>
                    </label>
                    <input
                      id="new-coordinator-email"
                      type="email"
                      value={form.coordinator_email}
                      onChange={(e) => setField('coordinator_email', e.target.value)}
                      className={`input${fieldErrors.coordinator_email ? ' border-danger' : ''}`}
                      placeholder="e.g. iqac@college.ac.in"
                      required
                      aria-describedby={fieldErrors.coordinator_email ? 'err-coord-email' : undefined}
                    />
                    {fieldErrors.coordinator_email && (
                      <p id="err-coord-email" className="mt-1 text-xs text-danger">
                        {fieldErrors.coordinator_email}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Optional profile fields */}
            <Field
              label="Type"
              value={form.institution_type}
              onChange={(value) => setField('institution_type', value)}
              placeholder="e.g. Engineering College"
            />
            <Field
              label="Affiliation"
              value={form.affiliation}
              onChange={(value) => setField('affiliation', value)}
              placeholder="e.g. Anna University"
            />
            <Field label="City" value={form.city} onChange={(value) => setField('city', value)} />
            <Field label="State" value={form.state} onChange={(value) => setField('state', value)} />
            <Field
              label="Accreditation"
              value={form.accreditation_status}
              onChange={(value) => setField('accreditation_status', value)}
              placeholder="e.g. NAAC A+"
            />
            <Field
              label="Website"
              value={form.website_url}
              onChange={(value) => setField('website_url', value)}
              type="url"
              placeholder="https://"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={creating || !form.name.trim() || !form.coordinator_name.trim() || !form.coordinator_email.trim()}
              className="btn-primary btn-sm"
            >
              {creating ? 'Creating…' : 'Create institution'}
            </button>
            <button type="button" onClick={closeForm} disabled={creating} className="btn-ghost btn-sm">
              Cancel
            </button>
          </div>
        </form>
      )}

      {deleteError && <InlineError message={deleteError} onDismiss={() => setDeleteError('')} />}

      {!institutions || institutions.length === 0 ? (
        <EmptyState
          message={
            canCreate
              ? 'No institutions yet. One has to exist before its DNA can be recorded.'
              : 'No institutions yet. One has to exist before its DNA can be recorded — a super admin, consultant or institution admin creates the first.'
          }
          action={canCreate && !showForm ? { label: 'Add institution', onClick: openForm } : undefined}
        />
      ) : (
        <div data-tour="institution-dna-table" className="table-shell">
          <table className="table-base">
            <thead>
              <tr>
                <th>Institution</th>
                <th>Type</th>
                <th>Location</th>
                <th>Sprints</th>
                <th>Students</th>
                {hasInactive && <th>Status</th>}
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {institutions.map((inst) => (
                <tr key={inst.id}>
                  <td className="font-semibold text-ink-900">{inst.name}</td>
                  <td className="text-ink-600">{inst.institution_type || '—'}</td>
                  <td className="text-ink-600">
                    {[inst.city, inst.state].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="text-ink-600">{inst.sprint_count}</td>
                  <td className="text-ink-600">
                    {inst.student_count != null ? inst.student_count.toLocaleString() : '—'}
                  </td>
                  {hasInactive && (
                    <td>
                      {!inst.is_active && <span className="badge badge-neutral">Inactive</span>}
                    </td>
                  )}
                  <td className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      {!inst.is_active && canDelete && (
                        <button
                          type="button"
                          onClick={() => handleUnarchive(inst)}
                          aria-label={`Reactivate ${inst.name}`}
                          title="Reactivate institution"
                          className="btn-ghost btn-sm text-brand-700 hover:text-brand-900 flex items-center gap-1"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span className="text-xs">Activate</span>
                        </button>
                      )}
                      {canDelete && (
                        <button
                          type="button"
                          onClick={() => handleDelete(inst)}
                          aria-label={`Delete ${inst.name}`}
                          title="Delete or Archive institution"
                          className="btn-icon hover:text-danger hover:bg-danger-bg"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => navigate(`/institution-dna/${inst.id}`)}
                        className="btn-secondary btn-sm ml-1"
                      >
                        <span>Manage</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Dependency Preview and Deletion / Archive Modal */}
      <InstitutionDeleteModal
        institution={deleteModalInstitution}
        isOpen={!!deleteModalInstitution}
        onClose={() => setDeleteModalInstitution(null)}
        onSuccess={() => refetch()}
      />
    </div>
  );
};

const Field: React.FC<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
}> = ({ label, value, onChange, type = 'text', placeholder }) => (
  <div>
    <label className="label">{label}</label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="input"
      placeholder={placeholder}
    />
  </div>
);
