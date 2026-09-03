import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { getErrorMessage } from '../../utils/errors';
import { Shield, ArrowRight, Lock } from 'lucide-react';
import ingageLogo from '../../assets/ingage-logo-mark.png';

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

export const Login: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState('superadmin@ingage.ai');
  const [password, setPassword] = useState('Password123!');
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
      await login(targetEmail, 'Password123!');
    } catch (err: any) {
      setError(getErrorMessage(err, 'Quick login failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center py-10 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full max-w-4xl text-center mb-8">
        <img src={ingageLogo} alt="Ingage" className="h-10 sm:h-12 w-auto mx-auto mb-5" />
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-900 tracking-tight text-balance">
          AIOS AI Readiness Discovery Sprint Platform
        </h1>
        <p className="mt-2 text-sm text-ink-500 max-w-xl mx-auto">
          Fast-Track Discovery Platform for Higher Education Institutions by InGage Technologies.
        </p>
      </div>

      <div className="max-w-5xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
        {/* Left: Custom Login Form */}
        <div className="lg:col-span-5 glass-card p-6 sm:p-8 flex flex-col justify-between">
          <div>
            <h2 className="text-xl font-bold text-ink-900 mb-1">Sign In to Discovery Sprint</h2>
            <p className="text-sm text-ink-500 mb-6">Enter your institutional credentials</p>

            {error && (
              <div className="mb-4 p-3 bg-danger-bg border border-danger-line rounded-lg text-sm text-danger">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="label">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="input"
                />
              </div>

              <div>
                <label className="label">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="input"
                />
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full">
                <span>{loading ? 'Authenticating...' : 'Sign In'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          </div>

          <div className="mt-8 pt-4 border-t border-line-200 text-xs text-ink-500 flex items-center justify-between flex-wrap gap-2">
            <span className="flex items-center gap-1"><Lock className="w-3.5 h-3.5 text-brand-800" /> RBAC Enforced</span>
            <span>Default PW: Password123!</span>
          </div>
        </div>

        {/* Right: Quick Login Grid for All 11 Roles */}
        <div className="lg:col-span-7 glass-card p-5 sm:p-6">
          <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
            <div>
              <h3 className="text-sm font-bold text-ink-900 flex items-center gap-2">
                <Shield className="w-4 h-4 text-brand-800" /> Demo Persona Quick Login (11 Roles)
              </h3>
              <p className="text-xs text-ink-500 mt-0.5">Click any persona to log in immediately and test role permissions</p>
            </div>
            <span className="badge-brand">Seeded Demo Data</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {SEEDED_ROLES.map((r) => (
              <button
                key={r.email}
                onClick={() => handleQuickLogin(r.email)}
                className="text-left p-3 rounded-lg bg-surface border border-line-200 hover:border-brand-500 hover:bg-brand-50 transition-all group"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-brand-800">{r.role}</span>
                  <ArrowRight className="w-3.5 h-3.5 text-ink-400 group-hover:text-brand-800 transition-colors shrink-0" />
                </div>
                <p className="text-sm font-semibold text-ink-900 mt-0.5 truncate">{r.name}</p>
                <p className="text-xs text-ink-500 truncate">{r.desc}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
