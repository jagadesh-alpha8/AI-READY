import React from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { SelectedSprintProvider, useSelectedSprint } from './context/SelectedSprintContext';
import { MenuTourProvider } from './context/MenuTourContext';
import { ThemeProvider } from './context/ThemeContext';
import { AppShell } from './layouts/AppShell';
import { ScrollToTop } from './components/ScrollToTop';
import { DialogHost } from './components/Dialog';
import { NoAccess } from './components/NoAccess';
import { canSeeMenu } from './utils/access';
import type { MenuKey } from './utils/access';

import { Login } from './pages/auth/Login';
import { ForgotPassword, ResetPassword } from './pages/auth/PasswordReset';
import { ActivateAccount } from './pages/auth/ActivateAccount';
import { Dashboard } from './pages/dashboard/Dashboard';
import { InstitutionList } from './pages/institutions/InstitutionList';
import { InstitutionDetail } from './pages/institutions/InstitutionDetail';
import { StatusDashboard } from './pages/status/StatusDashboard';
import { ModulePreview } from './pages/previews/ModulePreview';
import { AdminSettings } from './pages/admin/AdminSettings';
// Platform modules (originally ported from the InGage prototype; all now read
// real API data).
import { BenchmarkStudio } from './pages/benchmark/BenchmarkStudio';
import { BenchmarkAssessments } from './pages/assessments/BenchmarkAssessments';
import { SprintSetup } from './pages/sprints/SprintSetup';
import { AIQIFExpertQueue } from './pages/facts/AIQIFExpertQueue';
import { EvidenceWorkspace, UploadWorkspace, WorkspaceRedirect } from './pages/evidence/EvidenceWorkspace';
import { CapabilityWorkspace } from './pages/capability/CapabilityWorkspace';

/** /login itself, redirecting away if a session is already active. */
const LoginRoute: React.FC = () => {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenLoading />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
};

/** Every other route: requires a session, then wraps the page in the
 * Navbar/Sidebar shell. `menu` names the menu entry the page belongs to; a
 * role that may not see that menu (utils/access.ts) gets "No access" instead
 * of the page.
 *
 * `sprint` is how the page relates to the selected sprint
 * (context/SelectedSprintContext.tsx): 'show' puts the selected-sprint header
 * on top (the dashboard, and /sprint/:sprintId pages, whose URL is the
 * selection); 'required' also waits for the selection and remounts the page
 * when it changes (module pages that read the sprint from the context). Both
 * remount the page on a switch, so nothing of the previous sprint stays on
 * screen. */
const ProtectedLayout: React.FC<{ children: React.ReactNode; menu?: MenuKey; sprint?: 'show' | 'required' }> = ({
  children, menu, sprint,
}) => {
  const { user, loading } = useAuth();
  const { sprintId: routeSprintId } = useParams<{ sprintId: string }>();
  const selection = useSelectedSprint();

  if (loading) return <FullScreenLoading />;
  if (!user) return <Navigate to="/login" replace />;
  const allowed = !menu || canSeeMenu(user.role, menu);
  let page: React.ReactNode = allowed ? children : <NoAccess />;
  if (allowed && sprint === 'required' && selection.status === 'loading' && !selection.loadError) page = <FullPageLoading />;
  // A new sprint = a fresh page (state, requests and all).
  const pageKey = sprint ? `sprint:${routeSprintId || selection.sprintId || 'none'}` : undefined;
  return (
    <AppShell showSprintBar={!!sprint && allowed} currentMenu={menu}>
      <React.Fragment key={pageKey}>{page}</React.Fragment>
    </AppShell>
  );
};

const FullPageLoading: React.FC = () => <div className="text-sm text-ink-500 py-10 text-center">Loading...</div>;

/** A session-guarded page with no Navbar and no Sidebar.
 *
 * For pages that are *about* the product rather than part of it — today just
 * the build-status report. Keeping the shell off is the point: the page is
 * opened on its own to be read or shown, not navigated away from, and the
 * surrounding chrome would only invite someone to read it as a module. */
const StandaloneRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) return <FullScreenLoading />;
  if (!user) return <Navigate to="/login" replace />;
  return <div className="min-h-screen bg-surface p-4 sm:p-6 lg:p-8">{children}</div>;
};

