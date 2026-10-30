import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, KeyRound } from 'lucide-react';

import { acceptInvitation, checkInvitation } from '../../api/institutions';
import { Errors, Shell, apiMessages } from './PasswordReset';

/**
 * The IQAC Coordinator invitation link (/activate-account?token=...), public. The token is checked first
 * (POST /auth/invitation): a new account chooses its password here; an existing account just accepts and keeps
 * its password. The link works once and expires (backend apps/institutions/coordinator.py).
 */
type Invitation = { institution_name: string; name: string; email: string; needs_password: boolean };

export const ActivateAccount: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [checking, setChecking] = useState(!!token);
  const [linkError, setLinkError] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    checkInvitation(token)
      .then((res) => setInvitation(res.data))
      .catch((err) => setLinkError(apiMessages(err, 'This invitation link is invalid or has expired.')[0]))
      .finally(() => setChecking(false));
  }, [token]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (invitation?.needs_password && password !== confirm) {
      setErrors(['The two passwords do not match.']);
      return;
    }
    setErrors([]);
    setSaving(true);
    try {
      await acceptInvitation(token, invitation?.needs_password ? password : '');
      setDone(true);
    } catch (err) {
      setErrors(apiMessages(err, 'Could not activate the account. Please try again.'));
    } finally {
      setSaving(false);
    }
  };

  if (!token) {
    return (
      <Shell title="Invitation link incomplete" subtitle="Open the link from the invitation email exactly as it was sent.">
        <Link to="/login" className="btn-primary w-full">Go to sign in</Link>
      </Shell>
    );
  }
  if (checking) {
    return <Shell title="Checking your invitation…" subtitle="One moment."><div /></Shell>;
  }
  if (linkError || !invitation) {
    return (
      <Shell title="This link can't be used" subtitle="Invitation links work once and expire after a few days.">
        <Errors messages={[linkError || 'This invitation link is invalid or has expired.']} />
        <p className="text-sm text-ink-600 mb-4">
          Ask your InGage consultant to resend the invitation, or use “Forgot password” with your email address
          to get a new activation link.
        </p>
        <Link to="/forgot-password" className="btn-primary w-full">Get a new link</Link>
      </Shell>
    );
  }
  if (done) {
    return (
      <Shell title="You're all set" subtitle={`IQAC Coordinator of ${invitation.institution_name}`}>
        <div className="p-3 mb-4 bg-brand-50 border border-brand-100 rounded-lg text-sm text-ink-700 flex gap-2">
          <CheckCircle2 className="w-4 h-4 text-brand-800 shrink-0 mt-0.5" />
          <p>Your account is active. Sign in with {invitation.email}{invitation.needs_password ? ' and the password you just chose' : ' and your existing password'}.</p>
        </div>
        <Link to="/login" className="btn-primary w-full">Sign in</Link>
      </Shell>
    );
  }
  return (
    <Shell
      title={`Welcome, ${invitation.name}`}
      subtitle={`You are the IQAC Coordinator of ${invitation.institution_name}. ${invitation.needs_password
        ? 'Choose a password for ' + invitation.email + ' (at least 8 characters, not a common one, not only numbers).'
        : 'Accept to join with your existing account — your password stays the same.'}`}
    >
      <Errors messages={errors} />
      <form onSubmit={submit} className="space-y-4">
        {invitation.needs_password && (
          <>
            <div>
              <label className="label" htmlFor="activate-password">Password</label>
              <input id="activate-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                required minLength={8} autoComplete="new-password" className="input" />
            </div>
            <div>
              <label className="label" htmlFor="activate-confirm">Type it again</label>
              <input id="activate-confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                required minLength={8} autoComplete="new-password" className="input" />
            </div>
          </>
        )}
        <button type="submit" disabled={saving} className="btn-primary w-full">
          <KeyRound className="w-4 h-4" />
          <span>{saving ? 'Activating…' : invitation.needs_password ? 'Activate my account' : 'Accept invitation'}</span>
        </button>
      </form>
    </Shell>
  );
};
