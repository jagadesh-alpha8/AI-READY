import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { PAGE_META, pathOf } from '../navigation';
import type { PageKey } from '../utils/access';
import { errorMessage, statusOf } from '../utils/errors';
import { humanize, tone as toneOf, type Tone } from '../utils/format';

// --- states ---------------------------------------------------------------------------------------------

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Could not load this view' }: { error: unknown; onRetry?: () => void; title?: string }) {
  const forbidden = statusOf(error) === 403;
  return (
    <div className="state state-error" role="alert">
      <strong>{forbidden ? 'Not available for your role' : title}</strong>
      <p>{errorMessage(error)}</p>
      {onRetry && !forbidden && <button className="secondary-button" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** Inline success / info / warning / error message. */
export function Notice({ tone = 'info', children, onClose }: { tone?: 'info' | 'success' | 'warn' | 'error'; children: ReactNode; onClose?: () => void }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div>{children}</div>
      {onClose && <button className="notice-close" aria-label="Dismiss" onClick={onClose}>×</button>}
    </div>
  );
}

/**
 * A dummy section: the screen's layout filled with the handoff prototype's sample content, for a feature the
 * backend has no API for yet (listed in docs/API_MAPPING.md). Always labelled, so sample data is never read as real.
 */
export function Dummy({ title, note, children, code }: { title: string; note: ReactNode; children?: ReactNode; code?: string }) {
  return (
    <section className="dummy" aria-label={`${title} (sample data)`}>
      <div className="dummy-head">
        <span className="status neutral">Sample data</span>
        {code && <span className="status warn" title="See Backend status and the backend API requests PDF">{code} · waiting for backend</span>}
        <div><strong>{title}</strong><p>{note}</p></div>
      </div>
      {children && <div className="dummy-body">{children}</div>}
    </section>
  );
}

/** A small read-only table of sample rows inside a Dummy section. */
export function SampleTable({ columns, rows }: { columns: string[]; rows: ReactNode[][] }) {
  return (
    <Table columns={columns}>
      {rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}
    </Table>
  );
}

// --- layout pieces --------------------------------------------------------------------------------------

/** Pages about moving between maturity tiers show the CURRENT → SILVER → GOLD → PLATINUM line in their heading. */
const MATURITY_PAGES: ReadonlySet<PageKey> = new Set<PageKey>(['cri', 'pathway', 'plan', 'gaps', 'benchmark']);

export function PageHeading({ page, actions, title }: { page: PageKey; actions?: ReactNode; title?: string }) {
  const [eyebrow, defaultTitle, text] = PAGE_META[page];
  return (
    <div className={`page-heading ${MATURITY_PAGES.has(page) ? 'tier-journey' : ''}`}>
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title || defaultTitle}</h1>
        <p>{text}</p>
      </div>
      {actions && <div className="button-row">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <article className="stat-card">
      <label>{label}</label>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
      <span className="mini-line" aria-hidden="true"><i /><i /><i /><i /><i /></span>
    </article>
  );
}

export function Panel({ title, sub, actions, children, className = '' }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>{title && <h2>{title}</h2>}{sub && <p>{sub}</p>}</div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Pill({ status, label, tone }: { status?: string | null; label?: ReactNode; tone?: Tone }) {
  return <span className={`status ${tone || toneOf(status)}`}>{label ?? humanize(status)}</span>;
}

export function Bar({ label, value, max = 100 }: { label: string; value: number | null; max?: number }) {
  const width = value === null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="bar-row">
      <span>{label}</span>
      <div className="bar-track" role="meter" aria-valuenow={value ?? undefined} aria-valuemin={0} aria-valuemax={max} aria-label={label}>
        <div className="bar-fill" style={{ width: `${width}%` }} />
      </div>
      <b>{value === null ? '—' : Math.round(value)}</b>
    </div>
  );
}

export function CheckItem({ done, children, mark }: { done: boolean; children: ReactNode; mark?: string }) {
  return (
    <div className={`check-item ${done ? 'done' : 'todo'}`}>
      <i aria-hidden="true">{mark ?? (done ? '✓' : '')}</i>
      <span>{children}<span className="sr-only">{done ? ' (done)' : ' (not done)'}</span></span>
    </div>
  );
}

/** A table that scrolls inside its own box on narrow screens, never the page. */
export function Table({ columns, children, caption }: { columns: string[]; children: ReactNode; caption?: string }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function PageLink({ to, children, className = 'secondary-button' }: { to: PageKey; children?: ReactNode; className?: string }) {
  return <Link className={className} to={pathOf(to)}>{children ?? PAGE_META[to][1]}</Link>;
}

export function Pager({ page, count, pageSize, onPage }: { page: number; count: number; pageSize: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="Pages">
      <button className="secondary-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <span>Page {page} of {pages} · {count} items</span>
      <button className="secondary-button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
    </nav>
  );
}

// --- action dialog ----------------------------------------------------------------------------------------

export interface DialogField {
  name: string;
  label: string;
  type?: 'text' | 'textarea' | 'file' | 'date' | 'email' | 'number' | 'password' | 'select';
  required?: boolean;
  initial?: string;
  placeholder?: string;
  /** For `select`: the choices, as value / label pairs. */
  options?: { value: string; label: string }[];
}

/**
 * A modal form for one decision (approve / reject / correct / resolve...). It stays open with the error on a
 * failure, and closes on success.
 */
export function ActionDialog({ title, description, fields, confirmLabel, danger, onSubmit, onClose }: {
  title: string;
  description?: ReactNode;
  fields: DialogField[];
  confirmLabel: string;
  danger?: boolean;
  onSubmit: (values: Record<string, string>, files: Record<string, File | null>) => Promise<void>;
  onClose: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ''])));
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(values, files);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog ref={ref} className="action-dialog" onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }} aria-labelledby="dialog-title">
      <form onSubmit={submit}>
        <h2 id="dialog-title">{title}</h2>
        {description && <div className="dialog-description">{description}</div>}
        {fields.map((f) => (
          <label key={f.name} className="field">
            <span>{f.label}{f.required && ' *'}</span>
            {f.type === 'textarea' ? (
              <textarea required={f.required} value={values[f.name]} placeholder={f.placeholder} rows={3}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
            ) : f.type === 'file' ? (
              <input type="file" required={f.required} onChange={(e) => setFiles({ ...files, [f.name]: e.target.files?.[0] ?? null })} />
            ) : f.type === 'select' ? (
              <select required={f.required} value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                {!f.required && <option value="">—</option>}
                {f.required && !values[f.name] && <option value="" disabled>Choose…</option>}
                {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <input type={f.type || 'text'} required={f.required} value={values[f.name]} placeholder={f.placeholder}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
            )}
          </label>
        ))}
        {error !== null && <Notice tone="error">{errorMessage(error)}</Notice>}
        <div className="button-row dialog-actions">
          <button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancel</button>
          <button type="submit" className={danger ? 'danger-action' : 'primary-action'} disabled={busy}>
            {busy ? 'Saving…' : confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}

// --- tabs and generic read-outs ----------------------------------------------------------------------------

/** Pill tabs (same look as the filter pills used across the app). */
export function Tabs<K extends string>({ tabs, value, onChange, label }: {
  tabs: readonly { key: K; label: ReactNode }[]; value: K; onChange: (k: K) => void; label: string;
}) {
  return (
    <div className="filter-pills" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={value === t.key ? 'active' : ''} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function shortValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number' || typeof v === 'string') return String(v);
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x !== 'object' || x === null)) return v.join(', ') || '—';
    return `${v.length} item${v.length === 1 ? '' : 's'}`;
  }
  return <code className="clamp-2">{JSON.stringify(v)}</code>;
}

/** A backend object whose shape is open (`Record<string, unknown>`) as a definition list. */
export function KeyValues({ data, skip = [] }: { data: Record<string, unknown> | null | undefined; skip?: string[] }) {
  if (!data) return null;
  const entries = Object.entries(data).filter(([k]) => !skip.includes(k));
  if (!entries.length) return <p className="muted">Nothing recorded.</p>;
  return (
    <dl className="kv">
      {entries.map(([k, v]) => <Fragment key={k}><dt>{humanize(k)}</dt><dd>{shortValue(v)}</dd></Fragment>)}
    </dl>
  );
}

/** A list of open-shaped rows as a table, with the columns taken from the first rows. */
export function RowsTable({ rows, columns, empty = 'Nothing here yet.' }: { rows: Record<string, unknown>[]; columns?: string[]; empty?: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  const cols = columns || Array.from(new Set(rows.slice(0, 5).flatMap((r) => Object.keys(r)))).filter((c) => c !== 'id').slice(0, 6);
  return (
    <Table columns={cols.map(humanize)}>
      {rows.map((r, i) => <tr key={String(r.id ?? i)}>{cols.map((c) => <td key={c}>{shortValue(r[c])}</td>)}</tr>)}
    </Table>
  );
}
