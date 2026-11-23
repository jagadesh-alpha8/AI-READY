import { createContext, useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import logo from '../assets/ingage-logo.png';
import { useAuth } from '../context/AuthContext';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getEvidenceRequestSummary } from '../services/evidenceRequests';
import { listRuns } from '../services/capability';
import type { EvidenceRequestSummary } from '../types/api';
import type { PageKey } from '../utils/access';
import { roleLabel } from '../utils/access';
import { initials } from '../utils/format';
import { pathOf } from '../navigation';
import { Icon } from './Icon';
import { JOURNEY_STEPS, SECTIONS, sectionOf, visibleTabs } from './sections';

/** True inside the workspace: the old screens' own page headings give way to the section heading and tabs. */
export const InWorkspace = createContext(false);

const STAFF_ROLES = new Set(['super_admin', 'consultant']);

/** Sidebar, header, section heading and tabs of Harsha's workspace design, around every signed-in screen. */
export function WorkspaceShell({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user, logout } = useAuth();
  const { canSee } = useAccess();
  const { sprints, sprint, select } = useSprint();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const section = sectionOf(page);
  const tabs = visibleTabs(section).filter((t) => canSee(t.page));
  const staff = STAFF_ROLES.has(user?.role || '');

  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    const tab = tabs.find((t) => t.page === page);
    document.title = `${tab && tabs.length > 1 ? `${tab.label} · ` : ''}${section.label} · AI READY`;
  }, [page, section, tabs]);

  const summary = useResource<EvidenceRequestSummary>(getEvidenceRequestSummary, `er-summary:${user?.id}`, canSee('requests'));
  const waiting = (summary.data?.assigned_to_me || 0) + (summary.data?.awaiting_my_review || 0);
  const institutionName = sprint?.institution_name || 'No institution yet';
  const manyInstitutions = new Set(sprints.map((s) => s.institution_id)).size > 1;
  const stepIndex = JOURNEY_STEPS.findIndex((s) => s.key === section.key);
  // How far the college has got, from its assessments (a light list call): a result means the documents and the
  // assessment are done; a final result means the results step is done too.
  const runs = useResource(() => listRuns(sprint!.id), `ws-journey:${sprint?.id}:${page}`, !!sprint && stepIndex >= 0);
  const completed = runs.data?.results.filter((r) => r.status === 'completed') || [];
  const reached = completed.some((r) => r.stage === 'final') ? 3 : completed.length ? 2 : -1;
  const isDone = (i: number) => (i < stepIndex || i <= reached) && i !== stepIndex;

  const firstPage = (key: string) => {
    const s = SECTIONS.find((x) => x.key === key)!;
    return visibleTabs(s).find((t) => canSee(t.page))?.page;
  };

  return (
    <InWorkspace.Provider value={true}>
      <div className={`ws ${menuOpen ? 'menu-open' : ''}`}>
        <a className="skip" href="#content">Skip to content</a>
        <aside id="sidebar" className={menuOpen ? 'open' : ''} aria-label="Main navigation">
          <div className="brand"><img src={logo} alt="InGage" /><div className="brand-name">AI READY<small>by InGage</small></div></div>
          <label className="campus-switch ws-campus">
            <span className="campus-icon"><Icon name="building" /></span>
            <span className="ws-campus-text"><strong title={institutionName}>{institutionName}</strong>
              <small>{sprint ? [sprint.name || sprint.sprint_code, sprint.academic_year].filter(Boolean).join(' · ') : 'Campus workspace'}</small></span>
            {sprints.length > 1 && <Icon name="down" />}
            {sprints.length > 1 && (
              <select aria-label="Switch institution or assessment" value={sprint?.id || ''} onChange={(e) => select(e.target.value)}>
                {sprints.map((s) => (
                  <option key={s.id} value={s.id}>{manyInstitutions ? `${s.institution_name} · ` : ''}{s.name || s.sprint_code}</option>
                ))}
              </select>
            )}
          </label>
          <div className="nav-label">Workspace</div>
          <nav className="nav" aria-label="Sections">
            {SECTIONS.filter((s) => !s.staff && s.key !== 'help').map((s) => {
              const target = firstPage(s.key);
              if (!target) return null;
              return (
                <NavLink key={s.key} to={pathOf(target)} className={() => (section.key === s.key ? 'active' : '')}
                  aria-current={section.key === s.key ? 'page' : undefined}>
                  <Icon name={s.icon} />{s.label}
                  {s.key === 'evidence' && waiting > 0 && <span className="count">{waiting}</span>}
                </NavLink>
              );
            })}
          </nav>
          {staff && (
            <>
              <div className="nav-divider" />
              <div className="nav-label">Manage</div>
              <nav className="nav">
                <NavLink to={pathOf(firstPage('admin') || 'admin')} className={() => (section.key === 'admin' ? 'active' : '')}>
                  <Icon name="settings" />Administration
                </NavLink>
              </nav>
            </>
          )}
          <div className="side-bottom">
            <NavLink className="help-link" to={pathOf('help')}><Icon name="help" />Help & guidance</NavLink>
            <div className="person">
              <span className="avatar">{initials(user?.name || user?.email)}</span>
              <div><strong>{user?.name || user?.email}</strong><small>{roleLabel(user?.role)}</small></div>
            </div>
            <button className="btn ws-signout" onClick={() => void logout()}>Sign out</button>
          </div>
        </aside>
        {menuOpen && <div className="ws-scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
        <div className="frame">
          <header id="topbar">
            <div className="actions">
              <button className="icon-btn mobile-menu" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
              <div className="crumb"><span>Workspace</span><Icon name="chevron" /><b>{section.label}</b></div>
            </div>
            <div className="header-right">
              {canSee('copilot') && (
                <button className="header-search" onClick={() => navigate(pathOf('copilot'))}><Icon name="search" /><span>Search your evidence</span></button>
              )}
              {canSee('requests') && (
                <button className="icon-btn" aria-label={`Requests waiting for you${waiting ? `: ${waiting}` : ''}`} title="Requests waiting for you"
                  onClick={() => navigate(pathOf('requests'))}>
                  <Icon name="bell" />{waiting > 0 && <i className="ws-dot" />}
                </button>
              )}
              <span className="avatar">{initials(user?.name || user?.email)}</span>
            </div>
          </header>
          <main id="content" tabIndex={-1}>
            <div className="fade">
              <div className="page-heading">
                <div>
                  <div className="eyebrow">{section.eyebrow}</div>
                  <h1>{section.title}</h1>
                  <p>{section.text}</p>
                </div>
              </div>
              {stepIndex >= 0 && (
                <div className="journey" aria-label="Assessment journey">
                  {JOURNEY_STEPS.map((s, i) => {
                    const target = firstPage(s.key);
                    return (
                      <button key={s.key} className={isDone(i) ? 'done' : i === stepIndex ? 'current' : ''}
                        onClick={() => target && navigate(pathOf(target))}>
                        <span className="step-n">{isDone(i) ? <Icon name="check" /> : i + 1}</span>
                        <span>{s.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
              {tabs.length > 1 && (
                <div className="tabs" role="tablist" aria-label={`${section.label} views`}>
                  {tabs.map((t) => (
                    <NavLink key={t.page} to={pathOf(t.page)} role="tab" aria-selected={t.page === page}
                      className={t.page === page ? 'active' : ''}>{t.label}</NavLink>
                  ))}
                </div>
              )}
              {children}
            </div>
          </main>
          <footer>InGage AI READY</footer>
        </div>
      </div>
    </InWorkspace.Provider>
  );
}
