import React, { useState } from 'react';
import {
  Building2, Users, Server, Plus, Pencil, Trash2, Check, X, Info,
} from 'lucide-react';

import {
  createDepartment,
  createLeader,
  createSystem,
  deleteDepartment,
  deleteLeader,
  deleteSystem,
  getInstitution,
  listDepartments,
  listInstitutions,
  listSystems,
  updateDepartment,
  updateInstitution,
  updateSystem,
} from '../../api/institutions';
import { useApiResource } from '../../hooks/useApiResource';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type {
  Department,
  Institution,
  InstitutionDetail,
  InstitutionSystem,
  InstitutionSystemTag,
} from '../../types';

/** Roles allowed to write institution DNA — mirrors the backend's
 * WRITE_INSTITUTION_ROLES. The server is still the authority; this only
 * decides whether to *offer* an action that would otherwise 403. */
const WRITE_ROLES = ['super_admin', 'consultant', 'institution_admin'];

const TABS = [
  { key: 'profile', label: 'Institution Profile' },
  { key: 'departments', label: 'Departments' },
  { key: 'systems', label: 'Systems & IT' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

/** Mirrors Institution.DigitalMaturity on the backend. */
const MATURITY_LEVELS = [
  { value: 1, label: 'Level 1 — Manual' },
  { value: 2, label: 'Level 2 — Partial Digital' },
  { value: 3, label: 'Level 3 — Integrated' },
  { value: 4, label: 'Level 4 — Data-Driven' },
  { value: 5, label: 'Level 5 — AI-Enabled' },
];

const SYSTEM_TAGS: { value: InstitutionSystemTag; label: string }[] = [
  { value: '', label: 'No tag' },
  { value: 'legacy', label: 'Legacy' },
  { value: 'manual', label: 'Manual' },
];

/** An unset count reads as "not recorded", never as zero. */
function displayCount(value: number | null): string {
  return value === null || value === undefined ? '—' : value.toLocaleString();
}

function toCount(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : null;
}

export const InstitutionDNA: React.FC = () => {
  const { user } = useAuth();
  const canEdit = !!user && WRITE_ROLES.includes(user.role);

  const { data: institutions, loading: listLoading, error: listError, refetch: refetchList } =
    useApiResource<Institution[]>(() => listInstitutions(), []);

  const [selectedId, setSelectedId] = useState('');
  const activeId = selectedId || institutions?.[0]?.id || '';

  const {
    data: institution,
    loading,
    error,
    refetch,
  } = useApiResource<InstitutionDetail>(() => getInstitution(activeId), [activeId], !!activeId);

  const [tab, setTab] = useState<TabKey>('profile');

  if (listLoading) return <LoadingState message="Loading institutions…" />;
  if (listError) return <ErrorState message={listError} onRetry={refetchList} />;

  if (!institutions || institutions.length === 0) {
    return (
      <EmptyState message="No institutions yet. One has to exist before its DNA can be recorded — a super admin or consultant creates the first." />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-800 shrink-0">
            <Building2 className="w-6 h-6" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 truncate">Institution DNA</h1>
            <p className="text-sm text-ink-500">
              The institutional baseline every discovery sprint is measured against.
            </p>
          </div>
        </div>

        {institutions.length > 1 && (
          <select
            value={activeId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="input sm:ml-auto sm:w-auto"
            aria-label="Select institution"
          >
            {institutions.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={tab === item.key ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading && <LoadingState message="Loading institution…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && institution && (
        <>
          {tab === 'profile' && (
            <ProfileTab institution={institution} canEdit={canEdit} onSaved={refetch} />
          )}
          {tab === 'departments' && (
            <DepartmentsTab institutionId={institution.id} canEdit={canEdit} onChanged={refetch} />
          )}
          {tab === 'systems' && (
            <SystemsTab institution={institution} canEdit={canEdit} onSaved={refetch} />
          )}
        </>
      )}
    </div>
  );
};

// ---------------------------------------------------------------- profile ---

const ProfileTab: React.FC<{
  institution: InstitutionDetail;
  canEdit: boolean;
  onSaved: () => void;
}> = ({ institution, canEdit, onSaved }) => {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    name: institution.name,
    institution_type: institution.institution_type,
    location: [institution.city, institution.state].filter(Boolean).join(', '),
    accreditation_details: institution.accreditation_details,
    student_count: institution.student_count?.toString() ?? '',
    faculty_count: institution.faculty_count?.toString() ?? '',
  });

  const [priorities, setPriorities] = useState<string[]>(institution.priorities || []);
  const [newPriority, setNewPriority] = useState('');

  const startEditing = () => {
    setForm({
      name: institution.name,
      institution_type: institution.institution_type,
      location: [institution.city, institution.state].filter(Boolean).join(', '),
      accreditation_details: institution.accreditation_details,
      student_count: institution.student_count?.toString() ?? '',
      faculty_count: institution.faculty_count?.toString() ?? '',
    });
    setPriorities(institution.priorities || []);
    setError('');
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      // "Bengaluru, Karnataka" is one field to the reader but two columns to
      // the database; split on the last comma so a city containing one
      // ("Washington, D.C.") still lands in the right column.
      const [city, state] = splitLocation(form.location);
      await updateInstitution(institution.id, {
        name: form.name.trim(),
        institution_type: form.institution_type.trim(),
        city,
        state,
        accreditation_details: form.accreditation_details.trim(),
        student_count: toCount(form.student_count),
        faculty_count: toCount(form.faculty_count),
        priorities,
      });
      setEditing(false);
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not save the institution profile.'));
    } finally {
      setSaving(false);
    }
  };

  const rows: { label: string; value: string; derived?: boolean }[] = [
    { label: 'Institution', value: institution.name },
    { label: 'Type', value: institution.institution_type || '—' },
    {
      label: 'Location',
      value: [institution.city, institution.state].filter(Boolean).join(', ') || '—',
    },
    { label: 'Accreditation', value: institution.accreditation_details || '—' },
    { label: 'Students', value: displayCount(institution.student_count) },
    { label: 'Faculty', value: displayCount(institution.faculty_count) },
    { label: 'Departments', value: institution.department_count.toLocaleString(), derived: true },
    { label: 'Programs', value: institution.program_count.toLocaleString(), derived: true },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="glass-card p-5 sm:p-6 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-ink-900">Basic Information</h2>
          {canEdit && !editing && (
            <button type="button" onClick={startEditing} className="btn btn-outline btn-sm">
              <Pencil className="w-3.5 h-3.5" /> Edit
            </button>
          )}
        </div>

        {error && <InlineError message={error} onDismiss={() => setError('')} />}

        {editing ? (
          <div className="space-y-3">
            <Field label="Institution" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Field
              label="Type"
              value={form.institution_type}
              onChange={(v) => setForm({ ...form, institution_type: v })}
            />
            <Field
              label="Location (City, State)"
              value={form.location}
              onChange={(v) => setForm({ ...form, location: v })}
            />
            <Field
              label="Accreditation"
              value={form.accreditation_details}
              onChange={(v) => setForm({ ...form, accreditation_details: v })}
            />
            <div className="grid grid-cols-2 gap-3">
              <Field
                label="Students"
                value={form.student_count}
                onChange={(v) => setForm({ ...form, student_count: v })}
                type="number"
              />
              <Field
                label="Faculty"
                value={form.faculty_count}
                onChange={(v) => setForm({ ...form, faculty_count: v })}
                type="number"
              />
            </div>

            <p className="flex items-start gap-1.5 text-xs text-ink-500">
              <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
              <span>
                Departments and Programs are counted from the Departments tab, so they are not
                editable here.
              </span>
            </p>

            <PriorityEditor
              priorities={priorities}
              newPriority={newPriority}
              setNewPriority={setNewPriority}
              onAdd={() => {
                const label = newPriority.trim();
                if (label && !priorities.includes(label)) setPriorities([...priorities, label]);
                setNewPriority('');
              }}
              onRemove={(label) => setPriorities(priorities.filter((p) => p !== label))}
            />

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setEditing(false)} className="btn-secondary btn-sm">
                Cancel
              </button>
              <button type="button" onClick={save} disabled={saving} className="btn-primary btn-sm">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <dl className="divide-y divide-line-200">
            {rows.map((row) => (
              <div key={row.label} className="flex items-baseline justify-between gap-4 py-2.5">
                <dt className="text-sm text-ink-500 shrink-0">
                  {row.label}
                  {row.derived && (
                    <span className="ml-1.5 text-[10px] uppercase tracking-wide text-ink-400">
                      derived
                    </span>
                  )}
                </dt>
                <dd className="text-sm font-semibold text-ink-900 text-right">{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <div className="space-y-6">
        <LeadershipCard institution={institution} canEdit={canEdit} onChanged={onSaved} />

        {!editing && (
          <div className="glass-card p-5 sm:p-6">
            <h2 className="text-lg font-bold text-ink-900 mb-3">Priorities</h2>
            {institution.priorities?.length ? (
              <div className="flex flex-wrap gap-2">
                {institution.priorities.map((priority) => (
                  <span key={priority} className="badge badge-info">
                    {priority}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-500">
                No priorities recorded yet{canEdit ? ' — add them from Edit.' : '.'}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const Field: React.FC<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}> = ({ label, value, onChange, type = 'text' }) => (
  <div>
    <label className="label">{label}</label>
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className="input" />
  </div>
);

const PriorityEditor: React.FC<{
  priorities: string[];
  newPriority: string;
  setNewPriority: (value: string) => void;
  onAdd: () => void;
  onRemove: (label: string) => void;
}> = ({ priorities, newPriority, setNewPriority, onAdd, onRemove }) => (
  <div>
    <label className="label">Priorities</label>
    <div className="flex flex-wrap gap-2 mb-2">
      {priorities.map((priority) => (
        <span key={priority} className="badge badge-info inline-flex items-center gap-1">
          {priority}
          <button
            type="button"
            onClick={() => onRemove(priority)}
            aria-label={`Remove ${priority}`}
            className="hover:text-danger"
          >
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
    </div>
    <div className="flex gap-2">
      <input
        type="text"
        value={newPriority}
        onChange={(e) => setNewPriority(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            onAdd();
          }
        }}
        placeholder="e.g. NAAC Re-accreditation 2025"
        className="input"
      />
      <button type="button" onClick={onAdd} className="btn btn-outline btn-sm shrink-0">
        <Plus className="w-3.5 h-3.5" /> Add
      </button>
    </div>
  </div>
);

const LeadershipCard: React.FC<{
  institution: InstitutionDetail;
  canEdit: boolean;
  onChanged: () => void;
}> = ({ institution, canEdit, onChanged }) => {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const add = async () => {
    if (!name.trim() || !role.trim()) {
      setError('A name and a role are both required.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await createLeader(institution.id, {
        name: name.trim(),
        role: role.trim(),
        email: email.trim(),
      });
      setName('');
      setRole('');
      setEmail('');
      setAdding(false);
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not add that person.'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await deleteLeader(institution.id, id);
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not remove that person.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-card p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-lg font-bold text-ink-900">Leadership</h2>
        {canEdit && !adding && (
          <button type="button" onClick={() => setAdding(true)} className="btn btn-outline btn-sm">
            <Plus className="w-3.5 h-3.5" /> Add
          </button>
        )}
      </div>

      {error && <InlineError message={error} onDismiss={() => setError('')} />}

      {institution.leaders.length === 0 && !adding && (
        <p className="text-sm text-ink-500">No leadership recorded yet.</p>
      )}

      <ul className="divide-y divide-line-200">
        {institution.leaders.map((leader) => (
          <li key={leader.id} className="flex items-center gap-3 py-3">
            <span className="w-10 h-10 shrink-0 rounded-full bg-brand-500/15 text-brand-800 text-xs font-bold flex items-center justify-center">
              {leader.initials}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink-900 truncate">{leader.name}</p>
              <p className="text-xs text-ink-500 truncate">
                {leader.role}
                {leader.email && ` · ${leader.email}`}
              </p>
            </div>
            {canEdit && (
              <button
                type="button"
                onClick={() => remove(leader.id)}
                disabled={busy}
                aria-label={`Remove ${leader.name}`}
                className="btn-icon hover:text-danger"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </li>
        ))}
      </ul>

      {adding && (
        <div className="space-y-3 pt-3 border-t border-line-200 mt-3">
          <Field label="Name" value={name} onChange={setName} />
          <Field label="Role" value={role} onChange={setRole} />
          <Field label="Email" value={email} onChange={setEmail} type="email" />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setAdding(false)} className="btn-secondary btn-sm">
              Cancel
            </button>
            <button type="button" onClick={add} disabled={busy} className="btn-primary btn-sm">
              {busy ? 'Adding…' : 'Add'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

/** "Bengaluru, Karnataka" -> ["Bengaluru", "Karnataka"]. Splits on the LAST
 * comma so a city that contains one keeps it. */
function splitLocation(value: string): [string, string] {
  const index = value.lastIndexOf(',');
  if (index < 0) return [value.trim(), ''];
  return [value.slice(0, index).trim(), value.slice(index + 1).trim()];
}

// ------------------------------------------------------------ departments ---

const BLANK_DEPARTMENT = {
  name: '',
  head_name: '',
  faculty_count: '0',
  student_count: '0',
  program_count: '0',
};

const DepartmentsTab: React.FC<{
  institutionId: string;
  canEdit: boolean;
  onChanged: () => void;
}> = ({ institutionId, canEdit, onChanged }) => {
  const { data, loading, error, refetch } = useApiResource<Department[]>(
    () => listDepartments(institutionId),
    [institutionId],
  );

  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ ...BLANK_DEPARTMENT });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const departments = data || [];

  const openAdd = () => {
    setForm({ ...BLANK_DEPARTMENT });
    setEditingId(null);
    setFormError('');
    setAdding(true);
  };

  const openEdit = (department: Department) => {
    setForm({
      name: department.name,
      head_name: department.head_name,
      faculty_count: String(department.faculty_count),
      student_count: String(department.student_count),
      program_count: String(department.program_count),
    });
    setAdding(false);
    setFormError('');
    setEditingId(department.id);
  };

  const submit = async () => {
    if (!form.name.trim()) {
      setFormError('A department name is required.');
      return;
    }
    setBusy(true);
    setFormError('');
    const payload = {
      name: form.name.trim(),
      head_name: form.head_name.trim(),
      faculty_count: toCount(form.faculty_count) ?? 0,
      student_count: toCount(form.student_count) ?? 0,
      program_count: toCount(form.program_count) ?? 0,
    };
    try {
      if (editingId) {
        await updateDepartment(institutionId, editingId, payload);
      } else {
        await createDepartment(institutionId, payload);
      }
      setAdding(false);
      setEditingId(null);
      refetch();
      // The profile tab's derived department/programme counts change with this.
      onChanged();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not save that department.'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (department: Department) => {
    setBusy(true);
    try {
      await deleteDepartment(institutionId, department.id);
      refetch();
      onChanged();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not remove that department.'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState message="Loading departments…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <div className="space-y-4">
      {formError && <InlineError message={formError} onDismiss={() => setFormError('')} />}

      {canEdit && !adding && !editingId && (
        <div className="flex justify-end">
          <button type="button" onClick={openAdd} className="btn btn-outline btn-sm">
            <Plus className="w-3.5 h-3.5" /> Add department
          </button>
        </div>
      )}

      {(adding || editingId) && (
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-bold text-ink-900">
            {editingId ? 'Edit department' : 'New department'}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Field
              label="Head"
              value={form.head_name}
              onChange={(v) => setForm({ ...form, head_name: v })}
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field
              label="Faculty"
              type="number"
              value={form.faculty_count}
              onChange={(v) => setForm({ ...form, faculty_count: v })}
            />
            <Field
              label="Students"
              type="number"
              value={form.student_count}
              onChange={(v) => setForm({ ...form, student_count: v })}
            />
            <Field
              label="Programs"
              type="number"
              value={form.program_count}
              onChange={(v) => setForm({ ...form, program_count: v })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setEditingId(null);
              }}
              className="btn-secondary btn-sm"
            >
              Cancel
            </button>
            <button type="button" onClick={submit} disabled={busy} className="btn-primary btn-sm">
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {departments.length === 0 && !adding ? (
        <EmptyState
          message="No departments recorded. Add them so their faculty, student and programme counts feed the profile."
          action={canEdit ? { label: 'Add department', onClick: openAdd } : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {departments.map((department) => (
            <div key={department.id} className="glass-card p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-base font-bold text-ink-900 truncate">{department.name}</h3>
                  <p className="text-xs text-ink-500 mt-0.5 truncate">
                    {department.head_name ? `Head: ${department.head_name}` : 'No head recorded'}
                  </p>
                </div>
                {canEdit && (
                  <div className="flex shrink-0">
                    <button
                      type="button"
                      onClick={() => openEdit(department)}
                      aria-label={`Edit ${department.name}`}
                      className="btn-icon"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(department)}
                      disabled={busy}
                      aria-label={`Remove ${department.name}`}
                      className="btn-icon hover:text-danger"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-3 gap-2 mt-4">
                <Stat value={department.faculty_count} label="Faculty" />
                <Stat value={department.student_count} label="Students" />
                <Stat value={department.program_count} label="Programs" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ value: number; label: string }> = ({ value, label }) => (
  <div className="rounded-lg bg-surface border border-line-200 py-2.5 text-center">
    <p className="text-lg font-bold text-ink-900 leading-none">{value.toLocaleString()}</p>
    <p className="text-[11px] text-ink-500 mt-1">{label}</p>
  </div>
);

// ---------------------------------------------------------------- systems ---

const SystemsTab: React.FC<{
  institution: InstitutionDetail;
  canEdit: boolean;
  onSaved: () => void;
}> = ({ institution, canEdit, onSaved }) => {
  const { data, loading, error, refetch } = useApiResource<InstitutionSystem[]>(
    () => listSystems(institution.id),
    [institution.id],
  );

  const [maturity, setMaturity] = useState(institution.digital_maturity_level?.toString() ?? '');
  const [aiUsage, setAiUsage] = useState(institution.current_ai_usage);
  const [savingProfile, setSavingProfile] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<{ name: string; tag: InstitutionSystemTag; notes: string }>({
    name: '',
    tag: '',
    notes: '',
  });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const systems = data || [];
  const dirty =
    maturity !== (institution.digital_maturity_level?.toString() ?? '') ||
    aiUsage !== institution.current_ai_usage;

  const saveProfile = async () => {
    setSavingProfile(true);
    setFormError('');
    try {
      await updateInstitution(institution.id, {
        digital_maturity_level: maturity ? Number(maturity) : null,
        current_ai_usage: aiUsage.trim(),
      });
      onSaved();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not save the maturity assessment.'));
    } finally {
      setSavingProfile(false);
    }
  };

  const submitSystem = async () => {
    if (!form.name.trim()) {
      setFormError('A system name is required.');
      return;
    }
    setBusy(true);
    setFormError('');
    const payload = { name: form.name.trim(), tag: form.tag, notes: form.notes.trim() };
    try {
      if (editingId) {
        await updateSystem(institution.id, editingId, payload);
      } else {
        await createSystem(institution.id, payload);
      }
      setForm({ name: '', tag: '', notes: '' });
      setAdding(false);
      setEditingId(null);
      refetch();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not save that system.'));
    } finally {
      setBusy(false);
    }
  };

  const removeSystem = async (system: InstitutionSystem) => {
    setBusy(true);
    try {
      await deleteSystem(institution.id, system.id);
      refetch();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not remove that system.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-card p-5 sm:p-6 space-y-5">
      <h2 className="text-lg font-bold text-ink-900">Current Systems &amp; Digital Maturity</h2>

      {formError && <InlineError message={formError} onDismiss={() => setFormError('')} />}

      {/* Digital maturity */}
      <div className="rounded-xl border border-warning-line bg-warning-bg p-4">
        {canEdit ? (
          <div className="space-y-2">
            <label className="label">Digital Maturity</label>
            <select
              value={maturity}
              onChange={(e) => setMaturity(e.target.value)}
              className="input"
            >
              <option value="">Not assessed</option>
              {MATURITY_LEVELS.map((level) => (
                <option key={level.value} value={level.value}>
                  {level.label}
                </option>
              ))}
            </select>
            {institution.digital_maturity_description && (
              <p className="text-sm text-ink-600">{institution.digital_maturity_description}</p>
            )}
          </div>
        ) : (
          <>
            <p className="font-bold text-ink-900">
              {institution.digital_maturity_label || 'Digital maturity not assessed'}
            </p>
            {institution.digital_maturity_description && (
              <p className="text-sm text-ink-600 mt-1">
                {institution.digital_maturity_description}
              </p>
            )}
          </>
        )}
      </div>

      {/* Systems list */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h3 className="eyebrow flex items-center gap-2">
            <Server className="w-4 h-4 text-brand-800" /> Systems
          </h3>
          {canEdit && !adding && !editingId && (
            <button
              type="button"
              onClick={() => {
                setForm({ name: '', tag: '', notes: '' });
                setAdding(true);
              }}
              className="btn btn-outline btn-sm"
            >
              <Plus className="w-3.5 h-3.5" /> Add system
            </button>
          )}
        </div>

        {loading && <LoadingState message="Loading systems…" />}
        {error && <ErrorState message={error} onRetry={refetch} />}

        {!loading && !error && systems.length === 0 && !adding && (
          <p className="text-sm text-ink-500 py-2">No systems recorded yet.</p>
        )}

        {systems.map((system) => (
          <div
            key={system.id}
            className="flex items-center gap-3 rounded-lg bg-surface border border-line-200 px-3 py-2.5"
          >
            <Server className="w-4 h-4 shrink-0 text-ink-500" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink-900 truncate">
                {system.name}
                {system.tag && (
                  <span
                    className={`ml-2 badge ${
                      system.tag === 'legacy' ? 'badge-danger' : 'badge-warning'
                    }`}
                  >
                    {system.tag_label}
                  </span>
                )}
              </p>
              {system.notes && <p className="text-xs text-ink-500 truncate">{system.notes}</p>}
            </div>
            {canEdit && (
              <div className="flex shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setForm({ name: system.name, tag: system.tag, notes: system.notes });
                    setAdding(false);
                    setEditingId(system.id);
                  }}
                  aria-label={`Edit ${system.name}`}
                  className="btn-icon"
                >
                  <Pencil className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => removeSystem(system)}
                  disabled={busy}
                  aria-label={`Remove ${system.name}`}
                  className="btn-icon hover:text-danger"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        ))}

        {(adding || editingId) && (
          <div className="rounded-lg border border-line-200 p-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="md:col-span-2">
                <Field
                  label="System"
                  value={form.name}
                  onChange={(v) => setForm({ ...form, name: v })}
                />
              </div>
              <div>
                <label className="label">Tag</label>
                <select
                  value={form.tag}
                  onChange={(e) => setForm({ ...form, tag: e.target.value as InstitutionSystemTag })}
                  className="input"
                >
                  {SYSTEM_TAGS.map((tag) => (
                    <option key={tag.value} value={tag.value}>
                      {tag.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <Field
              label="Notes"
              value={form.notes}
              onChange={(v) => setForm({ ...form, notes: v })}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setAdding(false);
                  setEditingId(null);
                }}
                className="btn-secondary btn-sm"
              >
                Cancel
              </button>
              <button type="button" onClick={submitSystem} disabled={busy} className="btn-primary btn-sm">
                {busy ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Current AI usage */}
      <div className="rounded-xl border border-info-line bg-info-bg p-4 space-y-2">
        <h3 className="font-bold text-ink-900">Current AI Usage</h3>
        {canEdit ? (
          <textarea
            value={aiUsage}
            onChange={(e) => setAiUsage(e.target.value)}
            rows={3}
            placeholder="e.g. Limited — some faculty use AI assistants for research. No institutional AI policy."
            className="input"
          />
        ) : (
          <p className="text-sm text-ink-600">
            {institution.current_ai_usage || 'Not recorded yet.'}
          </p>
        )}
      </div>

      {canEdit && dirty && (
        <div className="flex justify-end">
          <button type="button" onClick={saveProfile} disabled={savingProfile} className="btn-primary btn-sm">
            <Check className="w-3.5 h-3.5" />
            {savingProfile ? 'Saving…' : 'Save assessment'}
          </button>
        </div>
      )}

      {canEdit && !dirty && (
        <p className="flex items-start gap-1.5 text-xs text-ink-500">
          <Users className="w-3.5 h-3.5 shrink-0 mt-px" />
          <span>Maturity and AI usage save together; systems save as you add them.</span>
        </p>
      )}
    </div>
  );
};
