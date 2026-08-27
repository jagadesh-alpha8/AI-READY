import React from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { LogOut, Menu, Moon, Sun } from 'lucide-react';
import ingageLogo from '../assets/ingage-logo-mark.png';

export const Navbar: React.FC<{ onMenuClick?: () => void }> = ({ onMenuClick }) => {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="bg-card border-b border-line-200 px-4 sm:px-6 py-3 flex items-center gap-3 sticky top-0 z-40">
      <button
        type="button"
        onClick={onMenuClick}
        className="lg:hidden btn-icon -ml-1"
        aria-label="Open navigation menu"
      >
        <Menu className="w-5 h-5" />
      </button>

      <div className="flex items-center gap-3 min-w-0">
        <img src={ingageLogo} alt="Ingage" className="h-6 sm:h-7 w-auto shrink-0" />
        <span className="hidden sm:block w-px h-7 bg-line-200 shrink-0" aria-hidden="true" />
        <div className="min-w-0 hidden sm:block">
          <h1 className="text-sm font-bold text-ink-900 tracking-tight leading-tight truncate">
            AI READINESS PLATFORM &middot; MVP
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2 ml-auto">
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
