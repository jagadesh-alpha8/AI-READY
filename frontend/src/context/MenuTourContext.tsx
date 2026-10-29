import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { useSelectedSprint } from './SelectedSprintContext';
import { getGuideStatus, updateMenuTour } from '../api/guide';
import { getMenuTour, MENU_TOURS } from '../components/tour/menuTours';
import type { MenuTourConfig, MenuTourStep, MenuTourStatus } from '../types/guide';
import type { MenuKey } from '../utils/access';
import { canSeeMenu } from '../utils/access';

export interface MenuTourContextValue {
  currentMenuKey: MenuKey | null;
  setCurrentMenuKey: (key: MenuKey | null) => void;
  tourActive: boolean;
  currentTour: MenuTourConfig | null;
  currentStepIndex: number;
  currentStep: MenuTourStep | null;
  totalSteps: number;
  tourMode: 'page' | 'navigation';
  startTour: (menuKey?: MenuKey | null) => void;
  startNavTour: () => void;
  nextStep: () => void;
  prevStep: () => void;
  skipStep: () => void;
  finishTour: () => Promise<void>;
  exitTour: () => void;
  dismissOffer: (menuKey?: MenuKey | null) => Promise<void>;
  isOfferVisible: (menuKey?: MenuKey | null) => boolean;
  isTourAvailable: (menuKey?: MenuKey | null) => boolean;
  menuTourStatus: (menuKey?: MenuKey | null) => MenuTourStatus | null;
}

export const MenuTourContext = createContext<MenuTourContextValue | null>(null);

function storageKey(userId?: string, institutionId?: string, sprintId?: string): string {
  return `aios_menu_tours_${userId || 'anon'}_${institutionId || 'none'}_${sprintId || 'none'}`;
}

function readLocalTourState(key: string): Record<string, { status: MenuTourStatus; updated_at?: string }> {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeLocalTourState(key: string, data: Record<string, { status: MenuTourStatus; updated_at?: string }>) {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // quota or private mode
  }
}

