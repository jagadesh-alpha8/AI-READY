import React, { useMemo, useState } from 'react';
import { Check, Plus, RotateCcw, UserCog, UserX, X } from 'lucide-react';

import { createUser, deactivateUser, listUsers, updateUser } from '../../api/users';
import type { AdminUser, UserPayload } from '../../api/users';
import { listInstitutions } from '../../api/institutions';
import { useApiResource } from '../../hooks/useApiResource';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { FilterPills } from '../../components/PageHeader';
import type { Institution } from '../../types';

/**
 * User administration. Mirrors the rules the server enforces in
 * `apps/accounts/user_admin.py` — the UI only decides what to *offer*; every
 * one of these is re-checked server-side, and a request that slips past the
 * form is still refused.
 */

/** The eleven roles on `User.Role`, in the order a person would read them. */
const ROLES: { value: string; label: string; platform?: boolean }[] = [
  { value: 'super_admin', label: 'Super Admin', platform: true },
  { value: 'consultant', label: 'InGage Consultant', platform: true },
  { value: 'institution_admin', label: 'Institution Admin' },
  { value: 'iqac_coordinator', label: 'IQAC Coordinator' },
  { value: 'registrar', label: 'Registrar' },
  { value: 'hod', label: 'Head of Department' },
  { value: 'hr_officer', label: 'HR Officer' },
  { value: 'lab_admin', label: 'Lab Admin' },
  { value: 'placement_officer', label: 'Placement Officer' },
  { value: 'faculty', label: 'Faculty' },
  { value: 'viewer', label: 'Viewer' },
];

const BLANK: UserPayload = {
  email: '', username: '', first_name: '', last_name: '', phone: '',
  role: 'viewer', department_name: '', password: '',
};

type Filter = 'all' | 'active' | 'inactive';

