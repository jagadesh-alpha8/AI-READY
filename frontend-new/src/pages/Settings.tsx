import { useState, type FormEvent } from 'react';
import { ErrorState, Loading, Notice, PageHeading, Panel, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { changePassword } from '../services/auth';
import { http } from '../services/http';
import { getScoringConfig } from '../services/scoring';
import { getPlatformAIUsage } from '../services/sprints';
import { API_BASE_URL } from '../config/env';
import type { PillarConfig } from '../types/api';
import type { PlatformAIUsage } from '../types/workflow';
import { roleLabel } from '../utils/access';
import { errorMessage } from '../utils/errors';
import { num } from '../utils/format';

export function Settings() {
  const { user, can } = useAccess();
  const rubric = useResource<PillarConfig[]>(getScoringConfig, 'rubric');
  const usage = useResource<PlatformAIUsage>(() => getPlatformAIUsage(), 'ai-usage', can('ai.usage'));
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
      {can('ai.usage') && (
        <Panel title="AI and processing" sub="Model usage and cost across all colleges (GET /extraction-jobs/usage-report)">
          {usage.loading ? <Loading /> : usage.error ? <ErrorState error={usage.error} onRetry={() => void usage.refetch()} /> : usage.data && (
            <>
              <div className="stat-grid">
                <Stat label="AI requests" value={usage.data.calls.toLocaleString()} note={usage.data.unpriced_calls ? `${usage.data.unpriced_calls} without a price` : 'All priced'} />
                <Stat label="Tokens" value={usage.data.total_tokens.toLocaleString()} note={`${usage.data.input_tokens.toLocaleString()} in · ${usage.data.output_tokens.toLocaleString()} out`} />
                <Stat label="Cost" value={`$${Number(usage.data.cost_usd).toFixed(2)}`} note="Priced requests only" />
                <Stat label="Billing rows" value={usage.data.rows.length} note="College × sprint × month" />
              </div>
              {usage.data.rows.length > 0 && (
                <Table columns={['Month', 'Institution', 'Sprint', 'Documents', 'Requests', 'Cost']}>
                  {[...usage.data.rows].sort((a, b) => b.month.localeCompare(a.month)).slice(0, 12).map((r, i) => (
                    <tr key={`${r.month}-${r.sprint}-${i}`}>
                      <td>{r.month}</td><td>{r.institution}</td><td>{r.sprint}</td><td>{r.documents}</td><td>{r.calls}</td><td>${Number(r.cost_usd).toFixed(2)}</td>
                    </tr>
                  ))}
                </Table>
              )}
              {usage.data.notes.length > 0 && <p className="muted">{usage.data.notes.join(' ')}</p>}
            </>
          )}
        </Panel>
      )}
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
