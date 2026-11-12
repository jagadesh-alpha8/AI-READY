import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { Loading, Notice } from '../components/ui';
import { acceptInvitation, checkInvitation, confirmPasswordReset } from '../services/auth';
import { errorMessage } from '../utils/errors';

/**
 * The two pages the backend's emails link to (same look as the login page, outside the signed-in app):
 *   {FRONTEND_BASE_URL}/reset-password?uid=...&token=...   (Forgot password? on the login page)
 *   {FRONTEND_BASE_URL}/activate-account?token=...         (IQAC Coordinator invitation from onboarding)
 */
function LinkFrame({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <AuthLayout>
      <div className="auth-card">
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {children}
        <Link className="link-button" to="/login">Back to sign in</Link>
      </div>
    </AuthLayout>
  );
}

function PasswordFields({ password, confirm, onPassword, onConfirm }: {
  password: string; confirm: string; onPassword: (v: string) => void; onConfirm: (v: string) => void;
}) {
  return (
    <>
      <label className="field">
        <span>New password</span>
        <input type="password" autoComplete="new-password" required value={password} onChange={(e) => onPassword(e.target.value)} />
      </label>
      <label className="field">
        <span>Confirm new password</span>
        <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => onConfirm(e.target.value)} />
      </label>
    </>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const uid = params.get('uid') || '';
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) { setError('The two passwords do not match.'); return; }
    setBusy(true);
    try {
      const res = await confirmPasswordReset(uid, token, password);
      setDone(res.data.detail || 'Your password has been changed. Sign in with the new password.');
    } catch (err) {
      setError(errorMessage(err, 'The password could not be changed.'));
    } finally {
      setBusy(false);
    }
  };

  if (!uid || !token) {
    return (
      <LinkFrame eyebrow="Password reset" title="This link is incomplete">
        <p>Open the full link from the reset email, or request a new one with “Forgot password?” on the sign-in page.</p>
      </LinkFrame>
    );
  }
  return (
    <LinkFrame eyebrow="Password reset" title="Choose a new password">
      <p>The link works once and expires after an hour. Every other session is signed out.</p>
      {done ? <Notice tone="success">{done}</Notice> : (
        <form onSubmit={submit}>
          <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
          {error && <Notice tone="error">{error}</Notice>}
          <button className="primary-action wide" type="submit" disabled={busy}>{busy ? 'Please wait…' : 'Change password'}</button>
        </form>
      )}
    </LinkFrame>
  );
}

export function ActivateAccount() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [invite, setInvite] = useState<{ institution_name: string; name: string; email: string; needs_password: boolean } | null>(null);
  const [checking, setChecking] = useState(!!token);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  useEffect(() => {
    if (!token) return;
    checkInvitation(token)
      .then((res) => setInvite(res.data))
      .catch((err) => setError(errorMessage(err, 'This invitation link is not valid.')))
      .finally(() => setChecking(false));
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (invite?.needs_password && password !== confirm) { setError('The two passwords do not match.'); return; }
    setBusy(true);
    try {
      const res = await acceptInvitation(token, invite?.needs_password ? password : '');
      setDone(res.data.detail || 'Your access is ready. Sign in to continue.');
    } catch (err) {
      setError(errorMessage(err, 'The invitation could not be accepted.'));
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <LinkFrame eyebrow="IQAC Coordinator invitation" title="This link is incomplete">
        <p>Open the full link from the invitation email, or ask InGage to resend it.</p>
      </LinkFrame>
    );
  }
  if (checking) return <LinkFrame eyebrow="IQAC Coordinator invitation" title="Checking your invitation"><Loading /></LinkFrame>;
  if (!invite) {
    return (
      <LinkFrame eyebrow="IQAC Coordinator invitation" title="This invitation can't be used">
        <Notice tone="error">{error || 'This invitation link is not valid.'}</Notice>
        <p>An invitation works once and expires. Ask InGage to resend it from the institution's onboarding.</p>
      </LinkFrame>
    );
  }
  return (
    <LinkFrame eyebrow="IQAC Coordinator invitation" title={`Welcome, ${invite.name || invite.email}`}>
      <p>You are invited as IQAC Coordinator for <b>{invite.institution_name}</b> ({invite.email}).</p>
      {done ? <Notice tone="success">{done}</Notice> : (
        <form onSubmit={submit}>
          {invite.needs_password
            ? <PasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
            : <p className="muted">You already have an account; accepting links it to this college.</p>}
          {error && <Notice tone="error">{error}</Notice>}
          <button className="primary-action wide" type="submit" disabled={busy}>{busy ? 'Please wait…' : 'Activate my access'}</button>
        </form>
      )}
    </LinkFrame>
  );
}
