import { useState, type FormEvent } from 'react';
import { Dummy, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { changePassword } from '../services/auth';
import { http } from '../services/http';
import { getScoringConfig } from '../services/scoring';
import { API_BASE_URL } from '../config/env';
import type { PillarConfig } from '../types/api';
import { roleLabel } from '../utils/access';
import { errorMessage } from '../utils/errors';
import { num } from '../utils/format';

export function Settings() {
  const { user } = useAccess();
  const rubric = useResource<PillarConfig[]>(getScoringConfig, 'rubric');
  const health = useResource<{ status: string; database?: string; cache?: string }>(() => http.get('/health'), 'health');

  return (
    <>
      <PageHeading page="admin" />
      <div className="content-grid">
        <Panel title="My account">
          <dl className="kv">
            <dt>Name</dt><dd>{user?.name || '—'}</dd>
            <dt>Email</dt><dd>{user?.email}</dd>
            <dt>Role</dt><dd>{roleLabel(user?.role)}</dd>
          </dl>
          <PasswordForm />
        </Panel>
        <Panel title="Service status" sub={`API ${API_BASE_URL}`}>
          {health.loading ? <Loading /> : health.error ? <ErrorState error={health.error} title="The backend health check failed" onRetry={() => void health.refetch()} /> : (
            <dl className="kv">
              <dt>API</dt><dd><Pill status={health.data!.status === 'ok' ? 'ready' : 'failed'} label={health.data!.status} /></dd>
              <dt>Database</dt><dd>{health.data!.database || '—'}</dd>
              <dt>Cache</dt><dd>{health.data!.cache || '—'}</dd>
            </dl>
          )}
        </Panel>
      </div>
      <h2 className="section-title">Scoring rubric (read-only)</h2>
      {rubric.loading ? <Loading /> : rubric.error ? <ErrorState error={rubric.error} onRetry={() => void rubric.refetch()} /> : (
        <Table columns={['Pillar', 'Weight', 'Criteria', 'Active']}>
          {rubric.data!.map((p) => (
            <tr key={p.key}><td><strong>{p.name}</strong><small className="cell-sub">{p.description}</small></td><td>{num(p.weight, 2)}</td><td>{p.criteria.length}</td><td>{p.is_active ? 'Yes' : 'No'}</td></tr>
          ))}
        </Table>
      )}
      <Dummy title="Organisation, integrations, data governance and audit settings" note="Managed in Django admin and server configuration; the API exposes no settings endpoints.">
        <div className="feature-grid">
          {[['Organisation settings', 'Brand, customer hierarchy, terminology and regional configuration.'],
            ['Identity and access', 'Roles, permissions, authentication, sessions and access reviews.'],
            ['AI and processing', 'Approved models, budgets, extraction protocols and human review controls.'],
            ['Integrations', 'Storage, SIS, LMS, HRMS, email, analytics and secure APIs.'],
            ['Data governance', 'Retention, consent, encryption, residency and deletion policies.'],
            ['Audit and monitoring', 'Immutable activity logs, health diagnostics, incidents and service status.']].map(([t, d], i) => (
            <article key={t} className="feature-card muted-card"><div className="feature-icon">{String(i + 1).padStart(2, '0')}</div><h3>{t}</h3><p>{d}</p></article>
          ))}
        </div>
      </Dummy>
    </>
  );
}

function PasswordForm() {
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const res = await changePassword(oldPw, newPw);
      setMsg({ tone: 'success', text: res.data.detail || 'Password updated.' });
      setOldPw('');
      setNewPw('');
    } catch (err) { setMsg({ tone: 'error', text: errorMessage(err) }); } finally { setBusy(false); }
  };
  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="field"><span>Current password</span><input type="password" autoComplete="current-password" required value={oldPw} onChange={(e) => setOldPw(e.target.value)} /></label>
      <label className="field"><span>New password</span><input type="password" autoComplete="new-password" required value={newPw} onChange={(e) => setNewPw(e.target.value)} /></label>
      {msg && <div className="span-2"><Notice tone={msg.tone}>{msg.text}</Notice></div>}
      <button className="secondary-button span-2" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
    </form>
  );
}
