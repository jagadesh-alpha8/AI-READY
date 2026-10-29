import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSelectedSprint } from '../context/SelectedSprintContext';
import { dismissGuide, getGuideStatus, resetGuide, skipGuideStep } from '../api/guide';
import type { GuideStatusResponse, GuideStep, GuideStepId } from '../types/guide';

function storageKey(userId?: string, institutionId?: string, sprintId?: string): string {
  return `aios_guide_${userId || 'anon'}_${institutionId || 'none'}_${sprintId || 'none'}`;
}

function readLocalFallback(key: string): Partial<GuideStatusResponse> | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeLocalFallback(key: string, data: GuideStatusResponse) {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // Storage quota or disabled in private mode
  }
}

export function useOnboardingGuide() {
  const { user } = useAuth();
  const { sprintId, status: sprintStatus } = useSelectedSprint();
  const userId = user?.id;
  const institutionId = user?.institution_id || undefined;

  const [data, setData] = useState<GuideStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedStepId, setSelectedStepId] = useState<GuideStepId | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const [tourStepIndex, setTourStepIndex] = useState(0);

  const key = storageKey(userId, institutionId, sprintId);
  const tourIntroKey = `aios_tour_seen_${userId || 'anon'}`;
  const reqSeq = useRef(0);

  const refresh = useCallback(async () => {
    if (!userId) {
      setData(null);
      return;
    }
    const seq = ++reqSeq.current;
    setLoading(true);

    try {
      const res = await getGuideStatus(sprintId || undefined, institutionId || undefined);
      if (seq === reqSeq.current) {
        setData(res.data);
        writeLocalFallback(key, res.data);
      }
    } catch (err) {
      if (seq === reqSeq.current) {
        // Fallback to local cache if network call fails
        const cached = readLocalFallback(key);
        if (cached && cached.steps) {
          setData(cached as GuideStatusResponse);
        }
      }
    } finally {
      if (seq === reqSeq.current) {
        setLoading(false);
      }
    }
  }, [userId, institutionId, sprintId, key]);

  useEffect(() => {
    refresh();
  }, [refresh, sprintId, sprintStatus]);

  // Auto-introduce tour on first visit after login if not already seen or dismissed
  useEffect(() => {
    if (userId && data && data.steps && data.steps.length > 0 && !data.is_dismissed) {
      try {
        const seen = localStorage.getItem(tourIntroKey);
        if (!seen) {
          const initialIdx = data.current_step
            ? Math.max(0, data.steps.findIndex((s) => s.id === data.current_step?.id))
            : 0;
          setTourStepIndex(initialIdx >= 0 ? initialIdx : 0);
          setTourActive(true);
          localStorage.setItem(tourIntroKey, 'true');
        }
      } catch {
        // storage disabled or quota
      }
    }
  }, [userId, data, tourIntroKey]);

  const skip = useCallback(
    async (stepId: GuideStepId, skipped: boolean = true) => {
      try {
        const res = await skipGuideStep(stepId, sprintId || undefined, institutionId || undefined, skipped);
        setData(res.data);
        writeLocalFallback(key, res.data);
        // If we unskipped or skipped, clear any explicit selection override so it follows progression
        setSelectedStepId(null);
      } catch (err) {
        console.error('Failed to update guide skip status', err);
      }
    },
    [sprintId, institutionId, key]
  );

  const toggleDismiss = useCallback(
    async (dismissed: boolean) => {
      try {
        const res = await dismissGuide(dismissed, sprintId || undefined, institutionId || undefined);
        setData(res.data);
        writeLocalFallback(key, res.data);
      } catch (err) {
        // Local update if API call fails
        setData((prev) => (prev ? { ...prev, is_dismissed: dismissed } : prev));
      }
    },
    [sprintId, institutionId, key]
  );

  const reset = useCallback(async () => {
    try {
      const res = await resetGuide(sprintId || undefined, institutionId || undefined);
      setData(res.data);
      writeLocalFallback(key, res.data);
      setSelectedStepId(null);
    } catch (err) {
      console.error('Failed to reset guide', err);
    }
  }, [sprintId, institutionId, key]);

  const steps = data?.steps || [];
  const currentStep = data?.current_step || null;

  // Selected step override if user picked a specific step in the drawer
  const activeStep: GuideStep | null =
    (selectedStepId ? steps.find((s) => s.id === selectedStepId) : null) || currentStep;

  const skipActiveStep = useCallback(async () => {
    if (activeStep) {
      await skip(activeStep.id, true);
    }
  }, [activeStep, skip]);

  const startTour = useCallback(
    (stepIndex?: number) => {
      if (typeof stepIndex === 'number') {
        setTourStepIndex(stepIndex);
      } else {
        const currentIdx = steps.findIndex((s) => s.id === currentStep?.id);
        if (currentIdx >= 0) {
          setTourStepIndex(currentIdx);
        } else {
          const firstIncomplete = steps.findIndex(
            (s) => s.is_authorized && s.status !== 'completed' && s.status !== 'skipped'
          );
          setTourStepIndex(firstIncomplete >= 0 ? firstIncomplete : 0);
        }
      }
      setTourActive(true);
    },
    [steps, currentStep]
  );

  const exitTour = useCallback(() => {
    setTourActive(false);
    if (userId) {
      try {
        localStorage.setItem(tourIntroKey, 'true');
      } catch {}
    }
  }, [userId, tourIntroKey]);

  const nextTourStep = useCallback(() => {
    let nextIdx = -1;
    for (let i = tourStepIndex + 1; i < steps.length; i++) {
      if (steps[i].is_authorized) {
        nextIdx = i;
        break;
      }
    }
    if (nextIdx !== -1) {
      setTourStepIndex(nextIdx);
    } else {
      setTourActive(false);
    }
  }, [tourStepIndex, steps]);

  const prevTourStep = useCallback(() => {
    let prevIdx = -1;
    for (let i = tourStepIndex - 1; i >= 0; i--) {
      if (steps[i].is_authorized) {
        prevIdx = i;
        break;
      }
    }
    if (prevIdx !== -1) {
      setTourStepIndex(prevIdx);
    }
  }, [tourStepIndex, steps]);

  const skipTourStep = useCallback(
    async (stepId: GuideStepId) => {
      await skip(stepId, true);
      nextTourStep();
    },
    [skip, nextTourStep]
  );

  const currentTourStep: GuideStep | null = steps[tourStepIndex] || activeStep || currentStep;

  return {
    data,
    steps,
    currentStep,
    activeStep,
    selectedStepId,
    setSelectedStepId,
    isDismissed: data?.is_dismissed ?? false,
    completedCount: data?.completed_count ?? 0,
    skippedCount: data?.skipped_count ?? 0,
    totalSteps: data?.total_steps ?? 11,
    loading,
    drawerOpen,
    setDrawerOpen,
    tourActive,
    setTourActive,
    tourStepIndex,
    currentTourStep,
    startTour,
    resumeTour: () => startTour(),
    exitTour,
    nextTourStep,
    prevTourStep,
    skipTourStep,
    skipStep: skip,
    skipActiveStep,
    dismissGuide: toggleDismiss,
    resetGuide: reset,
    refresh,
  };
}

