import React, { useEffect, useState } from 'react';

import { confirmProfile, getProfileSuggestion, type ProfileSuggestion, type ProfileValues } from '../../api/facts';
import { InlineError } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';

/** The values the documents suggest, falling back to the saved profile where the documents say nothing. */
function initialValues(s: ProfileSuggestion): ProfileValues {
  const cur = s.current;
  return {
    institution_type: s.suggested.institution_type.value || cur?.institution_type || '',
    autonomous_status: s.suggested.autonomous_status.value || cur?.autonomous_status || '',
    approval_bodies: s.suggested.approval_bodies.length ? s.suggested.approval_bodies : cur?.approval_bodies || [],
    programmes: s.suggested.programmes.length
      ? s.suggested.programmes.map(({ name, programme_type, approval_body }) => ({ name, programme_type, approval_body }))
      : cur?.programmes || [],
  };
}

const same = (a: ProfileValues, b: ProfileValues | null) => !!b && JSON.stringify({ ...a, approval_bodies: [...a.approval_bodies].sort(), programmes: [...a.programmes].sort((x, y) => x.name.localeCompare(y.name)) })
  === JSON.stringify({ ...b, approval_bodies: [...b.approval_bodies].sort(), programmes: [...b.programmes].sort((x, y) => x.name.localeCompare(y.name)) });

/**
 * "We read this from your documents — correct?" The institution profile (which indicators apply) pre-filled
 * from the sprint's profile facts (backend apps/facts/profile_suggestion.py). One Confirm; a field the
 * documents disagree on, or did not name, is a single choice. InGage staff confirm (with the client).
 */
export const ProfileConfirmPanel: React.FC<{ sprintId: string; canConfirm: boolean }> = ({ sprintId, canConfirm }) => {
  const { data, refetch } = useApiResource<ProfileSuggestion>(() => getProfileSuggestion(sprintId), [sprintId], !!sprintId);
  const [values, setValues] = useState<ProfileValues | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => { if (data) setValues(initialValues(data)); }, [data]);
  if (!data || !values) return null;

  const s = data.suggested;
  const hasSuggestion = !!(s.institution_type.candidates.length || s.autonomous_status.candidates.length
    || s.approval_bodies.length || s.programmes.length || data.unmatched.length);
  if (!hasSuggestion && !data.current) return null;
  const confirmed = same(values, data.current);
  const name = (list: { code: string; name: string }[], code: string) => list.find((o) => o.code === code)?.name || code || '—';
  const needsChoice = !values.institution_type || s.institution_type.conflict || s.autonomous_status.conflict;

  const submit = async () => {
    setBusy(true); setError(''); setMessage('');
    try {
      await confirmProfile(sprintId, values);
      setMessage('Profile confirmed. The CRI was recalculated with the indicators that apply to this institution.');
      setEditing(false);
      refetch();
    } catch (err) {
      setError(getErrorMessage(err, 'The profile could not be saved.'));
    } finally { setBusy(false); }
  };

  const choice = (label: string, field: 'institution_type' | 'autonomous_status',
    options: { code: string; name: string }[], conflict: boolean) => (
    <div>
      <dt className="text-ink-500">{label}{conflict && <span className="text-warning"> · documents disagree, pick one</span>}</dt>
      <dd>
        {editing || conflict || !values[field] ? (
          <select className="input text-xs py-1" value={values[field]} disabled={!canConfirm}
            onChange={(e) => setValues({ ...values, [field]: e.target.value })}>
            <option value="">Choose…</option>
            {options.map((o) => <option key={o.code} value={o.code}>{o.name}</option>)}
          </select>
        ) : <span className="text-ink-900">{name(options, values[field])}</span>}
      </dd>
    </div>
  );

  return (
    <div className="glass-card p-4 mb-4 text-xs space-y-3" data-testid="profile-confirm">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-bold text-ink-900">Institution profile{confirmed ? ' · confirmed' : ' — we read this from your documents. Correct?'}</h2>
          <p className="text-ink-500">It decides which AI-QIF indicators apply to {data.institution_name}.</p>
        </div>
        {canConfirm && !confirmed && (
          <div className="flex gap-2">
            <button className="btn-secondary btn-sm" onClick={() => setEditing(!editing)} disabled={busy}>{editing ? 'Done editing' : 'Edit'}</button>
            <button className="btn-primary btn-sm" onClick={submit} disabled={busy || needsChoice && !values.institution_type}>
              {busy ? 'Saving…' : 'Confirm'}
            </button>
          </div>
        )}
      </div>
      {error && <InlineError message={error} onDismiss={() => setError('')} />}
      {message && <p className="text-success">{message}</p>}
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {choice('Institution type', 'institution_type', data.options.institution_types, s.institution_type.conflict)}
        {choice('Autonomous status', 'autonomous_status', data.options.autonomous_statuses, s.autonomous_status.conflict)}
        <div>
          <dt className="text-ink-500">Approval bodies</dt>
          <dd className="flex flex-wrap gap-1">
            {editing ? data.options.approval_bodies.map((b) => (
              <label key={b} className="inline-flex items-center gap-1 mr-2">
                <input type="checkbox" checked={values.approval_bodies.includes(b)}
                  onChange={(e) => setValues({ ...values, approval_bodies: e.target.checked
                    ? [...values.approval_bodies, b] : values.approval_bodies.filter((x) => x !== b) })} />{b}
              </label>
            )) : (values.approval_bodies.length ? values.approval_bodies.map((b) => <span key={b} className="badge-neutral">{b}</span>) : '—')}
          </dd>
        </div>
        <div>
          <dt className="text-ink-500">Programmes</dt>
          <dd className="text-ink-900">
            {values.programmes.length ? values.programmes.map((p) => `${p.name} (${name(data.options.programme_types, p.programme_type)})`).join('; ') : '—'}
          </dd>
        </div>
      </dl>
      {data.unmatched.length > 0 && (
        <p className="text-ink-500">
          Also read, but not matched to the lists above (choose the right value if it matters):{' '}
          {data.unmatched.map((u) => `${u.field_name}: ${String(u.value)}`).join('; ')}.
        </p>
      )}
    </div>
  );
};
