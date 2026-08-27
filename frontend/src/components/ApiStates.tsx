import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * Shared loading/empty/error building blocks so every page renders these
 * states consistently instead of hand-rolling the same markup.
 */

export const LoadingState: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center py-8 text-sm text-ink-500">{message}</div>
);

export const EmptyState: React.FC<{
  message: string;
  action?: { label: string; onClick: () => void };
}> = ({ message, action }) => (
  <div className="panel-muted">
    <p className="text-sm text-ink-500">{message}</p>
    {action && (
      <button onClick={action.onClick} className="btn-primary btn-sm mt-3">
        {action.label}
      </button>
    )}
  </div>
);

export const ErrorState: React.FC<{ message: string; onRetry?: () => void }> = ({ message, onRetry }) => (
  <div className="text-center py-8 bg-danger-bg rounded-lg border border-danger-line space-y-3">
    <p className="text-sm text-danger flex items-center justify-center gap-1.5 px-4">
      <AlertTriangle className="w-4 h-4 shrink-0" /> {message}
    </p>
    {onRetry && (
      <button onClick={onRetry} className="btn-secondary btn-sm inline-flex items-center gap-1.5">
        <RefreshCw className="w-3.5 h-3.5" /> Try again
      </button>
    )}
  </div>
);

/** Inline (non-blocking) variant for action errors -- e.g. a failed confirm/resolve
 * click where the page's data is already loaded and shouldn't be replaced. */
export const InlineError: React.FC<{ message: string; onDismiss?: () => void }> = ({ message, onDismiss }) => (
  <div className="p-3 bg-danger-bg border border-danger-line rounded-lg text-sm text-danger flex items-center justify-between gap-3">
    <span className="flex items-center gap-1.5">
      <AlertTriangle className="w-4 h-4 shrink-0" /> {message}
    </span>
    {onDismiss && (
      <button onClick={onDismiss} className="text-danger/70 hover:text-danger font-bold px-1 shrink-0" aria-label="Dismiss">
        &times;
      </button>
    )}
  </div>
);
