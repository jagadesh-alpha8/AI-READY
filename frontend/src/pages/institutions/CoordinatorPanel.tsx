import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Mail, Pencil, RotateCw, UserCheck, X } from 'lucide-react';

import { getCoordinator, resendCoordinatorInvitation, setCoordinator } from '../../api/institutions';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { confirmDialog } from '../../components/Dialog';
import { useApiResource } from '../../hooks/useApiResource';
import type { CoordinatorStatus } from '../../types';
import { coordinatorEmailError, coordinatorNameError } from '../../utils/coordinator';
import { getErrorMessage } from '../../utils/errors';

/**
 * The college's IQAC Coordinator on its Institution DNA page (backend apps/institutions/coordinator.py).
 *
 * Kept apart from the profile form on purpose: a coordinator change is not a profile edit -- it may invite a
 * different person, so it goes through POST /institutions/<id>/coordinator, which checks the account is allowed
 * to join this college. Everyone who can open the page sees the coordinator and status; only InGage staff
 * (`canManage`, enforced again by the server) change it or resend the invitation.
 */

const STATE_BADGE: Record<string, string> = {
  active: 'badge-success', invited: 'badge-info', email_failed: 'badge-danger', expired: 'badge-warning',
  account_unavailable: 'badge-danger', not_sent: 'badge-warning', not_invited: 'badge-warning',
  pending_setup: 'badge-neutral', missing: 'badge-danger',
};

type Field = 'coordinator_name' | 'coordinator_email';

/** Field-level messages from the API ({coordinator_email: ["..."]}), or a general one under `detail`. */
export function coordinatorApiErrors(err: unknown): { fields: Partial<Record<Field, string>>; general: string } {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data;
  const fields: Partial<Record<Field, string>> = {};
  let general = '';
  if (data && typeof data === 'object') {
    (['coordinator_name', 'coordinator_email'] as Field[]).forEach((field) => {
      const value = data[field];
      if (Array.isArray(value) && typeof value[0] === 'string') fields[field] = value[0];
    });
    const detail = data.detail;
    if (Array.isArray(detail) && typeof detail[0] === 'string') general = detail[0];
    else if (typeof detail === 'string') general = detail;
  }
  if (!general && !Object.keys(fields).length) general = getErrorMessage(err, 'The coordinator could not be saved.');
  return { fields, general };
}