const FullScreenLoading: React.FC = () => (
  <div className="min-h-screen bg-surface flex items-center justify-center text-sm text-ink-500">
    Loading...
  </div>
);

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      {/* The IQAC Coordinator invitation link (public, single use). */}
      <Route path="/activate-account" element={<ActivateAccount />} />

      <Route path="/dashboard" element={<ProtectedLayout menu="dashboard" sprint="show"><Dashboard /></ProtectedLayout>} />
      <Route path="/institution-dna" element={<ProtectedLayout menu="institution-dna"><InstitutionList /></ProtectedLayout>} />
      <Route path="/institution-dna/:institutionId" element={<ProtectedLayout menu="institution-dna"><InstitutionDetail /></ProtectedLayout>} />
      {/* Build-progress report, deliberately OUTSIDE the app shell and absent
          from the sidebar: it reports on how much of the product plan exists,
          which makes it a report about the app rather than a module of it.
          Reached by URL. Still requires a session — it names unbuilt work. */}
      <Route path="/status-dashboard" element={<StandaloneRoute><StatusDashboard /></StandaloneRoute>} />

      {/* Canonical workspaces; earlier bookmarks redirect to the matching section. */}
      <Route path="/evidence" element={<ProtectedLayout menu="evidence-intelligence" sprint="required"><WorkspaceRedirect tab="documents" /></ProtectedLayout>} />
      <Route path="/cri-benchmark" element={<ProtectedLayout menu="cri-benchmark-intelligence" sprint="required"><CapabilityWorkspace /></ProtectedLayout>} />
      <Route path="/benchmark-studio" element={<ProtectedLayout menu="benchmark-studio"><BenchmarkStudio /></ProtectedLayout>} />
      <Route path="/benchmark-assessment" element={<ProtectedLayout menu="benchmark-assessment"><BenchmarkAssessments /></ProtectedLayout>} />
      <Route path="/transformation-plan" element={<ProtectedLayout menu="transformation-plan" sprint="required"><WorkspaceRedirect actions /></ProtectedLayout>} />
      <Route path="/goals-tasks" element={<ProtectedLayout menu="goals-tasks" sprint="required"><WorkspaceRedirect actions /></ProtectedLayout>} />
      <Route path="/compliance" element={<ProtectedLayout menu="compliance-mapping" sprint="required"><WorkspaceRedirect tab="accreditation" /></ProtectedLayout>} />
      <Route path="/admin-settings" element={<ProtectedLayout menu="admin-settings"><AdminSettings /></ProtectedLayout>} />

      {/* Design previews for the modules with no prototype screen to port.
          Every one of these says so at the top — see ModulePreview. */}
      <Route path="/preview/:moduleKey" element={<ProtectedLayout><ModulePreview /></ProtectedLayout>} />
      <Route path="/sprint/setup" element={<ProtectedLayout menu="sprint-setup"><SprintSetup /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/upload" element={<ProtectedLayout menu="sprint-upload" sprint="show"><UploadWorkspace /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/monitor" element={<ProtectedLayout menu="sprint-monitor" sprint="show"><WorkspaceRedirect upload /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/evidence" element={<ProtectedLayout menu="evidence-intelligence" sprint="show"><EvidenceWorkspace /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/facts" element={<ProtectedLayout menu="sprint-facts" sprint="show"><WorkspaceRedirect tab="review" /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/aiqif-review" element={<ProtectedLayout menu="sprint-aiqif-review" sprint="show"><AIQIFExpertQueue /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/gaps" element={<ProtectedLayout menu="sprint-gaps" sprint="show"><WorkspaceRedirect tab="gaps" /></ProtectedLayout>} />
      <Route
        path="/sprint/:sprintId/confirmation"
        element={<ProtectedLayout menu="sprint-confirmation" sprint="show"><WorkspaceRedirect tab="review" /></ProtectedLayout>}
      />
      <Route path="/sprint/:sprintId/score" element={<ProtectedLayout menu="sprint-score" sprint="show"><CapabilityWorkspace /></ProtectedLayout>} />
      <Route
        path="/sprint/:sprintId/recommendations"
        element={<ProtectedLayout menu="sprint-recommendations" sprint="show"><CapabilityWorkspace mode="actions" /></ProtectedLayout>}
      />
      <Route path="/sprint/:sprintId/report" element={<ProtectedLayout menu="sprint-report" sprint="show"><CapabilityWorkspace mode="report" /></ProtectedLayout>} />


      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          {/* Inside the Router so it can watch the location; outside the
              routes so a navigation resets scroll before the new screen
              paints. */}
          <ScrollToTop />
          <SelectedSprintProvider>
            <MenuTourProvider>
              <AppRoutes />
            </MenuTourProvider>
          </SelectedSprintProvider>
          <DialogHost />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
