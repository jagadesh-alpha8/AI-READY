import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { SprintProvider } from './context/SprintContext';
import { Shell } from './components/Shell';
import { Empty, Loading, PageLink } from './components/ui';
import { canSeePage, type PageKey } from './utils/access';
import { pathOf } from './navigation';

import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Onboarding } from './pages/Onboarding';
import { Profile } from './pages/Profile';
import { SprintSetup } from './pages/SprintSetup';
import { DataRequests } from './pages/DataRequests';
import { Uploads } from './pages/Uploads';
import { EvidenceIntelligence } from './pages/EvidenceIntelligence';
import { EvidenceReview } from './pages/EvidenceReview';
import { Assessment } from './pages/Assessment';
import { BenchmarkComparison } from './pages/BenchmarkComparison';
import { GapAnalysis } from './pages/GapAnalysis';
import { CriStanding } from './pages/CriStanding';
import { Pathway } from './pages/Pathway';
import { TransformationPlan } from './pages/TransformationPlan';
import { GoalsTasks } from './pages/GoalsTasks';
import { Progress } from './pages/Progress';
import { Reports } from './pages/Reports';
import { Advisor } from './pages/Advisor';
import { Compliance } from './pages/Compliance';
import { Team } from './pages/Team';
import { Notifications } from './pages/Notifications';
import { BenchmarkStudio } from './pages/BenchmarkStudio';
import { Settings } from './pages/Settings';
import { Help } from './pages/Help';

const PAGES: Record<PageKey, () => JSX.Element> = {
  overview: Overview,
  onboarding: Onboarding,
  profile: Profile,
  sprint: SprintSetup,
  requests: DataRequests,
  uploads: Uploads,
  evidence: EvidenceIntelligence,
  review: EvidenceReview,
  assessment: Assessment,
  benchmark: BenchmarkComparison,
  gaps: GapAnalysis,
  cri: CriStanding,
  pathway: Pathway,
  plan: TransformationPlan,
  goals: GoalsTasks,
  progress: Progress,
  reports: Reports,
  copilot: Advisor,
  compliance: Compliance,
  team: Team,
  notifications: Notifications,
  benchmarkstudio: BenchmarkStudio,
  admin: Settings,
  help: Help,
};

function Protected({ page, children }: { page: PageKey; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="fullscreen"><Loading label="Signing in…" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Shell page={page}>
      {canSeePage(user.role, page) ? children : (
        <Empty title="No access" action={<PageLink to="overview">Back to overview</PageLink>}>
          Your role does not include this screen.
        </Empty>
      )}
    </Shell>
  );
}

function LoginRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="fullscreen"><Loading /></div>;
  return user ? <Navigate to="/" replace /> : <Login />;
}

export function App() {
  return (
    <AuthProvider>
      <SprintProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginRoute />} />
            {(Object.keys(PAGES) as PageKey[]).map((key) => {
              const Page = PAGES[key];
              return <Route key={key} path={pathOf(key)} element={<Protected page={key}><Page /></Protected>} />;
            })}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </SprintProvider>
    </AuthProvider>
  );
}
