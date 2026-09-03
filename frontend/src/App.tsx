import React from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AppShell } from './layouts/AppShell';

import { Login } from './pages/auth/Login';
import { Dashboard } from './pages/dashboard/Dashboard';
import { InstitutionDNA } from './pages/institutions/InstitutionDNA';
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

const FullScreenLoading: React.FC = () => (
  <div className="min-h-screen bg-surface flex items-center justify-center text-sm text-ink-500">
    Loading...
  </div>
);

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />

      <Route path="/dashboard" element={<ProtectedLayout><Dashboard /></ProtectedLayout>} />
      <Route path="/institution-dna" element={<ProtectedLayout><InstitutionDNA /></ProtectedLayout>} />
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
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
