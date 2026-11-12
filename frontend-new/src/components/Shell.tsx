import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import ingageLogo from '../assets/ingage-logo-mark.png';
import { useAuth } from '../context/AuthContext';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { useReviewMode } from '../hooks/useReviewMode';
import { NAV_GROUPS, PAGE_META, PAGE_STEP, nextActionFor, pathOf } from '../navigation';
import { getEvidenceRequestSummary } from '../services/evidenceRequests';
import type { EvidenceRequestSummary } from '../types/api';
import type { PageKey } from '../utils/access';
import { roleLabel } from '../utils/access';
import { initials } from '../utils/format';
import { PAGE_API_STATUS, STATUS_LABEL, STATUS_MARK, STATUS_TONE } from '../utils/apiStatus';
import { JOURNEY, journeyStep } from '../utils/journey';

const APP_TITLE = 'AI Ready Campus';

/** Sidebar + header + journey strip around every signed-in screen (prototype layout). */
export function Shell({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user, logout } = useAuth();
  const { canSee } = useAccess();
  const { sprints, sprint, select } = useSprint();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [review, setReview] = useReviewMode();
  const pageStatus = PAGE_API_STATUS[page];

  // Close the mobile menu after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  // Name the browser tab after the page (sidebar label), so tabs and history can be told apart.
  useEffect(() => {
    const name = NAV_GROUPS.flatMap((g) => g.items).find((item) => item.key === page)?.label ?? PAGE_META[page][1];
    document.title = `${name} · ${APP_TITLE}`;
    return () => { document.title = APP_TITLE; };
  }, [page]);

  const summary = useResource<EvidenceRequestSummary>(getEvidenceRequestSummary, `er-summary:${user?.id}`, canSee('requests'));
  const openForMe = (summary.data?.assigned_to_me || 0) + (summary.data?.awaiting_my_review || 0);
  const badges: Partial<Record<PageKey, number>> = { requests: summary.data?.assigned_to_me };

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
                    {review && (
                      <span className={`nav-status status ${STATUS_TONE[PAGE_API_STATUS[i.key].status]}`} title={STATUS_LABEL[PAGE_API_STATUS[i.key].status]}
                        aria-label={STATUS_LABEL[PAGE_API_STATUS[i.key].status]}>{STATUS_MARK[PAGE_API_STATUS[i.key].status]}</span>
                    )}
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
          <div className="breadcrumb"><strong>{PAGE_META[page][1]}</strong></div>
          <div className="header-actions">
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
            <button className={review ? 'primary-action' : 'secondary-button'} aria-pressed={review} title="Mark every screen with its backend status"
              onClick={() => setReview(!review)}>{review ? 'Review mode on' : 'Review mode'}</button>
            <button className="icon-button" title="Evidence search" aria-label="Evidence search" onClick={() => navigate('/copilot')}>⌕</button>
            <button className="icon-button notification" title="Data requests waiting for you" aria-label={`Data requests${openForMe ? `, ${openForMe} open` : ''}`} onClick={() => navigate(pathOf('requests'))}>
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
        <main className={`page page-${page}`} id="main">
          {review && (
            <div className={`notice notice-${pageStatus.status === 'live' ? 'success' : pageStatus.status === 'partial' ? 'warn' : 'error'}`} role="status">
              <div>
                <span className={`status ${STATUS_TONE[pageStatus.status]}`}>{STATUS_MARK[pageStatus.status]} {STATUS_LABEL[pageStatus.status]}</span>{' '}
                {pageStatus.pending.length === 0 ? 'Everything on this screen comes from the backend.'
                  : pageStatus.pending.map((x) => <span key={x.code}><b>{x.code}</b> {x.text}. </span>)}
                {' '}<Link to={pathOf('apistatus')}>All screens →</Link>
              </div>
            </div>
          )}
          {children}
        </main>
      </section>
    </div>
  );
}