export const CoordinatorPanel: React.FC<{ institutionId: string; canManage: boolean }> = ({ institutionId, canManage }) => {
  const location = useLocation();
  const { data, loading, error, refetch } = useApiResource<CoordinatorStatus>(
    () => getCoordinator(institutionId), [institutionId]);
  // Just created on the list page: say whether the first invitation email went out.
  const created = (location.state as { invitationEmailSent?: boolean } | null)?.invitationEmailSent;
  const [message, setMessage] = useState(
    created === true ? 'Institution created. The invitation email was sent to the coordinator.' : '');
  const [failure, setFailure] = useState(
    created === false ? 'Institution created, but the invitation email could not be sent. Use “Resend invitation”.' : '');
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ coordinator_name: '', coordinator_email: '' });
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <LoadingState message="Loading the IQAC Coordinator…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data) return null;

  const startEdit = () => {
    setForm({ coordinator_name: data.name, coordinator_email: data.email });
    setFieldErrors({});
    setMessage('');
    setFailure('');
    setEditing(true);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<Field, string>> = {};
    const nameProblem = coordinatorNameError(form.coordinator_name);
    const emailProblem = coordinatorEmailError(form.coordinator_email);
    if (nameProblem) errors.coordinator_name = nameProblem;
    if (emailProblem) errors.coordinator_email = emailProblem;
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    const newPerson = form.coordinator_email.trim().toLowerCase() !== data.email.toLowerCase();
    if (newPerson && data.configured && !(await confirmDialog(
      `Invite ${form.coordinator_email.trim()} as this college's IQAC Coordinator? The pending invitation to `
      + `${data.email} stops working. The previous coordinator's account is not changed or removed — do that in `
      + 'User administration if they should lose access.',
      { title: 'Change IQAC Coordinator', confirmLabel: 'Invite new coordinator' },
    ))) return;
    setBusy(true);
    setFailure('');
    try {
      const { data: result } = await setCoordinator(
        institutionId, form.coordinator_name.trim(), form.coordinator_email.trim());
      setEditing(false);
      if (!result.changed) setMessage('Coordinator name updated. No new invitation was needed.');
      else if (result.invitation_email_sent) setMessage(`Invitation emailed to ${result.email}.`);
      else setFailure(`The coordinator was saved, but the invitation email to ${result.email} could not be sent. Use “Resend invitation”.`);
      await refetch();
    } catch (err) {
      const { fields, general } = coordinatorApiErrors(err);
      setFieldErrors(fields);
      setFailure(general);
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!(await confirmDialog(
      `Send a new activation link to ${data.email}? The link sent earlier stops working; only the new one can be used.`,
      { title: 'Resend invitation', confirmLabel: 'Resend' },
    ))) return;
    setBusy(true);
    setMessage('');
    setFailure('');
    try {
      const { data: result } = await resendCoordinatorInvitation(institutionId);
      if (result.invitation_email_sent) setMessage(`A new activation link was emailed to ${result.email}. The previous link no longer works.`);
      else setFailure('The invitation email could not be sent. Check the email settings, then try again.');
      await refetch();
    } catch (err) {
      setFailure(coordinatorApiErrors(err).general);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-card p-5 sm:p-6 space-y-4" aria-labelledby="iqac-coordinator-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <UserCheck className="w-5 h-5 text-brand-700 mt-0.5" />
          <div>
            <h2 id="iqac-coordinator-heading" className="text-lg font-bold text-ink-900">IQAC Coordinator</h2>
            <p className="text-xs text-ink-500">
              Owns this college's work on the platform. Changed only here — not through the profile form.
            </p>
          </div>
        </div>
        {canManage && !editing && (
          <div className="flex flex-wrap gap-2">
            {data.can_resend && (
              <button type="button" className="btn-secondary btn-sm" onClick={resend} disabled={busy}
                title="Sends a new activation link; the previous link stops working.">
                <RotateCw className="w-3.5 h-3.5" /> Resend invitation
              </button>
            )}
            <button type="button" className="btn-secondary btn-sm" onClick={startEdit} disabled={busy}>
              <Pencil className="w-3.5 h-3.5" /> {data.configured ? 'Change coordinator' : 'Add coordinator'}
            </button>
          </div>
        )}
      </div>

      {message && (
        <div role="status" className="rounded-lg border border-success-line bg-success-bg px-3 py-2 text-sm text-success">
          {message}
        </div>
      )}
      {failure && <InlineError message={failure} onDismiss={() => setFailure('')} />}

      {editing ? (
        <form onSubmit={save} className="space-y-3" noValidate>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="coordinator-name">IQAC Coordinator Name <span className="text-danger">*</span></label>
              <input id="coordinator-name" className={`input ${fieldErrors.coordinator_name ? 'input-error' : ''}`}
                value={form.coordinator_name} autoComplete="off" aria-invalid={!!fieldErrors.coordinator_name}
                onChange={(e) => { setForm({ ...form, coordinator_name: e.target.value }); setFieldErrors({ ...fieldErrors, coordinator_name: '' }); }} />
              {fieldErrors.coordinator_name && <p className="text-xs text-danger mt-1">{fieldErrors.coordinator_name}</p>}
            </div>
            <div>
              <label className="label" htmlFor="coordinator-email">IQAC Coordinator Email <span className="text-danger">*</span></label>
              <input id="coordinator-email" type="email" className={`input ${fieldErrors.coordinator_email ? 'input-error' : ''}`}
                value={form.coordinator_email} autoComplete="off" aria-invalid={!!fieldErrors.coordinator_email}
                onChange={(e) => { setForm({ ...form, coordinator_email: e.target.value }); setFieldErrors({ ...fieldErrors, coordinator_email: '' }); }} />
              {fieldErrors.coordinator_email && <p className="text-xs text-danger mt-1">{fieldErrors.coordinator_email}</p>}
            </div>
          </div>
          <p className="text-xs text-ink-500">
            A different email invites that person with a new single-use activation link; they get access only once they
            accept. Correcting the name of the same person sends nothing.
          </p>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary btn-sm" disabled={busy}>{busy ? 'Saving…' : 'Save coordinator'}</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setEditing(false)} disabled={busy}>
              <X className="w-3.5 h-3.5" /> Cancel
            </button>
          </div>
        </form>
      ) : (
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">Name</dt>
            <dd className="font-semibold text-ink-900">{data.name || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">Email</dt>
            <dd className="text-ink-800 break-all">{data.email ? <><Mail className="inline w-3.5 h-3.5 mr-1 text-ink-400" />{data.email}</> : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">Status</dt>
            <dd><span className={STATE_BADGE[data.state] || 'badge-neutral'}>{data.state_label}</span>
              {data.last_sent_at ? <span className="block text-[11px] text-ink-500 mt-0.5">Last emailed {new Date(data.last_sent_at).toLocaleString()}</span> : null}
            </dd>
          </div>
        </dl>
      )}
      {!data.configured && !editing && (
        <p className="text-sm text-danger">No IQAC Coordinator yet: sprints cannot be started for this college until one is added.</p>
      )}
      {data.events && data.events.length > 0 && (
        <details className="text-xs text-ink-600">
          <summary className="cursor-pointer font-semibold text-ink-700">History ({data.events.length})</summary>
          <ul className="mt-2 space-y-1">
            {[...data.events].reverse().map((e, i) => (
              <li key={i}>{new Date(e.created_at).toLocaleString()} — {e.label}{e.user_name ? ` (${e.user_name})` : ''}{e.note ? `: ${e.note}` : ''}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
};
