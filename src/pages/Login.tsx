import { useState, type FormEvent } from 'react';
import ingageLogo from '../assets/ingage-logo-mark.png';
import { useAuth } from '../context/AuthContext';
import { requestPasswordReset } from '../services/auth';
import { Notice } from '../components/ui';
import { errorMessage } from '../utils/errors';

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resetMode, setResetMode] = useState(false);
  const [resetDone, setResetDone] = useState('');

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
      setError(errorMessage(err, 'Sign-in failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <header className="roadmap-sharebar">
        <div className="concept-brand">
          <span className="brand-plate"><img className="brand-logo" src={ingageLogo} alt="Ingage" /></span>
          <div><strong>AI Ready Campus</strong><span>Maturity programme</span></div>
        </div>
        <div className="sharebar-flow" aria-hidden="true"><span>Discover</span><i /><span>Verify</span><i /><span>Assess</span><i /><span>Transform</span><i /><span>Advance</span></div>
      </header>
      <main className="login-card">
        <img className="login-logo" src={ingageLogo} alt="Ingage" />
        <span className="eyebrow">{resetMode ? 'Password reset' : 'Sign in'}</span>
        <h1>{resetMode ? 'Reset your password' : 'Your route from capable to AI-leading.'}</h1>
        <p>{resetMode ? 'Enter your account email and we will send a reset link.' : 'Sign in with your AI Ready Campus account.'}</p>
        <form onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          {!resetMode && (
            <label className="field">
              <span>Password</span>
              <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          {resetDone && <Notice tone="success">{resetDone}</Notice>}
          <button className="primary-action wide" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : resetMode ? 'Send reset link' : 'Sign in'}
          </button>
        </form>
        <button className="link-button" onClick={() => { setResetMode(!resetMode); setError(''); setResetDone(''); }}>
          {resetMode ? 'Back to sign in' : 'Forgot password?'}
        </button>
      </main>
    </div>
  );
}
