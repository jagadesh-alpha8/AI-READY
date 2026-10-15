import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, KeyRound, Mail } from 'lucide-react';
import { confirmPasswordReset, requestPasswordReset } from '../../api/auth';
import ingageLogo from '../../assets/ingage-logo-mark.png';
import ingageLogoDark from '../../assets/ingage-logo-mark-dark.png';

/**
 * Forgot password (/forgot-password) and choose a new one (/reset-password).
 *
 * Both are public. The request page shows the same message whether or not the
 * email has an account, so it can't be used to find out who is registered. The
 * emailed link carries uid + token; it works once and expires in an hour.
 */

/** Per-field messages from the API, without the "field:" prefix getErrorMessage adds. */
function apiMessages(err: any, fallback: string): string[] {
  const data = err?.response?.data;
  if (err?.response?.status === 429) return ['Too many attempts. Please wait a while and try again.'];
  if (!data || typeof data !== 'object') return [fallback];
  if (typeof data.detail === 'string') return [data.detail];
  const out: string[] = [];
  Object.values(data).forEach((v) => {
    if (Array.isArray(v)) v.forEach((m) => typeof m === 'string' && out.push(m));
    else if (typeof v === 'string') out.push(v);
  });
  return out.length ? out : [fallback];
}

const Shell: React.FC<{ title: string; subtitle: string; children: React.ReactNode }> = ({ title, subtitle, children }) => (
  <div className="min-h-screen bg-surface flex flex-col justify-center py-10 px-4">
    <div className="max-w-md mx-auto w-full">
      <img src={ingageLogo} alt="InGage" className="h-9 w-auto mb-6 dark:hidden" />
      <img src={ingageLogoDark} alt="InGage" className="h-9 w-auto mb-6 hidden dark:block" />
      <div className="glass-card p-6 sm:p-8">
        <h2 className="text-xl font-bold text-ink-900 mb-1">{title}</h2>
        <p className="text-sm text-ink-500 mb-6">{subtitle}</p>
        {children}
      </div>
      <Link to="/login" className="mt-4 inline-flex items-center gap-1.5 text-sm text-brand-800 hover:underline">
        <ArrowLeft className="w-4 h-4" /> Back to sign in
      </Link>
    </div>
  </div>
);

const Errors: React.FC<{ messages: string[] }> = ({ messages }) =>
  messages.length ? (
    <div className="mb-4 p-3 bg-danger-bg border border-danger-line rounded-lg text-sm text-danger space-y-1">
      {messages.map((m) => <p key={m}>{m}</p>)}
    </div>
  ) : null;

export const ForgotPassword: React.FC = () => {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);
    setLoading(true);
    try {
      const { data } = await requestPasswordReset(email.trim());
      setSent(data.detail);
    } catch (err) {
      setErrors(apiMessages(err, 'Could not send the email. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Shell title="Forgot password" subtitle="Enter your email and we'll send you a link to choose a new password.">
      {sent ? (
        <div className="p-3 bg-brand-50 border border-brand-100 rounded-lg text-sm text-ink-700 flex gap-2">
          <Mail className="w-4 h-4 text-brand-800 shrink-0 mt-0.5" />
          <p>{sent} Check your spam folder if it doesn't arrive in a few minutes.</p>
        </div>
      ) : (
        <>
          <Errors messages={errors} />
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label" htmlFor="reset-email">Email address</label>
              <input id="reset-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                required autoComplete="email" className="input" />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">
              <Mail className="w-4 h-4" />
              <span>{loading ? 'Sending…' : 'Send reset link'}</span>
            </button>
          </form>
        </>
      )}
    </Shell>
  );
};

export const ResetPassword: React.FC = () => {
  const [params] = useSearchParams();
  const uid = params.get('uid') || '';
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setErrors(['The two passwords do not match.']);
      return;
    }
    setErrors([]);
    setLoading(true);
    try {
      await confirmPasswordReset(uid, token, password);
      setDone(true);
    } catch (err) {
      setErrors(apiMessages(err, 'Could not change the password. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  if (!uid || !token) {
    return (
      <Shell title="Reset link incomplete" subtitle="Open the link from the email exactly as it was sent.">
        <Link to="/forgot-password" className="btn-primary w-full">Ask for a new link</Link>
      </Shell>
    );
  }

  return (
    <Shell title="Choose a new password" subtitle="At least 8 characters; not a common password, and not only numbers.">
      {done ? (
        <div className="space-y-4">
          <div className="p-3 bg-brand-50 border border-brand-100 rounded-lg text-sm text-ink-700 flex gap-2">
            <CheckCircle2 className="w-4 h-4 text-brand-800 shrink-0 mt-0.5" />
            <p>Your password has been changed and you've been signed out on every device.</p>
          </div>
          <Link to="/login" className="btn-primary w-full">Sign in</Link>
        </div>
      ) : (
        <>
          <Errors messages={errors} />
          {errors.some((m) => m.includes('expired')) && (
            <p className="mb-4 text-sm"><Link to="/forgot-password" className="text-brand-800 hover:underline">Ask for a new link</Link></p>
          )}
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label" htmlFor="new-password">New password</label>
              <input id="new-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                required minLength={8} autoComplete="new-password" className="input" />
            </div>
            <div>
              <label className="label" htmlFor="confirm-password">Type it again</label>
              <input id="confirm-password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                required minLength={8} autoComplete="new-password" className="input" />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">
              <KeyRound className="w-4 h-4" />
              <span>{loading ? 'Saving…' : 'Set new password'}</span>
            </button>
          </form>
        </>
      )}
    </Shell>
  );
};
