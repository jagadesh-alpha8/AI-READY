import React from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AppShell } from './layouts/AppShell';
import { ScrollToTop } from './components/ScrollToTop';

import { Login } from './pages/auth/Login';
import { ForgotPassword, ResetPassword } from './pages/auth/PasswordReset';
import { Dashboard } from './pages/dashboard/Dashboard';
import { InstitutionList } from './pages/institutions/InstitutionList';
import { InstitutionDetail } from './pages/institutions/InstitutionDetail';
import { StatusDashboard } from './pages/status/StatusDashboard';
import { ModulePreview } from './pages/previews/ModulePreview';
import { AdminSettings } from './pages/admin/AdminSettings';
// Platform modules (originally ported from the InGage prototype; all now read
// real API data).
import { EvidenceIntelligence } from './pages/evidence/EvidenceIntelligence';
import { CriBenchmarkIntelligence } from './pages/benchmark/CriBenchmarkIntelligence';
import { BenchmarkStudio } from './pages/benchmark/BenchmarkStudio';
import { BenchmarkAssessments } from './pages/assessments/BenchmarkAssessments';
import { TransformationPlan } from './pages/workspace/TransformationPlan';
import { GoalsTasks } from './pages/workspace/GoalsTasks';
import { AICopilot } from './pages/chat/AICopilot';
import { Reminders } from './pages/workspace/Reminders';
import { ComplianceMapping } from './pages/compliance/ComplianceMapping';
import { UatReadiness } from './pages/workspace/UatReadiness';
import { SprintSetup } from './pages/sprints/SprintSetup';
import { UploadDataPack } from './pages/documents/UploadDataPack';
import { AIProcessingMonitor } from './pages/documents/AIProcessingMonitor';
import { FactsReview } from './pages/facts/FactsReview';
import { ConfirmationWorkspace } from './pages/facts/ConfirmationWorkspace';
import { GapDashboard } from './pages/gaps/GapDashboard';
import { LiveCRIPreview } from './pages/scoring/LiveCRIPreview';
import { BaselineApproval } from './pages/scoring/BaselineApproval';
import { RecommendationsReview } from './pages/recommendations/RecommendationsReview';
import { ReportPreviewExport } from './pages/reports/ReportPreviewExport';

/** /login itself, redirecting away if a session is already active. */
const LoginRoute: React.FC = () => {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenLoading />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
};

/** Every other route: requires a session, then wraps the page in the
 * Navbar/Sidebar shell (aware of :sprintId when the current route has one). */
const ProtectedLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  const { sprintId } = useParams<{ sprintId: string }>();

  if (loading) return <FullScreenLoading />;
  if (!user) return <Navigate to="/login" replace />;
  return <AppShell activeSprintId={sprintId}>{children}</AppShell>;
};

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

      <Route path="/dashboard" element={<ProtectedLayout><Dashboard /></ProtectedLayout>} />
      <Route path="/institution-dna" element={<ProtectedLayout><InstitutionList /></ProtectedLayout>} />
      <Route path="/institution-dna/:institutionId" element={<ProtectedLayout><InstitutionDetail /></ProtectedLayout>} />
      {/* Build-progress report, deliberately OUTSIDE the app shell and absent
          from the sidebar: it reports on how much of the product plan exists,
          which makes it a report about the app rather than a module of it.
          Reached by URL. Still requires a session — it names unbuilt work. */}
      <Route path="/status-dashboard" element={<StandaloneRoute><StatusDashboard /></StandaloneRoute>} />

      {/* Ported from the InGage prototype: real screens, demo data. */}
      <Route path="/evidence" element={<ProtectedLayout><EvidenceIntelligence /></ProtectedLayout>} />
      <Route path="/cri-benchmark" element={<ProtectedLayout><CriBenchmarkIntelligence /></ProtectedLayout>} />
      <Route path="/benchmark-studio" element={<ProtectedLayout><BenchmarkStudio /></ProtectedLayout>} />
      <Route path="/benchmark-assessment" element={<ProtectedLayout><BenchmarkAssessments /></ProtectedLayout>} />
      <Route path="/transformation-plan" element={<ProtectedLayout><TransformationPlan /></ProtectedLayout>} />
      <Route path="/goals-tasks" element={<ProtectedLayout><GoalsTasks /></ProtectedLayout>} />
      <Route path="/ai-copilot" element={<ProtectedLayout><AICopilot /></ProtectedLayout>} />
      <Route path="/reminders" element={<ProtectedLayout><Reminders /></ProtectedLayout>} />
      <Route path="/compliance" element={<ProtectedLayout><ComplianceMapping /></ProtectedLayout>} />
      <Route path="/uat-readiness" element={<ProtectedLayout><UatReadiness /></ProtectedLayout>} />
      <Route path="/admin-settings" element={<ProtectedLayout><AdminSettings /></ProtectedLayout>} />

      {/* Design previews for the modules with no prototype screen to port.
          Every one of these says so at the top — see ModulePreview. */}
      <Route path="/preview/:moduleKey" element={<ProtectedLayout><ModulePreview /></ProtectedLayout>} />
      <Route path="/sprint/setup" element={<ProtectedLayout><SprintSetup /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/upload" element={<ProtectedLayout><UploadDataPack /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/monitor" element={<ProtectedLayout><AIProcessingMonitor /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/facts" element={<ProtectedLayout><FactsReview /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/gaps" element={<ProtectedLayout><GapDashboard /></ProtectedLayout>} />
      <Route
        path="/sprint/:sprintId/confirmation"
        element={<ProtectedLayout><ConfirmationWorkspace /></ProtectedLayout>}
      />
      <Route path="/sprint/:sprintId/score" element={<ProtectedLayout><LiveCRIPreview /></ProtectedLayout>} />
      <Route path="/sprint/:sprintId/approval" element={<ProtectedLayout><BaselineApproval /></ProtectedLayout>} />
      <Route
        path="/sprint/:sprintId/recommendations"
        element={<ProtectedLayout><RecommendationsReview /></ProtectedLayout>}
      />
      <Route path="/sprint/:sprintId/report" element={<ProtectedLayout><ReportPreviewExport /></ProtectedLayout>} />

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
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
