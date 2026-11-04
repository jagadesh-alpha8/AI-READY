import { Empty, ErrorState, Loading, PageHeading, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getRoleAccessMatrix } from '../services/auth';
import { listUsers } from '../services/users';
import type { AdminUser, RoleAccessDefinition } from '../types/api';

export function Team() {
  const { can } = useAccess();
  const users = useResource<AdminUser[]>(listUsers, 'users', can('users.manage'));
  const matrix = useResource<{ roles: RoleAccessDefinition[] }>(getRoleAccessMatrix, 'access-matrix');

  return (
    <>
      <PageHeading page="team" />
      {can('users.manage') && (
        users.loading ? <Loading /> : users.error ? <ErrorState error={users.error} onRetry={() => void users.refetch()} /> :
          !users.data?.length ? <Empty title="No people yet" /> : (
            <Table columns={['Person', 'Role', 'Institution', 'Department', 'Status']}>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.full_name || u.email}</strong><small className="cell-sub">{u.email}</small></td>
                  <td>{u.role_label}</td>
                  <td>{u.institution_name || 'All institutions'}</td>
                  <td>{u.department_name || '—'}</td>
                  <td><Pill status={u.is_active ? 'active' : 'blocked'} label={u.is_active ? 'Active' : 'Deactivated'} /></td>
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
    </>
  );
}
