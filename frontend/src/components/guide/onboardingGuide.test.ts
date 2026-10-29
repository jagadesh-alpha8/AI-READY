import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../../testing/bundle.ts';
import type { GuideStep } from '../../types/guide';

describe('onboarding guide UI components', async () => {
  const React = (await import('react')).default;
  const { renderToStaticMarkup } = await import('react-dom/server');

  const cardBundle = await bundleComponent(new URL('./OnboardingGuideCard.tsx', import.meta.url), {
    'react-router-dom': `
      export const useNavigate = () => () => {};
    `,
  });

  const drawerBundle = await bundleComponent(new URL('./OnboardingGuideDrawer.tsx', import.meta.url), {
    'react-router-dom': `
      export const useNavigate = () => () => {};
    `,
  });

  const tourBundle = await bundleComponent(new URL('../tour/ProductTourOverlay.tsx', import.meta.url), {});

  after(() => {
    cardBundle.cleanup();
    drawerBundle.cleanup();
    tourBundle.cleanup();
  });

  const sampleStep: GuideStep = {
    id: 'upload_documents',
    number: 3,
    title: 'Upload sprint documents',
    purpose: 'Add institution data packs, policy documents, and reports, or import files from Google Drive.',
    status: 'not_started',
    action_label: 'Upload Documents',
    target_path: '/sprint/spr-123/upload',
    is_authorized: true,
    block_reason: null,
  };

  it('renders OnboardingGuideCard with step number, title, purpose, and action button', () => {
    const html = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: sampleStep,
        totalSteps: 11,
        completedCount: 2,
        skippedCount: 0,
        isDismissed: false,
        onSkip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );

    assert.ok(html.includes('Step 3 of 11'));
    assert.ok(html.includes('Upload sprint documents'));
    assert.ok(html.includes('Add institution data packs'));
    assert.ok(html.includes('Upload Documents'));
    assert.ok(html.includes('Skip this step'));
    assert.ok(html.includes('Not started'));
  });

  it('distinctly displays Needs attention status when extraction has errors or partial pages', () => {
    const attentionStep: GuideStep = {
      ...sampleStep,
      id: 'monitor_processing',
      number: 4,
      title: 'Monitor document processing',
      status: 'needs_attention',
      action_label: 'Retry / Review Issues',
      block_reason: '2 pages could not be read. Please review or retry.',
    };

    const html = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: attentionStep,
        totalSteps: 11,
        completedCount: 2,
        skippedCount: 0,
        isDismissed: false,
        onSkip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );

    assert.ok(html.includes('Needs attention'));
    assert.ok(html.includes('2 pages could not be read'));
    assert.ok(html.includes('Retry / Review Issues'));
  });

  it('shows Resume this step action when step is marked as skipped', () => {
    const skippedStep: GuideStep = {
      ...sampleStep,
      status: 'skipped',
    };

    const html = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: skippedStep,
        totalSteps: 11,
        completedCount: 2,
        skippedCount: 1,
        isDismissed: false,
        onSkip: async () => {},
        onUnskip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );

    assert.ok(html.includes('Skipped'));
    assert.ok(html.includes('Resume this step'));
    assert.ok(!html.includes('Skip this step'));
  });

  it('returns nothing when isDismissed is true', () => {
    const html = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: sampleStep,
        totalSteps: 11,
        completedCount: 2,
        skippedCount: 0,
        isDismissed: true,
        onSkip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );

    assert.equal(html, '');
  });

  it('renders all 11 steps in OnboardingGuideDrawer with progress and controls', () => {
    const all11Steps: GuideStep[] = [
      { id: 'institution_dna', number: 1, title: 'Set up or review Institution DNA', purpose: 'DNA', status: 'completed', action_label: 'Review DNA', target_path: '/institution-dna', is_authorized: true, block_reason: null },
      { id: 'sprint_setup', number: 2, title: 'Create or select a sprint', purpose: 'Sprint', status: 'completed', action_label: 'Manage Sprint', target_path: '/sprint/setup', is_authorized: true, block_reason: null },
      { id: 'upload_documents', number: 3, title: 'Upload sprint documents', purpose: 'Upload', status: 'completed', action_label: 'Upload', target_path: '/sprint/1/upload', is_authorized: true, block_reason: null },
      { id: 'monitor_processing', number: 4, title: 'Monitor document processing', purpose: 'Monitor', status: 'needs_attention', action_label: 'Monitor', target_path: '/sprint/1/monitor', is_authorized: true, block_reason: null },
      { id: 'facts_review', number: 5, title: 'Review extracted facts', purpose: 'Facts', status: 'in_progress', action_label: 'Review Facts', target_path: '/sprint/1/facts', is_authorized: true, block_reason: null },
      { id: 'gaps_evidence', number: 6, title: 'Review gaps & evidence requests', purpose: 'Gaps', status: 'skipped', action_label: 'Review Gaps', target_path: '/sprint/1/gaps', is_authorized: true, block_reason: null },
      { id: 'live_cri', number: 7, title: 'View Live CRI', purpose: 'CRI', status: 'not_started', action_label: 'View CRI', target_path: '/sprint/1/score', is_authorized: true, block_reason: null },
      { id: 'baseline_approval', number: 8, title: 'Complete Baseline Approval', purpose: 'Approval', status: 'not_started', action_label: 'Approval', target_path: '/sprint/1/approval', is_authorized: true, block_reason: null },
      { id: 'recommendations', number: 9, title: 'Review Recommendations', purpose: 'Recs', status: 'not_started', action_label: 'Recs', target_path: '/sprint/1/recommendations', is_authorized: true, block_reason: null },
      { id: 'transformation_plan', number: 10, title: 'Transformation Plan & Goals', purpose: 'Plan', status: 'not_started', action_label: 'Plan', target_path: '/transformation-plan', is_authorized: true, block_reason: null },
      { id: 'reports', number: 11, title: 'Generate and review Report', purpose: 'Reports', status: 'not_started', action_label: 'Report', target_path: '/sprint/1/report', is_authorized: true, block_reason: 'Requires Baseline Approval' },
    ];

    const html = renderToStaticMarkup(
      React.createElement(drawerBundle.mod.OnboardingGuideDrawer, {
        open: true,
        onClose: () => {},
        steps: all11Steps,
        currentStepId: 'monitor_processing',
        completedCount: 3,
        skippedCount: 1,
        totalSteps: 11,
        onSkip: async () => {},
        onUnskip: async () => {},
        onReset: async () => {},
      })
    );

    assert.ok(html.includes('AI Readiness Platform Guide'));
    assert.ok(html.includes('3 of 11 Steps Completed'));
    assert.ok(html.includes('1 Skipped'));
    assert.ok(html.includes('Set up or review Institution DNA'));
    assert.ok(html.includes('Generate and review Report'));
    assert.ok(html.includes('Requires Baseline Approval'));
    assert.ok(html.includes('Current'));
  });

  it('does not render false completion in OnboardingGuideCard when loading or when data is missing', () => {
    // When loading is true
    const loadingHtml = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: null,
        totalSteps: 11,
        completedCount: 0,
        skippedCount: 0,
        isDismissed: false,
        loading: true,
        onSkip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );
    assert.equal(loadingHtml, '');

    // When step is null and total completed is 0 (not finished)
    const incompleteHtml = renderToStaticMarkup(
      React.createElement(cardBundle.mod.OnboardingGuideCard, {
        step: null,
        totalSteps: 11,
        completedCount: 0,
        skippedCount: 0,
        isDismissed: false,
        loading: false,
        onSkip: async () => {},
        onDismiss: () => {},
        onOpenDrawer: () => {},
      })
    );
    assert.equal(incompleteHtml, '');
  });

  it('renders ProductTourOverlay with step progress, location, purpose, and skip disclaimer', () => {
    const liveCriStep: GuideStep = {
      id: 'live_cri',
      number: 7,
      title: 'View Live CRI',
      purpose: 'Inspect real-time College Readiness Index scores evaluated across the nine AI-QIF criteria and confidence levels.',
      status: 'not_started',
      action_label: 'View Live CRI',
      target_path: '/sprint/spr-1/score',
      tour_target: 'nav-sprint-score',
      tour_location: 'AI Readiness Audit > Live CRI Preview',
      is_authorized: true,
      block_reason: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(tourBundle.mod.ProductTourOverlay, {
        active: true,
        step: liveCriStep,
        stepIndex: 6,
        totalSteps: 11,
        onNext: () => {},
        onPrev: () => {},
        onSkip: () => {},
        onExit: () => {},
        onNavigate: () => {},
      })
    );

    assert.ok(html.includes('Step 7 of 11'));
    assert.ok(html.includes('View Live CRI'));
    assert.ok(html.includes('nine AI-QIF criteria'));
    assert.ok(html.includes('AI Readiness Audit &gt; Live CRI Preview'));
    assert.ok(html.includes('Skip step'));
    assert.ok(html.includes('Skipping advances the tour only. It does not mark the task completed or alter sprint data.'));
    assert.ok(html.includes('Exit tour'));
  });

  it('renders accurate provisional baseline approval note in ProductTourOverlay', () => {
    const provisionalApprovalStep: GuideStep = {
      id: 'baseline_approval',
      number: 8,
      title: 'Complete Baseline Approval',
      purpose: 'Formalize and freeze the baseline CRI score with rationale to unlock recommendations and report export.',
      status: 'in_progress',
      action_label: 'View Provisional Baseline',
      target_path: '/sprint/spr-1/approval',
      tour_target: 'nav-sprint-approval',
      tour_location: 'AI Readiness Audit > Baseline Approval',
      is_authorized: true,
      block_reason: null,
      details: {
        is_provisional: true,
        approval_status: 'provisional',
      },
    };

    const html = renderToStaticMarkup(
      React.createElement(tourBundle.mod.ProductTourOverlay, {
        active: true,
        step: provisionalApprovalStep,
        stepIndex: 7,
        totalSteps: 11,
        onNext: () => {},
        onPrev: () => {},
        onSkip: () => {},
        onExit: () => {},
        onNavigate: () => {},
      })
    );

    assert.ok(html.includes('Step 8 of 11'));
    assert.ok(html.includes('Complete Baseline Approval'));
    assert.ok(html.includes('Baseline is currently provisional'));
    assert.ok(html.includes('View Provisional Baseline'));
  });
});

