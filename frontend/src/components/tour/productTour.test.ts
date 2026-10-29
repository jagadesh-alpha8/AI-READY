import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { MenuTourStep } from '../../types/guide';

describe('interactive product tour for every role-accessible menu', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');

  const tourBundle = await bundleComponent(new URL('./ProductTourOverlay.tsx', import.meta.url), {});
  const offerBundle = await bundleComponent(new URL('./MenuTourOfferBanner.tsx', import.meta.url), {
    '../../context/MenuTourContext': `
      export const useMenuTour = () => ({
        currentMenuKey: 'sprint-report',
        isOfferVisible: () => true,
        isTourAvailable: () => true,
        startTour: () => {},
        dismissOffer: () => {},
      });
    `,
  });
  const menuToursBundle = await bundleComponent(new URL('./menuTours.ts', import.meta.url), {});
  const { ALL_MENU_TOURS, getMenuTour, getNavigationTour } = menuToursBundle.mod;

  after(() => {
    tourBundle.cleanup();
    offerBundle.cleanup();
    menuToursBundle.cleanup();
  });

  const ALL_25_MENUS = [
    'dashboard',
    'institution-dna',
    'sprint-setup',
    'sprint-upload',
    'sprint-monitor',
    'evidence-intelligence',
    'sprint-facts',
    'sprint-aiqif-review',
    'evidence-requests',
    'sprint-gaps',
    'sprint-confirmation',
    'sprint-score',
    'sprint-approval',
    'sprint-recommendations',
    'sprint-report',
    'cri-benchmark-intelligence',
    'benchmark-studio',
    'benchmark-assessment',
    'transformation-plan',
    'goals-tasks',
    'ai-copilot',
    'reminders',
    'compliance-mapping',
    'uat-readiness',
    'admin-settings',
  ];

  it('defines structured tours for all 25 menus in the platform', () => {
    assert.equal(ALL_MENU_TOURS.length, 25);
    const menuKeys = ALL_MENU_TOURS.map((t: any) => t.menuKey);
    for (const key of ALL_25_MENUS) {
      assert.ok(menuKeys.includes(key), `Menu ${key} should be defined in ALL_MENU_TOURS`);
    }
  });

  it('ensures every tour step has a stable target, title, purpose, and location', () => {
    for (const tour of ALL_MENU_TOURS) {
      assert.ok(tour.steps.length > 0, `Tour for ${tour.menuKey} must have at least one step`);
      for (const step of tour.steps) {
        assert.ok(step.id, `Step in ${tour.menuKey} missing id`);
        assert.ok(step.title, `Step in ${tour.menuKey} missing title`);
        assert.ok(step.purpose, `Step in ${tour.menuKey} missing purpose`);
        assert.ok(step.tour_target, `Step in ${tour.menuKey} missing tour_target`);
        assert.ok(step.tour_location, `Step in ${tour.menuKey} missing tour_location`);
      }
    }
  });

  it('strictly respects role accessibility matrix for menu tours', () => {
    // 1. sprint-aiqif-review: Super Admin only
    assert.ok(getMenuTour('sprint-aiqif-review', 'super_admin') !== null);
    assert.equal(getMenuTour('sprint-aiqif-review', 'consultant'), null);
    assert.equal(getMenuTour('sprint-aiqif-review', 'iqac_coordinator'), null);

    // 2. benchmark-studio: Super Admin & Consultant only
    assert.ok(getMenuTour('benchmark-studio', 'super_admin') !== null);
    assert.ok(getMenuTour('benchmark-studio', 'consultant') !== null);
    assert.equal(getMenuTour('benchmark-studio', 'iqac_coordinator'), null);

    // 3. sprint-confirmation: Consultant & IQAC Coordinator only
    assert.equal(getMenuTour('sprint-confirmation', 'super_admin'), null);
    assert.ok(getMenuTour('sprint-confirmation', 'consultant') !== null);
    assert.ok(getMenuTour('sprint-confirmation', 'iqac_coordinator') !== null);

    // 4. dashboard: all roles
    assert.ok(getMenuTour('dashboard', 'super_admin') !== null);
    assert.ok(getMenuTour('dashboard', 'consultant') !== null);
    assert.ok(getMenuTour('dashboard', 'iqac_coordinator') !== null);
  });

  it('renders MenuTourOfferBanner with expanded invitation, Take Tour button, and Not now collapse action', () => {
    const html = renderToStaticMarkup(
      React.createElement(offerBundle.mod.MenuTourOfferBanner, {})
    );

    assert.ok(html.includes('Welcome to'));
    assert.ok(html.includes('steps'));
    assert.ok(html.includes('Take Tour'));
    assert.ok(html.includes('Not now'));
  });

  it('generates role-aware navigation tours with stable targets for each role', () => {
    const adminNavTour = getNavigationTour('super_admin');
    const consultantNavTour = getNavigationTour('consultant');
    const iqacNavTour = getNavigationTour('iqac_coordinator');

    // Super Admin: benchmark-studio included, sprint-confirmation excluded
    const adminTargets = adminNavTour.steps.map((s: any) => s.tour_target);
    assert.ok(adminTargets.includes('nav-benchmark-studio'));
    assert.ok(!adminTargets.includes('nav-sprint-confirmation'));

    // Consultant: both benchmark-studio and sprint-confirmation included
    const consultantTargets = consultantNavTour.steps.map((s: any) => s.tour_target);
    assert.ok(consultantTargets.includes('nav-benchmark-studio'));
    assert.ok(consultantTargets.includes('nav-sprint-confirmation'));

    // IQAC Coordinator: sprint-confirmation included, benchmark-studio excluded
    const iqacTargets = iqacNavTour.steps.map((s: any) => s.tour_target);
    assert.ok(!iqacTargets.includes('nav-benchmark-studio'));
    assert.ok(iqacTargets.includes('nav-sprint-confirmation'));

    // Top buttons included in navigation tour
    assert.ok(adminTargets.includes('persistent-tour-btn'));
    assert.ok(adminTargets.includes('workflow-guide-btn'));
  });

  it('renders ProductTourOverlay for menu tour step with progress, Prev, Next, Skip, and Exit', () => {
    const sampleMenuStep: MenuTourStep = {
      id: 'gaps-summary-bar',
      number: 1,
      title: 'Gap Totals & CRI Score Impact',
      purpose: 'View the summary of open vs closed gaps and total score penalties applied to your sprint.',
      tour_target: 'gaps-summary-bar',
      tour_location: 'AI Readiness Audit > Gap Dashboard',
    };

    const html = renderToStaticMarkup(
      React.createElement(tourBundle.mod.ProductTourOverlay, {
        active: true,
        step: sampleMenuStep,
        stepIndex: 0,
        totalSteps: 5,
        onNext: () => {},
        onPrev: () => {},
        onSkip: () => {},
        onExit: () => {},
        onFinish: () => {},
      })
    );

    assert.ok(html.includes('Step 1 of 5'));
    assert.ok(html.includes('Gap Totals &amp; CRI Score Impact'));
    assert.ok(html.includes('View the summary of open vs closed gaps'));
    assert.ok(html.includes('AI Readiness Audit &gt; Gap Dashboard'));
    assert.ok(html.includes('Skip step'));
    assert.ok(html.includes('Skipping advances the tour only. It does not mark the task completed or alter sprint data.'));
    assert.ok(html.includes('Next'));
    assert.ok(html.includes('Exit tour'));
  });

  it('renders Finish button on final step of a menu tour instead of Next', () => {
    const lastMenuStep: MenuTourStep = {
      id: 'gaps-proceed-btn',
      number: 5,
      title: 'Proceed to Next Audit Stage',
      purpose: 'Move forward to the next stage in your readiness assessment once critical gaps are addressed.',
      tour_target: 'gaps-proceed-btn',
      tour_location: 'AI Readiness Audit > Gap Dashboard',
    };

    const html = renderToStaticMarkup(
      React.createElement(tourBundle.mod.ProductTourOverlay, {
        active: true,
        step: lastMenuStep,
        stepIndex: 4,
        totalSteps: 5,
        onNext: () => {},
        onPrev: () => {},
        onSkip: () => {},
        onExit: () => {},
        onFinish: () => {},
      })
    );

    assert.ok(html.includes('Step 5 of 5'));
    assert.ok(html.includes('Finish'));
  });

  it('disables Previous button on the first tour step', () => {
    const firstStep: MenuTourStep = {
      id: 'step-1',
      number: 1,
      title: 'First Step',
      purpose: 'Test first step',
      tour_target: 'test-target',
      tour_location: 'Test Location',
    };

    const html = renderToStaticMarkup(
      React.createElement(tourBundle.mod.ProductTourOverlay, {
        active: true,
        step: firstStep,
        stepIndex: 0,
        totalSteps: 3,
        onNext: () => {},
        onPrev: () => {},
        onSkip: () => {},
        onExit: () => {},
      })
    );

    assert.ok(html.includes('disabled=""') || html.includes('disabled'));
  });
});
