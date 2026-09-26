import React, { useState } from 'react';
import { Check, Info, KeyRound, Settings, Sliders, UserCog } from 'lucide-react';

import { changePassword } from '../../api/auth';
import { getScoringConfig } from '../../api/config';
import type { PillarConfig } from '../../api/config';
import { useAuth } from '../../context/AuthContext';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { UsersTab } from './UsersTab';
import { PageHeader, TabStrip } from '../../components/PageHeader';

/**
 * Admin / Settings.
 *
 * Three tabs, all backed by the database:
 *
 *   Scoring rubric  — the live pillar and criterion weights the CRI engine is
 *                     actually using. Read-only: editing a weight
 *                     re-fingerprints the engine and moves every score
 *                     calculated afterwards, including ones a client has
 *                     already signed off, so it needs an approval path rather
 *                     than an input box.
 *   Account         — the signed-in user, and a password change that works.
 *   Users           — create, edit, deactivate and reactivate any of the
 *                     eleven roles, via `/api/v1/users`. The server scopes an
 *                     institution admin to their own college and refuses
 *                     privilege escalation; see `apps/accounts/user_admin.py`.
 */

type Tab = 'rubric' | 'account' | 'users';

export const AdminSettings: React.FC = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>('rubric');

  const { data: pillars, loading, error, refetch } =
    useApiResource<PillarConfig[]>(() => getScoringConfig(), []);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Settings}
        title="Admin / Settings"
        description="The scoring rubric the engine runs on, and your own account."
      />

      <TabStrip
        tabs={[
          { id: 'rubric', label: 'Scoring rubric', icon: Sliders, count: pillars?.length },
          { id: 'account', label: 'Account', icon: KeyRound },
          { id: 'users', label: 'Users', icon: UserCog },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'rubric' && (
        <>
          {loading && <LoadingState message="Loading the scoring rubric…" />}
          {error && <ErrorState message={error} onRetry={refetch} />}
          {!loading && !error && pillars && <Rubric pillars={pillars} />}
        </>
      )}

      {tab === 'account' && <Account user={user} />}
      {tab === 'users' && <UsersTab />}
    </div>
  );
};

