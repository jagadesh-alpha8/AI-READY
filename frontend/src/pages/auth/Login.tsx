import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import {
  ArrowRight, ClipboardCheck, FileSearch, Gauge, Lock, Shield, Target,
} from 'lucide-react';
import ingageLogo from '../../assets/ingage-logo-mark.png';
import ingageLogoDark from '../../assets/ingage-logo-mark-dark.png';

/**
 * Sign-in. Two columns: what the platform is, and the form to get into it.
 *
 * The eleven demo personas and the shared seed password used to sit on this
 * page in the open. That is fine on a developer's machine and wrong in front
 * of a client: it advertises eleven live accounts and their password to
 * anyone who reaches the URL. They are now behind a flag that is off unless
 * `VITE_SHOW_DEMO_PERSONAS=true` is set, so nothing was deleted and a
 * developer can have them back with one line in `.env.local`.
 */
const SHOW_DEMO_PERSONAS = import.meta.env.VITE_SHOW_DEMO_PERSONAS === 'true';

// The seed password is only ever compiled into a developer build with
// VITE_SHOW_DEMO_PERSONAS=true. A production bundle contains neither it nor a
// prefilled login: anyone reaching /login could otherwise read the super
// admin's credentials out of the password box.
const DEMO_PASSWORD = SHOW_DEMO_PERSONAS ? 'Password123!' : '';
const DEFAULT_EMAIL = SHOW_DEMO_PERSONAS ? 'superadmin@ingage.ai' : '';
const DEFAULT_PASSWORD = DEMO_PASSWORD;

/** Only ever rendered when SHOW_DEMO_PERSONAS is on; see above. */
const SEEDED_ROLES = [
  { role: 'SUPER_ADMIN', name: 'Super Admin', email: 'superadmin@ingage.ai', desc: 'Full System & Config Control' },
  { role: 'INGAGE_CONSULTANT', name: 'InGage Lead Consultant', email: 'consultant@ingage.ai', desc: 'Sprint Lead & Scoring Specialist' },
  { role: 'INSTITUTION_ADMIN', name: 'Dr. N. Ramesh', email: 'principal@mkce.ac.in', desc: 'Principal / Institution Admin' },
  { role: 'IQAC_COORDINATOR', name: 'Prof. S. Kanthaswamy', email: 'iqac@mkce.ac.in', desc: 'IQAC & AQAR Nodal Officer' },
  { role: 'REGISTRAR', name: 'Dr. K. Vignesh', email: 'registrar@mkce.ac.in', desc: 'Registrar (Master Records)' },
  { role: 'HOD', name: 'Dr. C. Vivek', email: 'hod_cs@mkce.ac.in', desc: 'HOD Computer Science' },
  { role: 'HR_OFFICER', name: 'P. Meenakshi', email: 'hr@mkce.ac.in', desc: 'HR Officer (Faculty Records)' },
  { role: 'PLACEMENT_OFFICER', name: 'R. Anand', email: 'placement@mkce.ac.in', desc: 'Placement & Industry Head' },
  { role: 'FACULTY', name: 'R. Priya', email: 'faculty@mkce.ac.in', desc: 'Faculty (Computer Science)' },
  { role: 'LAB_ADMIN', name: 'S. Karthik', email: 'labadmin@mkce.ac.in', desc: 'Lab & Compute Infrastructure' },
  { role: 'VIEWER', name: 'Trustee Board', email: 'viewer@mkce.ac.in', desc: 'Approved Reports Viewer' },
];

/** What the platform actually does. Every claim here maps to a module that
 *  exists — no capability is described that a client cannot be shown. */
const CAPABILITIES = [
  {
    icon: FileSearch,
    title: 'Evidence-first, not self-reported',
    body: 'Institutional documents — SSR, AQAR, audited records — are ingested and machine-read. '
      + 'Each extracted fact keeps a citation back to its source page.',
  },
  {
    icon: Gauge,
    title: 'Composite Readiness Index',
    body: 'A single weighted score across eight readiness domains, recomputed from confirmed '
      + 'facts rather than opinion, with the rubric visible to administrators.',
  },
  {
    icon: Target,
    title: 'Gaps become a costed plan',
    body: 'Every gap is ranked by impact and effort, then rolled into a phased transformation '
      + 'plan with owners, milestones and projected score lift.',
  },
  {
    icon: ClipboardCheck,
    title: 'Audit-ready by construction',
    body: 'Scores trace back to the document that produced them, so a finding can be defended '
      + 'in an accreditation review rather than merely asserted.',
  },
];

