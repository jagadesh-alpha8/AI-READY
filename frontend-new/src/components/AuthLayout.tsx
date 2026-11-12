import type { ReactNode } from 'react';
import ingageLogo from '../assets/ingage-logo-mark.png';

/**
 * The signed-out pages (sign in, password reset, account activation): the journey on the left, the page's card
 * on the right. Content describes what the product does; nothing here is a figure the platform cannot show.
 */
const STEPS = [
  ['Discover', 'Institution and sprint'],
  ['Verify', 'Upload and review evidence'],
  ['Assess', 'CRI and maturity level'],
  ['Transform', 'Goals and tasks'],
  ['Advance', 'Reassess, reach the next level'],
] as const;

/** The nine AI-QIF pillars the CRI is scored across (backend apps/scoring/constants.py, short names). */
const PILLARS = [
  'Strategy & Governance', 'Responsible AI', 'Curriculum & Learning', 'Faculty Capability', 'Student Readiness',
  'Infrastructure & Data', 'Research & Innovation', 'Operations & Outcomes', 'Assurance & Improvement',
];

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-page">
      <div className="auth-grid">
        <section className="auth-intro" aria-labelledby="auth-heading">
          <img className="auth-logo" src={ingageLogo} alt="Ingage" />
          <span className="eyebrow">Maturity programme</span>
          <h1 id="auth-heading">From first upload to verified AI readiness.</h1>
          <p className="auth-lead">One guided journey for IQAC teams and InGage consultants, with every step backed by evidence.</p>

          <ol className="auth-steps" aria-label="The journey">
            {STEPS.map(([name, text], i) => (
              <li key={name}>
                <b aria-hidden="true">{i + 1}</b>
                <span>{name}</span>
                <small>{text}</small>
              </li>
            ))}
          </ol>

          <div className="auth-pillars">
            <span className="eyebrow">Nine AI-QIF pillars · 36 key indicators</span>
            <ul>{PILLARS.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
          <p className="auth-foot">Built by InGage Technologies. Access is role-based and checked on the server.</p>
        </section>

        <section className="auth-card-col">{children}</section>
      </div>
    </div>
  );
}

/** The white card on the right, shared by every signed-out page. */
export function AuthCard({ title, lead, children, note }: { title: string; lead: string; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="auth-card">
      <h2>{title}</h2>
      <p className="auth-card-lead">{lead}</p>
      {children}
      {note && (
        <p className="auth-note">
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" focusable="false">
            <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              d="M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3" />
          </svg>
          {note}
        </p>
      )}
    </div>
  );
}

/** Arrow used on the primary button of each card. */
export function ArrowRight() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