// ===== SCORING RUBRIC =====
const Rubric: React.FC<{ pillars: PillarConfig[] }> = ({ pillars }) => {
  const active = pillars.filter((p) => p.is_active);
  const totalWeight = active.reduce((sum, p) => sum + p.weight, 0);
  const criteriaCount = pillars.reduce((sum, p) => sum + p.criteria.length, 0);
  // Weights are normalised at evaluation time, so a total that is not 1.0 is
  // not a fault — but an administrator should be able to see what it is.
  const weightsSumToOne = Math.abs(totalWeight - 1) < 0.001;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Metric label="Active pillars" value={`${active.length} / ${pillars.length}`} />
        <Metric label="Criteria defined" value={criteriaCount} />
        <Metric
          label="Active weights total"
          value={totalWeight.toFixed(3)}
          tone={weightsSumToOne ? 'success' : 'default'}
        />
      </div>

      <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600 min-w-0">
          <strong className="text-info">Read-only, deliberately. </strong>
          These weights are live — the CRI engine reads them from the database on every calculation,
          and its version fingerprint changes when they do. Editing one here would silently move
          every score calculated afterwards, including ones a client has already signed off. That
          needs an approval workflow, not a text box.
        </p>
      </div>

      <div className="space-y-3">
        {pillars.map((pillar) => (
          <div key={pillar.key} className="glass-card p-5 space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-bold text-ink-900">{pillar.name}</h3>
                  <span className="font-mono text-[11px] text-ink-500">{pillar.key}</span>
                  {!pillar.is_active && <span className="badge badge-neutral">Inactive</span>}
                </div>
                {pillar.description && (
                  <p className="text-xs text-ink-600 mt-1">{pillar.description}</p>
                )}
              </div>
              <span className="badge badge-brand shrink-0">
                weight {(pillar.weight * 100).toFixed(0)}%
              </span>
            </div>

            {pillar.criteria.length > 0 ? (
              <div className="table-shell">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th>Weight</th>
                      <th>Fact fields</th>
                      <th>Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pillar.criteria.map((c) => (
                      <tr key={c.key}>
                        <td>
                          <p className="font-medium text-ink-900">{c.name}</p>
                          <p className="font-mono text-[11px] text-ink-500">{c.key}</p>
                        </td>
                        <td className="tabular-nums text-ink-700 whitespace-nowrap">
                          {(c.weight * 100).toFixed(0)}%
                        </td>
                        <td className="text-ink-600 text-xs">
                          {c.fact_field_keys.length > 0
                            ? c.fact_field_keys.join(', ')
                            : 'Every confirmed fact on this pillar'}
                        </td>
                        <td>
                          <span className={`badge ${c.is_active ? 'badge-success' : 'badge-neutral'}`}>
                            {c.is_active ? 'Yes' : 'No'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-ink-500">
                No criteria defined — every confirmed fact tagged to this pillar counts toward it.
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ===== ACCOUNT =====
const Account: React.FC<{ user: ReturnType<typeof useAuth>['user'] }> = ({ user }) => {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    if (next !== confirm) {
      setError('The new password and its confirmation do not match.');
      return;
    }
    setSaving(true);
    setError('');
    setDone(false);
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent(''); setNext(''); setConfirm('');
    } catch (err) {
      // Django's own validators produce the useful message here — length,
      // similarity to the username, common passwords — so surface theirs.
      setError(getErrorMessage(err, 'Could not change the password.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="glass-card p-5 space-y-3">
        <h2 className="eyebrow">Signed in as</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Name" value={user?.name || '—'} />
          <Field label="Email" value={user?.email || '—'} />
          <Field label="Role" value={(user?.role || '').replace(/_/g, ' ') || '—'} capitalize />
          <Field label="Department" value={user?.department_name || '—'} />
        </div>
        <p className="text-xs text-ink-500">
          Your role decides what you can do, and it is enforced by the server on every request —
          the screens you can open are not the same as the actions you can take.
        </p>
      </div>

      <form onSubmit={submit} className="glass-card p-5 space-y-4">
        <h2 className="eyebrow">Change password</h2>

        {error && <InlineError message={error} onDismiss={() => setError('')} />}
        {done && (
          <div className="rounded-lg border border-success-line bg-success-bg p-3 flex items-center gap-2">
            <Check className="w-4 h-4 text-success shrink-0" />
            <p className="text-sm text-success">Password changed.</p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="pw-current">Current password</label>
            <input
              id="pw-current" type="password" value={current} required autoComplete="current-password"
              onChange={(e) => setCurrent(e.target.value)} className="input"
            />
          </div>
          <div>
            <label className="label" htmlFor="pw-new">New password</label>
            <input
              id="pw-new" type="password" value={next} required autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)} className="input"
            />
          </div>
          <div>
            <label className="label" htmlFor="pw-confirm">Confirm new password</label>
            <input
              id="pw-confirm" type="password" value={confirm} required autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)} className="input"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={saving || !current || !next || !confirm}
          className="btn-primary btn-sm"
        >
          {saving ? 'Changing…' : 'Change password'}
        </button>
      </form>
    </div>
  );
};

const Field: React.FC<{ label: string; value: string; capitalize?: boolean }> = ({
  label, value, capitalize = false,
}) => (
  <div className="rounded-lg border border-line-200 bg-surface p-3 min-w-0">
    <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    {/* Opt-in: capitalising everything turned an email address into
        "Superadmin@Ingage.Ai". Only the role slug needs it. */}
    <p className={`text-sm text-ink-900 mt-0.5 truncate ${capitalize ? 'capitalize' : ''}`}>{value}</p>
  </div>
);

const Metric: React.FC<{
  label: string;
  value: number | string;
  tone?: 'default' | 'success';
}> = ({ label, value, tone = 'default' }) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p className={`text-2xl font-bold mt-1 tabular-nums ${tone === 'success' ? 'text-success' : 'text-ink-900'}`}>
      {value}
    </p>
  </div>
);