export const MenuTourProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const { sprintId } = useSelectedSprint();
  const userId = user?.id;
  const institutionId = user?.institution_id || undefined;

  const [currentMenuKey, setCurrentMenuKey] = useState<MenuKey | null>(null);
  const [tourActive, setTourActive] = useState(false);
  const [activeMenuKey, setActiveMenuKey] = useState<MenuKey | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [tourMode, setTourMode] = useState<'page' | 'navigation'>('page');

  // Tour status records map from backend and local cache
  const [tourRecords, setTourRecords] = useState<Record<string, { status: MenuTourStatus; updated_at?: string }>>({});
  const localKey = storageKey(userId, institutionId, sprintId);

  // Sync initial guide state on mount / sprint switch
  useEffect(() => {
    if (!userId) {
      setTourRecords({});
      return;
    }

    const localCached = readLocalTourState(localKey);
    setTourRecords(localCached);

    getGuideStatus(sprintId || undefined, institutionId || undefined)
      .then((res) => {
        if (res.data?.menu_tours) {
          const merged = { ...localCached, ...res.data.menu_tours };
          setTourRecords(merged);
          writeLocalTourState(localKey, merged);
        }
      })
      .catch(() => {
        // use local storage fallback
      });
  }, [userId, institutionId, sprintId, localKey]);

  // Determine active tour config
  const currentTour = useMemo(() => {
    if (!activeMenuKey) return null;
    return getMenuTour(activeMenuKey, user?.role);
  }, [activeMenuKey, user?.role]);

  const currentStep = useMemo(() => {
    if (!currentTour || !currentTour.steps.length) return null;
    return currentTour.steps[currentStepIndex] || currentTour.steps[0];
  }, [currentTour, currentStepIndex]);

  const totalSteps = currentTour?.steps.length || 0;

  const isTourAvailable = useCallback(
    (key?: MenuKey | null) => {
      const targetKey = key || currentMenuKey;
      if (!targetKey) return false;
      return canSeeMenu(user?.role, targetKey) && !!getMenuTour(targetKey, user?.role);
    },
    [currentMenuKey, user?.role]
  );

  const menuTourStatus = useCallback(
    (key?: MenuKey | null): MenuTourStatus | null => {
      const targetKey = key || currentMenuKey;
      if (!targetKey) return null;
      return tourRecords[targetKey]?.status || null;
    },
    [currentMenuKey, tourRecords]
  );

  const isOfferVisible = useCallback(
    (key?: MenuKey | null) => {
      const targetKey = key || currentMenuKey;
      if (!targetKey || !userId) return false;
      return isTourAvailable(targetKey);
    },
    [currentMenuKey, userId, isTourAvailable]
  );

  const persistStatus = useCallback(
    async (menuKey: MenuKey, status: MenuTourStatus) => {
      const updated = {
        ...tourRecords,
        [menuKey]: {
          status,
          updated_at: new Date().toISOString(),
        },
      };
      setTourRecords(updated);
      writeLocalTourState(localKey, updated);

      try {
        await updateMenuTour(menuKey, status, sprintId || undefined, institutionId || undefined);
      } catch {
        // Network failure gracefully preserved by local storage fallback
      }
    },
    [tourRecords, localKey, sprintId, institutionId]
  );

  const startTour = useCallback(
    (menuKey?: MenuKey | null) => {
      const targetKey = menuKey || currentMenuKey;
      if (!targetKey) return;
      const tour = getMenuTour(targetKey, user?.role);
      if (!tour || !tour.steps.length) return;

      setTourMode('page');
      setActiveMenuKey(targetKey);
      setCurrentStepIndex(0);
      setTourActive(true);
      persistStatus(targetKey, 'in_progress');
    },
    [currentMenuKey, user?.role, persistStatus]
  );

  const startNavTour = useCallback(() => {
    const navTour = getMenuTour('navigation-tour', user?.role);
    if (!navTour || !navTour.steps.length) return;

    setTourMode('navigation');
    setActiveMenuKey('navigation-tour' as any);
    setCurrentStepIndex(0);
    setTourActive(true);
    persistStatus('navigation-tour' as any, 'in_progress');
  }, [user?.role, persistStatus]);

  const nextStep = useCallback(() => {
    if (!currentTour) return;
    if (currentStepIndex < currentTour.steps.length - 1) {
      setCurrentStepIndex((prev) => prev + 1);
    } else {
      // Completed last step
      if (activeMenuKey) {
        persistStatus(activeMenuKey, 'completed');
      }
      setTourActive(false);
    }
  }, [currentTour, currentStepIndex, activeMenuKey, persistStatus]);

  const prevStep = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    }
  }, [currentStepIndex]);

  const skipStep = useCallback(() => {
    // Skipping advances to the next step without altering any workflow or sprint records
    if (!currentTour) return;
    if (currentStepIndex < currentTour.steps.length - 1) {
      setCurrentStepIndex((prev) => prev + 1);
    } else {
      if (activeMenuKey) {
        persistStatus(activeMenuKey, 'dismissed');
      }
      setTourActive(false);
    }
  }, [currentTour, currentStepIndex, activeMenuKey, persistStatus]);

  const finishTour = useCallback(async () => {
    if (activeMenuKey) {
      await persistStatus(activeMenuKey, 'completed');
    }
    setTourActive(false);
  }, [activeMenuKey, persistStatus]);

  const exitTour = useCallback(() => {
    if (activeMenuKey) {
      // Keep dismissed so auto-prompt doesn't pop up again, while preserving replayability
      const current = tourRecords[activeMenuKey]?.status;
      if (current !== 'completed') {
        persistStatus(activeMenuKey, 'dismissed');
      }
    }
    setTourActive(false);
  }, [activeMenuKey, tourRecords, persistStatus]);

  const dismissOffer = useCallback(
    async (menuKey?: MenuKey | null) => {
      const targetKey = menuKey || currentMenuKey;
      if (!targetKey) return;
      await persistStatus(targetKey, 'dismissed');
    },
    [currentMenuKey, persistStatus]
  );

  const value = useMemo(
    () => ({
      currentMenuKey,
      setCurrentMenuKey,
      tourActive,
      currentTour,
      currentStepIndex,
      currentStep,
      totalSteps,
      tourMode,
      startTour,
      startNavTour,
      nextStep,
      prevStep,
      skipStep,
      finishTour,
      exitTour,
      dismissOffer,
      isOfferVisible,
      isTourAvailable,
      menuTourStatus,
    }),
    [
      currentMenuKey,
      tourActive,
      currentTour,
      currentStepIndex,
      currentStep,
      totalSteps,
      tourMode,
      startTour,
      startNavTour,
      nextStep,
      prevStep,
      skipStep,
      finishTour,
      exitTour,
      dismissOffer,
      isOfferVisible,
      isTourAvailable,
      menuTourStatus,
    ]
  );

  return <MenuTourContext.Provider value={value}>{children}</MenuTourContext.Provider>;
};

const DEFAULT_MENU_TOUR_CONTEXT: MenuTourContextValue = {
  currentMenuKey: null,
  setCurrentMenuKey: () => {},
  tourActive: false,
  currentTour: null,
  currentStepIndex: 0,
  currentStep: null,
  totalSteps: 0,
  tourMode: 'page',
  startTour: () => {},
  startNavTour: () => {},
  nextStep: () => {},
  prevStep: () => {},
  skipStep: () => {},
  finishTour: async () => {},
  exitTour: () => {},
  dismissOffer: async () => {},
  isOfferVisible: () => false,
  isTourAvailable: () => false,
  menuTourStatus: () => null,
};

export function useMenuTour(): MenuTourContextValue {
  const context = useContext(MenuTourContext);
  return context || DEFAULT_MENU_TOUR_CONTEXT;
}
