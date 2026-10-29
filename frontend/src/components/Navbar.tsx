import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { Compass, LogOut, Menu, Moon, Sparkles, Sun } from 'lucide-react';
import ingageLogo from '../assets/ingage-logo-mark.png';
import ingageLogoDark from '../assets/ingage-logo-mark-dark.png';

export const Navbar: React.FC<{
  onMenuClick?: () => void;
  onGuideClick?: () => void;
  onTourClick?: () => void;
  guideCompletedCount?: number;
  guideTotalSteps?: number;
  guideLoading?: boolean;
}> = ({ onMenuClick, onGuideClick, onTourClick, guideCompletedCount, guideTotalSteps, guideLoading }) => {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [showTourAttention, setShowTourAttention] = useState(false);
  const location = useLocation();

  // Draw attention to the learning controls whenever the user lands on a page.
  useEffect(() => {
    if (!user?.id) {
      setShowTourAttention(false);
      return;
    }

    setShowTourAttention(true);
    const timeoutId = window.setTimeout(() => setShowTourAttention(false), 5600);
    return () => window.clearTimeout(timeoutId);
  }, [user?.id, location.pathname]);

  return (
    <header className="bg-card border-b border-line-200 px-4 sm:px-6 py-3 flex items-center gap-3 shrink-0 relative z-40">
      <button
        type="button"
        onClick={onMenuClick}
        className="lg:hidden btn-icon -ml-1"
        aria-label="Open navigation menu"
      >
        <Menu className="w-5 h-5" />
      </button>

      <div className="flex items-center gap-3 min-w-0">
        {/* Two files rather than one recoloured with a CSS filter: the wordmark
            is two brand colours, and no filter can lighten the near-black "in"
            without also shifting the green. Swapped in CSS rather than from
            ThemeContext so it follows index.html's pre-React theme script and
            cannot flash the wrong logo on first paint. */}
        <img src={ingageLogo} alt="Ingage" className="h-6 sm:h-7 w-auto shrink-0 dark:hidden" />
        <img
          src={ingageLogoDark}
          alt=""
          aria-hidden="true"
          className="h-6 sm:h-7 w-auto shrink-0 hidden dark:block"
        />
        <span className="hidden sm:block w-px h-7 bg-line-200 shrink-0" aria-hidden="true" />
        <div className="min-w-0 hidden sm:block">
          <h1 className="text-sm font-bold text-ink-900 tracking-tight leading-tight truncate">
            AI READINESS PLATFORM &middot; MVP
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2 ml-auto">
        {onTourClick && user && (
          <button
            type="button"
            key={`product-tour:${user.id}:${location.pathname}`}
            onClick={onTourClick}
            data-tour="persistent-tour-btn"
            className={`btn-secondary text-xs flex items-center gap-1.5 px-2.5 py-1.5 ${showTourAttention ? 'tour-ring-run' : ''}`}
            title="Start Product Tour of platform navigation"
            aria-label="Start Product Tour of platform navigation"
          >
            <Sparkles className="w-4 h-4 text-brand-600 dark:text-brand-400" />
            <span className="hidden sm:inline font-semibold">Product Tour</span>
          </button>
        )}

        {onGuideClick && user && (
          <button
            type="button"
            key={`workflow-guide:${user.id}:${location.pathname}`}
            onClick={onGuideClick}
            data-tour="workflow-guide-btn"
            className={`btn-secondary text-xs flex items-center gap-1.5 px-2.5 py-1.5 ${showTourAttention ? 'tour-ring-run tour-ring-run-delay' : ''}`}
            title="Open Onboarding Workflow Guide"
            aria-label="Open Onboarding Workflow Guide"
          >
            <Compass className="w-4 h-4 text-brand-600 dark:text-brand-400" />
            <span className="hidden sm:inline font-semibold">Workflow Guide</span>
            {guideTotalSteps && !guideLoading ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-line-200 text-ink-500 font-mono">
                {guideCompletedCount ?? 0}/{guideTotalSteps}
              </span>
            ) : null}
          </button>
        )}

        <button
          type="button"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="btn-icon"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        {user && (
          <div className="flex items-center gap-3 bg-surface pl-3 pr-1.5 py-1.5 rounded-lg border border-line-200">
            <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center text-xs font-bold text-on-brand shrink-0">
              {user.name.charAt(0)}
            </div>
            <div className="text-left text-xs hidden sm:block">
              <p className="font-semibold text-ink-900 leading-tight">{user.name}</p>
              <span className="inline-block px-1.5 py-0.5 text-[10px] font-bold rounded bg-accent-bg text-accent border border-accent-line leading-none">
                {user.role}
              </span>
            </div>
            <button
              onClick={logout}
              title="Logout"
              aria-label="Logout"
              className="btn-icon hover:text-danger hover:bg-danger-bg"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
