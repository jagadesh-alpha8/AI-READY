import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { SprintContextBar } from '../components/SprintContextBar';
import { OnboardingGuideDrawer } from '../components/guide/OnboardingGuideDrawer';
import { ProductTourOverlay } from '../components/tour/ProductTourOverlay';
import { MenuTourOfferBanner } from '../components/tour/MenuTourOfferBanner';
import { useOnboardingGuide } from '../hooks/useOnboardingGuide';
import { useMenuTour } from '../context/MenuTourContext';
import type { MenuKey } from '../utils/access';

/** The authenticated app layout every pages/* screen is designed to sit
 * inside: Navbar across the top, Sidebar down the left (linking to the
 * selected sprint's steps), and the page content on the right -- headed by the
 * selected sprint on the dashboard and sprint pages (`showSprintBar`).
 * Below the lg breakpoint the sidebar becomes a slide-in drawer, toggled
 * from the Navbar's hamburger button. */
export const AppShell: React.FC<{
  children: React.ReactNode;
  showSprintBar?: boolean;
  currentMenu?: MenuKey;
}> = ({
  children,
  showSprintBar = false,
  currentMenu,
}) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const guide = useOnboardingGuide();
  const menuTour = useMenuTour();

  // Keep MenuTourContext synchronized with current menu
  useEffect(() => {
    menuTour.setCurrentMenuKey(currentMenu || null);
  }, [currentMenu, menuTour]);

  return (
    <div className="h-screen min-h-0 overflow-hidden bg-surface flex flex-col">
      <Navbar
        onMenuClick={() => setSidebarOpen(true)}
        onGuideClick={() => guide.setDrawerOpen(true)}
        onTourClick={() => menuTour.startNavTour()}
        guideCompletedCount={guide.completedCount}
        guideTotalSteps={guide.totalSteps}
        guideLoading={guide.loading}
      />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="flex-1 min-w-0 min-h-0 h-full overflow-y-auto overscroll-contain p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto w-full">
          {showSprintBar && <SprintContextBar />}
          <MenuTourOfferBanner />
          {children}
        </main>
      </div>

      <OnboardingGuideDrawer
        open={guide.drawerOpen}
        onClose={() => guide.setDrawerOpen(false)}
        steps={guide.steps}
        currentStepId={guide.currentStep?.id || null}
        completedCount={guide.completedCount}
        skippedCount={guide.skippedCount}
        totalSteps={guide.totalSteps}
        onStartTour={() => {
          menuTour.startNavTour();
        }}
        onSkip={(stepId) => guide.skipStep(stepId, true)}
        onUnskip={(stepId) => guide.skipStep(stepId, false)}
        onReset={guide.resetGuide}
        onSelectStep={(stepId) => guide.setSelectedStepId(stepId)}
      />

      {/* Contextual / Navigation Product Tour Overlay */}
      <ProductTourOverlay
        active={menuTour.tourActive}
        step={menuTour.currentStep}
        stepIndex={menuTour.currentStepIndex}
        totalSteps={menuTour.totalSteps}
        onNext={menuTour.nextStep}
        onPrev={menuTour.prevStep}
        onSkip={menuTour.skipStep}
        onFinish={menuTour.finishTour}
        onExit={menuTour.exitTour}
        onNavigate={menuTour.tourMode === 'navigation' ? undefined : (path) => navigate(path)}
        openSidebar={() => setSidebarOpen(true)}
      />

      {/* Overall Cross-Module Workflow Guide Tour Overlay */}
      <ProductTourOverlay
        active={!menuTour.tourActive && guide.tourActive}
        step={guide.currentTourStep}
        stepIndex={guide.tourStepIndex}
        totalSteps={guide.totalSteps}
        onNext={guide.nextTourStep}
        onPrev={guide.prevTourStep}
        onSkip={(stepId) => guide.skipTourStep(stepId as any)}
        onExit={guide.exitTour}
        onNavigate={(path) => navigate(path)}
        openSidebar={() => setSidebarOpen(true)}
      />
    </div>
  );
};