/** The eight scored domains, matching the live rubric in the database. */
const DOMAINS = [
  'Governance & Strategy',
  'Curriculum & Academic Readiness',
  'Faculty AI Capability',
  'Student AI Readiness',
  'Infrastructure & Digital Capability',
  'Research & Innovation',
  'Industry & Placement Outcomes',
  'Evidence Quality & Data Confidence',
];

export const Login: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState(DEFAULT_EMAIL);
  const [password, setPassword] = useState(DEFAULT_PASSWORD);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Invalid login credentials'));
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (targetEmail: string) => {
    setEmail(targetEmail);
    setError('');
    setLoading(true);
    try {
      await login(targetEmail, DEMO_PASSWORD);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Quick login failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center py-10 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 lg:items-center">

        {/* ===== Column 1 — the portal ===== */}
        <section className="lg:col-span-7 min-w-0 order-2 lg:order-1">
          {/* Light/dark pair — see the note in Navbar.tsx. */}
          <img src={ingageLogo} alt="InGage" className="h-9 sm:h-10 w-auto mb-6 dark:hidden" />
          <img
            src={ingageLogoDark}
            alt=""
            aria-hidden="true"
            className="h-9 sm:h-10 w-auto mb-6 hidden dark:block"
          />

          <h1 className="text-3xl sm:text-4xl font-bold text-ink-900 tracking-tight text-balance">
            AIOS AI Readiness Discovery Sprint Platform
          </h1>
          <p className="mt-3 text-base text-ink-600 max-w-2xl">
            A fast-track discovery platform that tells a higher-education institution where it
            actually stands on AI readiness — from its own evidence, in weeks rather than quarters.
          </p>

          <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-6">
            {CAPABILITIES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="flex items-start gap-3 min-w-0">
                <span className="shrink-0 rounded-lg bg-brand-50 border border-brand-100 p-2">
                  <Icon className="w-4 h-4 text-brand-800" />
                </span>
                <div className="min-w-0">
                  <h2 className="text-sm font-bold text-ink-900">{title}</h2>
                  <p className="text-sm text-ink-500 mt-0.5">{body}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 pt-6 border-t border-line-200">
            <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">
              Scored across eight domains
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {DOMAINS.map((d) => (
                <span
                  key={d}
                  className="text-xs text-ink-600 bg-card border border-line-200 rounded-full px-2.5 py-1"
                >
                  {d}
                </span>
              ))}
            </div>
          </div>

          <p className="mt-6 text-xs text-ink-500">
            Built by InGage Technologies. Access is role-based and enforced server-side.
          </p>
        </section>

        {/* ===== Column 2 — sign in ===== */}
        <section className="lg:col-span-5 min-w-0 order-1 lg:order-2">
          <div className="glass-card p-6 sm:p-8">
            <h2 className="text-xl font-bold text-ink-900 mb-1">Sign in</h2>
            <p className="text-sm text-ink-500 mb-6">Use your institutional credentials.</p>

            {error && (
              <div className="mb-4 p-3 bg-danger-bg border border-danger-line rounded-lg text-sm text-danger">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="label" htmlFor="login-email">Email address</label>
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="username"
                  placeholder="you@institution.edu"
                  className="input"
                />
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="label" htmlFor="login-password">Password</label>
                  <Link to="/forgot-password" className="text-xs text-brand-800 hover:underline mb-1">
                    Forgot password?
                  </Link>
                </div>
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="input"
                />
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full">
                <span>{loading ? 'Authenticating…' : 'Sign In'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            <div className="mt-6 pt-4 border-t border-line-200 flex items-center gap-1.5 text-xs text-ink-500">
              <Lock className="w-3.5 h-3.5 text-brand-800 shrink-0" />
              <span>Role-based access control is enforced on every request.</span>
            </div>
          </div>

          {/* Developer convenience only, and off by default — see the note at
              the top of this file. */}
          {SHOW_DEMO_PERSONAS && (
            <div className="glass-card p-5 mt-4">
              <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
                <h3 className="text-sm font-bold text-ink-900 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-brand-800" /> Demo persona quick login
                </h3>
                <span className="badge-brand">Seeded demo data</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SEEDED_ROLES.map((r) => (
                  <button
                    key={r.email}
                    onClick={() => handleQuickLogin(r.email)}
                    className="text-left p-2.5 rounded-lg bg-surface border border-line-200 hover:border-brand-500 hover:bg-brand-50 transition-all group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold text-brand-800">{r.role}</span>
                      <ArrowRight className="w-3 h-3 text-ink-400 group-hover:text-brand-800 transition-colors shrink-0" />
                    </div>
                    <p className="text-sm font-semibold text-ink-900 mt-0.5 truncate">{r.name}</p>
                    <p className="text-xs text-ink-500 truncate">{r.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
