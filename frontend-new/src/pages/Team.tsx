import { useState } from 'react';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table, type DialogField } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { getRoleAccessMatrix } from '../services/auth';
import { listInstitutions } from '../services/institutions';
import { createUser, deactivateUser, listUsers, permanentlyDeleteUser, previewUserDeletion, updateUser } from '../services/users';
import type { AdminUser, Institution, RoleAccessDefinition } from '../types/api';
import type { UserDeletionPreview, UserPayload } from '../types/workflow';
import { ROLE_LABELS } from '../utils/access';

type Dialog = { kind: 'create' } | { kind: 'edit'; user: AdminUser } | { kind: 'delete'; user: AdminUser; preview: UserDeletionPreview };

export function Team() {
  const { can, role, user: me } = useAccess();
  const superAdmin = role === 'super_admin';
  const users = useResource<AdminUser[]>(listUsers, 'users', can('users.manage'));
  const matrix = useResource<{ roles: RoleAccessDefinition[] }>(getRoleAccessMatrix, 'access-matrix');
  const institutions = useResource<Institution[]>(listInstitutions, 'institutions', superAdmin);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const { busy, msg, setMsg, run } = useRunner();

  // IQAC Coordinators may only assign their own role, inside their own college (server-enforced too).
  const roleOptions = (superAdmin ? Object.entries(ROLE_LABELS) : [['iqac_coordinator', ROLE_LABELS.iqac_coordinator]])
    .map(([value, label]) => ({ value, label }));

  const fields = (u?: AdminUser): DialogField[] => [
    ...(u ? [] : [{ name: 'email', label: 'Email', type: 'email' as const, required: true }]),
    { name: 'first_name', label: 'First name', initial: u?.first_name || '', required: true },
    { name: 'last_name', label: 'Last name', initial: u?.last_name || '' },
    { name: 'phone', label: 'Phone', initial: u?.phone || '' },
    { name: 'role', label: 'Role', type: 'select', required: true, options: roleOptions, initial: u?.role || (superAdmin ? '' : 'iqac_coordinator') },
    ...(superAdmin ? [{
      name: 'institution_id', label: 'Institution (blank = all institutions, InGage staff)', type: 'select' as const,
      options: (institutions.data || []).map((i) => ({ value: i.id, label: i.name })), initial: u?.institution_id || '',
    }] : []),
    { name: 'department_name', label: 'Department', initial: u?.department_name || '' },
    { name: 'password', label: u ? 'New password (leave blank to keep)' : 'Initial password', type: 'password', required: !u },
  ];

  const payload = (v: Record<string, string>): UserPayload => {
    const p: UserPayload = {
      first_name: v.first_name, last_name: v.last_name, phone: v.phone, role: v.role, department_name: v.department_name,
    };
    if (v.email) p.email = v.email;
    if (superAdmin) p.institution_id = v.institution_id || null;
    if (v.password) p.password = v.password;
    return p;
  };

  const askDelete = (u: AdminUser) => run(`preview:${u.id}`, async () => {
    const res = await previewUserDeletion(u.id);
    setDialog({ kind: 'delete', user: u, preview: res.data });
  });

  return (
    <>
      <PageHeading page="team" actions={can('users.manage') && (
        <button className="primary-action" onClick={() => setDialog({ kind: 'create' })}>Add person</button>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {can('users.manage') && (
        users.loading ? <Loading /> : users.error ? <ErrorState error={users.error} onRetry={() => void users.refetch()} /> :
          !users.data?.length ? <Empty title="No people yet" /> : (
            <Table columns={['Person', 'Role', 'Institution', 'Department', 'Status', '']}>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.full_name || u.email}</strong><small className="cell-sub">{u.email}</small></td>
                  <td>{u.role_label}</td>
                  <td>{u.institution_name || 'All institutions'}</td>
                  <td>{u.department_name || '—'}</td>
                  <td><Pill status={u.is_active ? 'active' : 'blocked'} label={u.is_active ? 'Active' : 'Deactivated'} /></td>
                  <td>
                    <div className="row-actions nowrap">
                      <button className="secondary-button" onClick={() => setDialog({ kind: 'edit', user: u })}>Edit</button>
                      {u.id !== me?.id && (u.is_active ? (
                        <button className="secondary-button" disabled={!!busy} onClick={() => void run(`off:${u.id}`, async () => { await deactivateUser(u.id); await users.refetch(); }, `${u.email} deactivated.`)}>Deactivate</button>
                      ) : (
                        <button className="secondary-button" disabled={!!busy} onClick={() => void run(`on:${u.id}`, async () => { await updateUser(u.id, { is_active: true }); await users.refetch(); }, `${u.email} reactivated.`)}>Reactivate</button>
                      ))}
                      {superAdmin && u.id !== me?.id && (
                        <button className="secondary-button" disabled={!!busy} onClick={() => void askDelete(u)}>Delete…</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )
      )}
      <h2 className="section-title">Roles and access</h2>
      {matrix.loading ? <Loading /> : matrix.error ? <ErrorState error={matrix.error} onRetry={() => void matrix.refetch()} /> : (
        <div className="feature-grid">
          {matrix.data!.roles.map((r) => (
            <Panel key={r.role} title={r.name} sub={r.institution_scope}>
              <p className="muted">{r.description}</p>
              <ul className="plain-list">{r.modules.slice(0, 8).map((m) => <li key={m.name}><b>{m.name}</b>: {m.access}</li>)}</ul>
            </Panel>
          ))}
        </div>
      )}

      {dialog?.kind === 'create' && (
        <ActionDialog title="Add a person" confirmLabel="Create" fields={fields()}
          onSubmit={async (v) => { await createUser(payload(v)); await users.refetch(); setMsg({ tone: 'success', text: `${v.email} created.` }); }}
          onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'edit' && (
        <ActionDialog title={`Edit ${dialog.user.full_name || dialog.user.email}`} confirmLabel="Save" fields={fields(dialog.user)}
          onSubmit={async (v) => { await updateUser(dialog.user.id, payload(v)); await users.refetch(); setMsg({ tone: 'success', text: 'Saved.' }); }}
          onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'delete' && (
        <ActionDialog
          title={`Permanently delete ${dialog.user.email}?`}
          danger
          confirmLabel="Delete permanently"
          description={dialog.preview.can_delete ? (
            <p>This cannot be undone. Deactivating keeps the account for the audit trail instead.</p>
          ) : (
            <>
              <Notice tone="warn">{dialog.preview.detail || 'Records still reference this person, so it cannot be deleted. Deactivate instead.'}</Notice>
              <ul className="plain-list">{dialog.preview.dependencies.map((d) => <li key={`${d.model}.${d.field}`}>{d.model} · {d.field}: {d.count}</li>)}</ul>
            </>
          )}
          fields={dialog.preview.can_delete ? [{ name: 'reason', label: 'Reason (kept in the audit log)', type: 'textarea', required: true }] : []}
          onSubmit={async (v) => {
            if (!dialog.preview.can_delete) throw new Error('This person cannot be deleted while records reference them.');
            await permanentlyDeleteUser(dialog.user.id, v.reason);
            await users.refetch();
            setMsg({ tone: 'success', text: `${dialog.user.email} deleted.` });
          }}
          onClose={() => setDialog(null)} />
      )}
    </>
  );
}