export const UsersTab: React.FC = () => {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === 'super_admin';

  const { data: users, loading, error, refetch } = useApiResource<AdminUser[]>(() => listUsers(), []);
  const { data: institutions } = useApiResource<Institution[]>(
    () => listInstitutions(), [], isSuperAdmin,
  );

  const [filter, setFilter] = useState<Filter>('all');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<UserPayload>(BLANK);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [listError, setListError] = useState('');

  // An institution admin cannot grant a platform-wide role. The server
  // refuses it either way; hiding it stops someone picking an option that
  // can only fail.
  const assignableRoles = useMemo(
    () => (isSuperAdmin ? ROLES : ROLES.filter((r) => !r.platform)),
    [isSuperAdmin],
  );

  const rows = (users ?? []).filter((u) =>
    filter === 'all' ? true : filter === 'active' ? u.is_active : !u.is_active);

  const setField = (key: keyof UserPayload, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const openCreate = () => {
    setForm(BLANK); setEditingId(null); setFormError(''); setShowForm(true);
  };

  const openEdit = (u: AdminUser) => {
    setForm({
      email: u.email, username: u.username, first_name: u.first_name, last_name: u.last_name,
      phone: u.phone, role: u.role, department_name: u.department_name,
      institution_id: u.institution_id, password: '',
    });
    setEditingId(u.id); setFormError(''); setShowForm(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setFormError('');
    try {
      const payload: UserPayload = { ...form };
      // An empty password on an edit means "leave it alone", not "set it to
      // empty string" — sending it would fail validation for no reason.
      if (!payload.password) delete payload.password;
      if (editingId) await updateUser(editingId, payload);
      else await createUser(payload);
      setShowForm(false); setForm(BLANK); setEditingId(null);
      await refetch();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Could not save the user.'));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (u: AdminUser) => {
    setListError('');
    try {
      if (u.is_active) {
        if (!window.confirm(
          `Deactivate ${u.full_name || u.email}? They will not be able to sign in. `
          + 'Their record stays, so anything they reviewed or approved still names them.',
        )) return;
        await deactivateUser(u.id);
      } else {
        await updateUser(u.id, { is_active: true });
      }
      await refetch();
    } catch (err) {
      setListError(getErrorMessage(err, 'Could not change that account.'));
    }
  };

  if (loading) return <LoadingState message="Loading users…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <p className="text-sm text-ink-500 min-w-0">
          {isSuperAdmin
            ? 'Every user on the platform, across all institutions.'
            : 'Users in your institution. Platform-wide roles are managed by InGage.'}
        </p>
        {!showForm && (
          <button type="button" onClick={openCreate} className="btn-primary btn-sm shrink-0">
            <Plus className="w-3.5 h-3.5" />
            <span>Add user</span>
          </button>
        )}
      </div>

      {listError && <InlineError message={listError} onDismiss={() => setListError('')} />}

      {showForm && (
        <form onSubmit={submit} className="glass-card p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <h3 className="eyebrow">{editingId ? 'Edit user' : 'Add user'}</h3>
            <button type="button" onClick={() => setShowForm(false)} aria-label="Cancel" className="btn-icon">
              <X className="w-4 h-4" />
            </button>
          </div>

          {formError && <InlineError message={formError} onDismiss={() => setFormError('')} />}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input label="Email" type="email" value={form.email || ''} onChange={(v) => setField('email', v)} required />
            <Input label="Username" value={form.username || ''} onChange={(v) => setField('username', v)} required />
            <Input label="First name" value={form.first_name || ''} onChange={(v) => setField('first_name', v)} />
            <Input label="Last name" value={form.last_name || ''} onChange={(v) => setField('last_name', v)} />

            <div>
              <label className="label" htmlFor="user-role">Role</label>
              <select
                id="user-role" value={form.role} required className="input"
                onChange={(e) => setField('role', e.target.value)}
              >
                {assignableRoles.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            {isSuperAdmin && (
              <div>
                <label className="label" htmlFor="user-institution">Institution</label>
                <select
                  id="user-institution" value={form.institution_id || ''} className="input"
                  onChange={(e) => setForm((f) => ({ ...f, institution_id: e.target.value || null }))}
                >
                  <option value="">None — platform staff</option>
                  {(institutions ?? []).map((inst) => (
                    <option key={inst.id} value={inst.id}>{inst.name}</option>
                  ))}
                </select>
              </div>
            )}

            <Input label="Department" value={form.department_name || ''} onChange={(v) => setField('department_name', v)} />
            <Input label="Phone" value={form.phone || ''} onChange={(v) => setField('phone', v)} />

            <div className="sm:col-span-2">
              <label className="label" htmlFor="user-password">
                {editingId ? 'New password' : 'Password'}
                {editingId && <span className="font-normal text-ink-500"> — leave blank to keep the current one</span>}
              </label>
              <input
                id="user-password" type="password" value={form.password || ''} className="input"
                autoComplete="new-password" required={!editingId}
                onChange={(e) => setField('password', e.target.value)}
              />
            </div>
          </div>

          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="btn-primary btn-sm">
              {busy ? 'Saving…' : editingId ? 'Save changes' : 'Create user'}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={busy} className="btn-ghost btn-sm">
              Cancel
            </button>
          </div>
        </form>
      )}

      <FilterPills
        options={[
          { id: 'all', label: 'All', count: (users ?? []).length },
          { id: 'active', label: 'Active', count: (users ?? []).filter((u) => u.is_active).length },
          { id: 'inactive', label: 'Deactivated', count: (users ?? []).filter((u) => !u.is_active).length },
        ]}
        active={filter}
        onChange={setFilter}
      />

      {rows.length === 0 ? (
        <EmptyState message="No users match that filter." />
      ) : (
        <div className="table-shell">
          <table className="table-base">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Institution</th>
                <th>Status</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => {
                const isMe = u.id === me?.id;
                return (
                  <tr key={u.id}>
                    <td>
                      <p className="font-semibold text-ink-900">{u.full_name || u.username}</p>
                      <p className="text-xs text-ink-500">{u.email}</p>
                    </td>
                    <td className="text-ink-600 whitespace-nowrap">{u.role_label}</td>
                    <td className="text-ink-600">{u.institution_name || '—'}</td>
                    <td>
                      <span className={`badge ${u.is_active ? 'badge-success' : 'badge-neutral'}`}>
                        {u.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </td>
                    <td className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button" onClick={() => openEdit(u)}
                          className="btn-secondary btn-sm" title="Edit"
                        >
                          <UserCog className="w-3.5 h-3.5" />
                        </button>
                        {/* Deactivating yourself would lock you out, so the
                            server refuses it and the button is not offered. */}
                        {!isMe && (
                          <button
                            type="button" onClick={() => toggleActive(u)}
                            className={`btn-icon ${u.is_active ? 'hover:text-danger hover:bg-danger-bg' : 'hover:text-success'}`}
                            title={u.is_active ? 'Deactivate' : 'Reactivate'}
                            aria-label={u.is_active ? `Deactivate ${u.email}` : `Reactivate ${u.email}`}
                          >
                            {u.is_active ? <UserX className="w-4 h-4" /> : <RotateCcw className="w-4 h-4" />}
                          </button>
                        )}
                        {isMe && (
                          <span className="badge badge-brand ml-1">
                            <Check className="w-3 h-3" /> You
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-ink-500">
        Deactivating keeps the record: fact reviews, baseline decisions and uploaded documents all
        name their user, and an audit trail that resolves to nothing is not an audit trail.
      </p>
    </div>
  );
};

const Input: React.FC<{
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
}> = ({ label, value, onChange, type = 'text', required }) => (
  <div>
    <label className="label">{label}{required && ' *'}</label>
    <input
      type={type} value={value} required={required} className="input"
      onChange={(e) => onChange(e.target.value)}
    />
  </div>
);
