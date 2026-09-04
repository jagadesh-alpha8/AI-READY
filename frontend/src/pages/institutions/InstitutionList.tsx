import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, Plus, Trash2, X } from 'lucide-react';

import { createInstitution, deleteInstitution, listInstitutions } from '../../api/institutions';
import { useApiResource } from '../../hooks/useApiResource';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { CreateInstitutionPayload, Institution } from '../../types';

/** Roles allowed to delete an institution outright — mirrors the backend's
 * DELETE_INSTITUTION_ROLES. Narrower than the roles that can edit an
 * institution's DNA, because deleting the institution itself takes every
 * sprint, document, fact, gap, score, recommendation and report scoped to it
 * down with it. */
const DELETE_ROLES = ['super_admin', 'consultant'];

/** Roles allowed to create an institution — mirrors the backend's
 * WRITE_INSTITUTION_ROLES, so it is wider than DELETE_ROLES. The server is
 * still the authority; this only decides whether to offer an action that
 * would otherwise come back a 403. */
const CREATE_ROLES = ['super_admin', 'consultant', 'institution_admin'];

/** Only `name` is required. The rest are the fields the create endpoint
 * accepts; everything else about an institution — headcounts, priorities,
 * leadership, departments, digital maturity — is edited on its DNA page,
 * which is where this form lands you. */
const BLANK_FORM: Required<CreateInstitutionPayload> = {
  name: '',
  institution_type: '',
  city: '',
  state: '',
  affiliation: '',
  accreditation_status: '',
  website_url: '',
};

type FormField = keyof typeof BLANK_FORM;

/** Landing page for Institution DNA: pick an institution here before editing
 * anything about it. Creating and deleting both live on this list rather than
 * inside a specific institution's workspace, since they act on the
 * institution as a whole rather than any one field of its profile. */
export const InstitutionList: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canDelete = !!user && DELETE_ROLES.includes(user.role);
  const canCreate = !!user && CREATE_ROLES.includes(user.role);

  const { data: institutions, loading, error, refetch } =
    useApiResource<Institution[]>(() => listInstitutions(), []);

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(BLANK_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  const setField = (field: FormField, value: string) =>
    setForm((current) => ({ ...current, [field]: value }));

  const openForm = () => {
    setForm(BLANK_FORM);
    setCreateError('');
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setCreateError('');
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name || creating) return;

    setCreating(true);
    setCreateError('');
    try {
      // Blank optional fields are left out of the payload rather than posted
      // as empty strings, so an institution created here is indistinguishable
      // from one whose optional fields were never typed at all.
      const payload: CreateInstitutionPayload = { name };
      (Object.keys(BLANK_FORM) as FormField[]).forEach((field) => {
        const value = form[field].trim();
        if (field !== 'name' && value) payload[field] = value;
      });

      const { data } = await createInstitution(payload);
      // Straight into the new institution's DNA: creating one here is always
      // the first step of filling it in, never the end of the task.
      navigate(`/institution-dna/${data.id}`);
    } catch (err) {
      setCreateError(getErrorMessage(err, 'Could not create the institution.'));
      setCreating(false);
    }
  };

  const handleDelete = async (inst: Institution) => {
    if (
      !window.confirm(
        `Delete "${inst.name}"? This permanently removes the institution and everything scoped to it — departments, leadership, systems, sprints, uploaded documents, extracted facts, gaps, scores and reports. This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingId(inst.id);
    setDeleteError('');
    try {
      await deleteInstitution(inst.id);
      await refetch();
    } catch (err) {
      setDeleteError(getErrorMessage(err, `Could not delete "${inst.name}".`));
    } finally {
      setDeletingId(null);
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
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
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
        {canCreate && !showForm && (
          <button
            type="button"
            onClick={openForm}
            className="btn-primary btn-sm shrink-0 self-start sm:self-auto"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add institution</span>
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-card p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="eyebrow">Add new institution</h2>
              <p className="text-sm text-ink-500 mt-0.5">
                Only the name is required — the rest of the DNA is filled in on the next screen.
              </p>
            </div>
            <button type="button" onClick={closeForm} aria-label="Cancel" className="btn-icon shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>

          {createError && <InlineError message={createError} onDismiss={() => setCreateError('')} />}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="new-institution-name">
                Institution name <span className="text-danger">*</span>
              </label>
              <input
                id="new-institution-name"
                type="text"
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
                className="input"
                placeholder="e.g. Sri Venkateswara College of Engineering"
                autoFocus
                required
              />
            </div>
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
            <button type="submit" disabled={creating || !form.name.trim()} className="btn-primary btn-sm">
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
        <div className="table-shell">
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
                      {canDelete && (
                        <button
                          type="button"
                          onClick={() => handleDelete(inst)}
                          disabled={deletingId === inst.id}
                          aria-label={`Delete ${inst.name}`}
                          title="Delete institution"
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
