import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import ingageLogo from '../assets/ingage-logo-mark.png';
import { useAuth } from '../context/AuthContext';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { NAV_GROUPS, PAGE_META, PAGE_STEP, nextActionFor, pathOf } from '../navigation';
import { getEvidenceRequestSummary } from '../services/evidenceRequests';
import type { EvidenceRequestSummary } from '../types/api';
import type { PageKey } from '../utils/access';
import { roleLabel } from '../utils/access';
import { initials } from '../utils/format';
import { JOURNEY, journeyStep } from '../utils/journey';

/** Sidebar + header + journey strip around every signed-in screen (prototype layout). */
export function Shell({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user, logout } = useAuth();
  const { canSee } = useAccess();
  const { sprints, sprint, select } = useSprint();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile menu after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const summary = useResource<EvidenceRequestSummary>(getEvidenceRequestSummary, `er-summary:${user?.id}`, canSee('requests'));
  const openForMe = (summary.data?.assigned_to_me || 0) + (summary.data?.awaiting_my_review || 0);
  const badges: Partial<Record<PageKey, number>> = { requests: summary.data?.assigned_to_me, notifications: summary.data?.assigned_to_me_overdue };

  const current = PAGE_STEP[page] ?? journeyStep(sprint?.status);
  const next = nextActionFor(sprint?.status);
  const institutionName = sprint?.institution_name || 'No sprint selected';
  const manyInstitutions = new Set(sprints.map((s) => s.institution_id)).size > 1;

  return (
    <div className="prototype">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`} id="sidebar" aria-label="Platform navigation">
        <div className="product-brand">
          {/* Brand guideline: on a coloured background the colour logo sits on a white clear area. */}
          <span className="brand-plate"><img className="brand-logo" src={ingageLogo} alt="Ingage" /></span>
          <div><strong>AI Ready Campus</strong><span>Maturity programme</span></div>
          <button className="sidebar-close" aria-label="Close menu" onClick={() => setMenuOpen(false)}>×</button>
        </div>
        <label className="institution-switcher">
          <span className="institution-logo" aria-hidden="true">{initials(institutionName)}</span>
          <div>
            <strong title={institutionName}>{institutionName}</strong>
            <span>{sprint ? [sprint.sprint_code, sprint.academic_year].filter(Boolean).join(' · ') : 'Create a sprint to begin'}</span>
          </div>
          {sprints.length > 0 && (
            <select aria-label="Switch audit sprint" value={sprint?.id || ''} onChange={(e) => select(e.target.value)}>
              {sprints.map((s) => (
                <option key={s.id} value={s.id}>
                  {/* Name the institution only when the list spans several, so a single college's sprints don't repeat it. */}
                  {manyInstitutions ? `${s.institution_name} · ` : ''}{s.name || s.sprint_code}{s.status === 'archived' ? ' (archived)' : ''}
                </option>
              ))}
            </select>
          )}
        </label>
        <nav className="side-nav">
          {NAV_GROUPS.map((g) => {
            const items = g.items.filter((i) => canSee(i.key));
            if (items.length === 0) return null;
            return (
              <div className="nav-group" key={g.label}>
                <div className="nav-label">{g.label}</div>
                {items.map((i) => (
                  <NavLink key={i.key} to={pathOf(i.key)} end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                    <span className="nav-icon" aria-hidden="true">{i.icon}</span>
                    <span>{i.label}</span>
                    {!!badges[i.key] && <span className="nav-badge">{badges[i.key]}</span>}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <Link to="/help" className="help-link"><span aria-hidden="true">?</span> Help & support</Link>
          <div className="user-chip">
            <span aria-hidden="true">{initials(user?.name || user?.email)}</span>
            <div><strong>{user?.name || user?.email}</strong><small>{roleLabel(user?.role)}</small></div>
            <button className="sign-out" onClick={() => void logout()}>Sign out</button>
          </div>
        </div>
      </aside>
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}

      <section className="app-frame">
        <header className="app-header">
          <button className="icon-button menu-button" aria-label="Open menu" aria-controls="sidebar" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>☰</button>
          <div className="breadcrumb"><span className="crumb-institution">{institutionName}&nbsp;/&nbsp;</span><strong>{PAGE_META[page][1]}</strong></div>
          <div className="header-actions">
            <button className="icon-button" title="Ask the AI advisor" aria-label="Search evidence" onClick={() => navigate('/copilot')}>⌕</button>
            <button className="icon-button notification" title="Notifications" aria-label={`Notifications${openForMe ? `, ${openForMe} open` : ''}`} onClick={() => navigate('/notifications')}>
              ◌{openForMe > 0 && <i />}
            </button>
            {canSee(next) && (
              <button className="primary-action" onClick={() => navigate(pathOf(next))}>
                {page === 'overview' ? 'Continue audit' : 'Next step'}
              </button>
            )}
          </div>
        </header>
        <ol className="journey-strip" aria-label="Journey">
          {JOURNEY.map((label, i) => (
            <li key={label} className={`journey-step ${i < current ? 'done' : i === current ? 'current' : ''}`} aria-current={i === current ? 'step' : undefined}>
              <span>{i < current ? '✓' : i + 1}</span><b>{label}</b>
            </li>
          ))}
        </ol>
        <main className={`page page-${page}`} id="main">{children}</main>
      </section>
    </div>
  );
}
