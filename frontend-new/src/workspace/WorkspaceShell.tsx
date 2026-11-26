import { createContext, useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import logo from '../assets/ingage-logo.png';
import { useAuth } from '../context/AuthContext';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getEvidenceRequestSummary } from '../services/evidenceRequests';
import { JOURNEY, useJourney } from './journey';
import type { EvidenceRequestSummary } from '../types/api';
import type { PageKey } from '../utils/access';
import { roleLabel } from '../utils/access';
import { initials } from '../utils/format';
import { pathOf } from '../navigation';
import { Icon } from './Icon';
import { SECTIONS, sectionOf, tabOf, visibleTabs } from './sections';

/** True inside the workspace: the old screens' own page headings give way to the section heading and tabs. */
export const InWorkspace = createContext(false);

const STAFF_ROLES = new Set(['super_admin', 'consultant']);

const Beta = () => <span className="tag ws-beta">Beta</span>;

/** Sidebar, header, progress bar, heading and tabs of the merged website design (27 Nov 2026: Harsha's six
 * workspaces around our result screens), around every signed-in screen. */
export function WorkspaceShell({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user, logout } = useAuth();
  const { canSee } = useAccess();
  const { sprints, sprint, select } = useSprint();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const section = sectionOf(page);
  const staff = STAFF_ROLES.has(user?.role || '');
  const tabs = visibleTabs(section, staff).filter((t) => canSee(t.page));
  const tab = tabOf(page);
  const journey = useJourney(sprint);

  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    document.title = `${tab && tabs.length > 1 ? `${tab.label} · ` : ''}${section.label} · AI READY`;
  }, [page, section, tab, tabs.length]);

  const summary = useResource<EvidenceRequestSummary>(getEvidenceRequestSummary, `er-summary:${user?.id}`, canSee('requests'));
  const waiting = (summary.data?.assigned_to_me || 0) + (summary.data?.awaiting_my_review || 0);
  const institutionName = sprint?.institution_name || 'No institution yet';
  const manyInstitutions = new Set(sprints.map((s) => s.institution_id)).size > 1;
  // Staff see a note on the result pages when what they see is not what the college sees.
  const resultPage = ['overview', 'results', 'plan', 'assessment'].includes(section.key);
  const shown = journey.shown;

  const firstPage = (key: string) => {
    const s = SECTIONS.find((x) => x.key === key)!;
    return visibleTabs(s, staff).find((t) => canSee(t.page))?.page;
  };
  const navItem = (s: (typeof SECTIONS)[number]) => {
    const target = firstPage(s.key);
    if (!target) return null;
    return (
      <NavLink key={s.key} to={pathOf(target)} className={() => (section.key === s.key ? 'active' : '')}
        aria-current={section.key === s.key ? 'page' : undefined}>
        <Icon name={s.icon} />{s.label}
        {s.key === 'documents' && waiting > 0 && <span className="count" aria-label={`${waiting} waiting for you`}>{waiting}</span>}
        {s.key === 'assessment' && journey.stage1 && !journey.closed && (journey.open ?? 0) > 0 && (
          <span className="ws-nav-dot" title="Follow-up questions to answer" aria-label="Follow-up questions to answer" />
        )}
      </NavLink>
    );
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
            {SECTIONS.filter((s) => !s.staff && s.key !== 'help').map(navItem)}
          </nav>
          {staff && (
            <>
              <div className="nav-divider" />
              <div className="nav-label">InGage staff only</div>
              <nav className="nav" aria-label="Staff sections">{SECTIONS.filter((s) => s.staff).map(navItem)}</nav>
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
                <button className="header-search ws-search-btn" onClick={() => navigate(pathOf('copilot'))}><Icon name="search" /><span>Search your documents</span></button>
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
          {sprint && (
            <nav className="ws-progress" aria-label="Where your assessment is">
              <ol>
                {JOURNEY.map((s, i) => {
                  const state = i < journey.current ? 'done' : i === journey.current ? 'current' : 'todo';
                  return (
                    <li key={s.label} className={state} aria-current={state === 'current' ? 'step' : undefined}>
                      <NavLink to={pathOf(s.page)}>
                        <span className="n" aria-hidden="true">{state === 'done' ? <Icon name="check" size={12} /> : i + 1}</span>
                        <span>{s.label}<span className="ws-sr">{state === 'done' ? ', done' : state === 'current' ? ', current step' : ''}</span></span>
                      </NavLink>
                    </li>
                  );
                })}
              </ol>
            </nav>
          )}
          <main id="content" tabIndex={-1}>
            <div className="fade">
              <div className="page-heading">
                <div>
                  <h1>{tab?.title || section.title}{tab?.beta && <Beta />}</h1>
                  <p>{tab?.text || section.text}</p>
                </div>
              </div>
              {staff && resultPage && (shown.preview || shown.newer) && (
                <div className="callout ws-publication-note" role="status"><Icon name="help" />
                  <p>{shown.preview
                    ? <><strong>Not published.</strong> You are seeing the newest result; the college sees nothing until a result is published{journey.autoPublish ? ' (it publishes itself once its reports are written and pass the checks)' : ''}.</>
                    : <><strong>A newer result is not published.</strong> The college still sees the published one.</>}
                  {' '}<NavLink to={pathOf('assessment')}>Choose what the college sees</NavLink></p>
                </div>
              )}
              {tabs.length > 1 && (
                <div className="tabs" role="tablist" aria-label={`${section.label} views`}>
                  {tabs.map((t) => (
                    <NavLink key={t.page} to={pathOf(t.page)} role="tab" aria-selected={t.page === page}
                      className={t.page === page ? 'active' : ''}>{t.label}{t.beta && <Beta />}</NavLink>
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
