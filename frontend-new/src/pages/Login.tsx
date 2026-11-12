import { useState, type FormEvent } from 'react';
import { ArrowRight, AuthCard, AuthLayout } from '../components/AuthLayout';
import { Notice } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { requestPasswordReset } from '../services/auth';
import { errorMessage } from '../utils/errors';

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resetMode, setResetMode] = useState(false);
  const [resetDone, setResetDone] = useState('');

  const switchMode = (reset: boolean) => { setResetMode(reset); setError(''); setResetDone(''); };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (resetMode) {
        const res = await requestPasswordReset(email);
        setResetDone(res.data.detail || 'If the address has an account, a reset link is on its way.');
      } else {
        await login(email, password);
      }
    } catch (err) {
      setError(errorMessage(err, resetMode ? 'The reset link could not be sent.' : 'Sign-in failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <AuthCard
        title={resetMode ? 'Reset your password' : 'Welcome back'}
        lead={resetMode ? 'Enter your account email and we will send a reset link.' : 'Sign in to continue your audit sprint.'}
        note={resetMode ? 'The link works once and expires after an hour.' : "Your institution's data is visible only to its own team and InGage."}>
        <form className="auth-form" onSubmit={submit}>
          <label className="field">
            <span>Email address</span>
            <input id="login-email" type="email" autoComplete="username" placeholder="you@institution.edu" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          {!resetMode && (
            <label className="field">
              <span className="field-row">Password
                <button type="button" className="link-button" onClick={() => switchMode(true)}>Forgot password?</button>
              </span>
              <input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          {resetDone && <Notice tone="success">{resetDone}</Notice>}
          <button className="primary-action wide" type="submit" disabled={busy}>
            <span>{busy ? 'Please wait…' : resetMode ? 'Send reset link' : 'Sign in'}</span>
            {!busy && <ArrowRight />}
          </button>
          {resetMode && <button type="button" className="link-button" onClick={() => switchMode(false)}>Back to sign in</button>}
        </form>
      </AuthCard>
    </AuthLayout>
  );
}
