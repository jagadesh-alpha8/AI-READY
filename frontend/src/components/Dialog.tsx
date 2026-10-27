import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Info, X } from 'lucide-react';

/**
 * In-app replacements for window.confirm / window.prompt / window.alert, styled like the rest of the app.
 * Call them from anywhere (no hook needed) -- they return a promise:
 *
 *   if (!(await confirmDialog('Delete this file?', { danger: true, confirmLabel: 'Delete' }))) return;
 *   const reason = await promptDialog('Why reopen?', { required: true });  // null when cancelled
 *   await alertDialog('Failed to delete the job.');
 *
 * <DialogHost /> is mounted once in App. Where it is not mounted (component tests render pages on their own),
 * the browser's native dialogs are used instead, so behaviour is unchanged there.
 */

type Kind = 'confirm' | 'prompt' | 'alert';

export interface DialogOptions {
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button, for deletes and other irreversible actions. */
  danger?: boolean;
  /** prompt only: initial text, placeholder, and whether an empty answer is refused. */
  defaultValue?: string;
  placeholder?: string;
  required?: boolean;
}

interface Request extends DialogOptions {
  kind: Kind;
  message: string;
  resolve: (value: boolean | string | null) => void;
}

let show: ((request: Request) => void) | null = null;

function open<T>(kind: Kind, message: string, options: DialogOptions, fallback: () => T): Promise<T> {
  if (!show) return Promise.resolve(fallback());
  const target = show;
  return new Promise<T>((resolve) => target({ ...options, kind, message, resolve: resolve as Request['resolve'] }));
}

export const confirmDialog = (message: string, options: DialogOptions = {}): Promise<boolean> =>
  open('confirm', message, options, () => window.confirm(message));

/** The trimmed answer, or null when cancelled. */
export const promptDialog = (message: string, options: DialogOptions = {}): Promise<string | null> =>
  open('prompt', message, options, () => {
    const answer = window.prompt(message, options.defaultValue ?? '');
    return answer === null ? null : answer.trim();
  });

export const alertDialog = (message: string, options: DialogOptions = {}): Promise<void> =>
  open('alert', message, options, () => window.alert(message));

export const DialogHost: React.FC = () => {
  const [queue, setQueue] = useState<Request[]>([]);
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const current = queue[0];

  useEffect(() => {
    show = (request) => setQueue((q) => [...q, request]);
    return () => { show = null; };
  }, []);

  useEffect(() => {
    if (!current) return;
    setText(current.defaultValue ?? '');
    const focus = window.setTimeout(() => (current.kind === 'prompt' ? inputRef.current : confirmRef.current)?.focus());
    return () => window.clearTimeout(focus);
  }, [current]);

  if (!current) return null;

  const close = (value: boolean | string | null) => {
    current.resolve(value);
    setQueue((q) => q.slice(1));
  };
  const answer = text.trim();
  const blocked = current.kind === 'prompt' && current.required && !answer;
  const ok = () => {
    if (blocked) return;
    close(current.kind === 'prompt' ? answer : true);
  };
  const cancel = () => close(current.kind === 'prompt' ? null : current.kind === 'alert' ? true : false);
  const Icon = current.danger ? AlertTriangle : Info;
  const title = current.title
    ?? (current.kind === 'alert' ? 'Notice' : current.kind === 'prompt' ? 'Please explain' : 'Please confirm');

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-ink-900/40 p-4"
      role="dialog" aria-modal="true" aria-labelledby="app-dialog-title"
      onKeyDown={(e) => {
        if (e.key === 'Escape') { e.stopPropagation(); cancel(); }
        if (e.key === 'Enter' && (current.kind !== 'prompt' || !e.shiftKey)) { e.preventDefault(); ok(); }
      }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) cancel(); }}
    >
      <div className="glass-card w-full max-w-md p-5 space-y-4">
        <div className="flex items-start gap-3">
          <span className={`mt-0.5 shrink-0 rounded-full p-1.5 ${current.danger ? 'bg-danger-bg text-danger' : 'bg-brand-100 text-brand-700'}`}>
            <Icon className="w-4 h-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="app-dialog-title" className="text-base font-bold text-ink-900">{title}</h2>
            <p className="text-sm text-ink-600 mt-1 whitespace-pre-line">{current.message}</p>
          </div>
          <button className="btn-icon" onClick={cancel} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        {current.kind === 'prompt' && (
          <div>
            <textarea
              ref={inputRef}
              className="input w-full min-h-[84px]"
              value={text}
              placeholder={current.placeholder ?? (current.required ? 'Required' : 'Optional')}
              onChange={(e) => setText(e.target.value)}
            />
            {blocked && text.length > 0 && <p className="text-xs text-danger mt-1">Please enter a reason.</p>}
          </div>
        )}
        <div className="flex justify-end gap-2">
          {current.kind !== 'alert' && (
            <button className="btn-secondary" onClick={cancel}>{current.cancelLabel ?? 'Cancel'}</button>
          )}
          <button
            ref={confirmRef}
            className={current.danger ? 'btn-danger' : 'btn-primary'}
            onClick={ok}
            disabled={blocked}
          >
            {current.confirmLabel ?? 'OK'}
          </button>
        </div>
      </div>
    </div>
  );
};
