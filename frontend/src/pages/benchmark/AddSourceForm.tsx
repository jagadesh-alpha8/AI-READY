import React, { useMemo, useState } from 'react';
import { CheckCircle2, Plus, Upload, X } from 'lucide-react';
import { createSource, getSourceReference } from '../../api/benchmarks';
import type { NewSource, SourceDocument, SourceReference } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';

/**
 * Add one source document by hand (InGage staff), instead of a Source Register
 * import row. Same fields and rules as the import -- see
 * backend/apps/benchmarks/services/source_create.py. The source is saved with
 * one DRAFT version; its collection status follows what is given (uploaded
 * file -> Downloaded, licensed -> Licensed link only, URL -> Found link only,
 * nothing -> To find). Approval stays a separate step in the list below.
 */

const NEW_AUTHORITY = '__new__';
const EMPTY: NewSource = {
  authority: '', authority_name: '', authority_kind: '', category: '', source_code: '', title: '',
  source_role: '', document_type: '', applies_to: '', programme_scope: '', official_url: '', direct_url: '',
  licensed_content: false, version_label: '', issued_on: '', effective_from: '', review_cadence_months: '12', notes: '',
};
const URL_RE = /^https?:\/\/[^\s/$.?#].\S*$/i;

type Errors = Partial<Record<keyof NewSource | 'file', string>>;

function checkLocally(f: NewSource, file: File | null, ref: SourceReference): Errors {
  const e: Errors = {};
  if (!f.authority) e.authority = 'Pick the authority that issued this source.';
  if (f.authority === NEW_AUTHORITY) {
    if (f.authority_name.trim().length < 2) e.authority_name = "Enter the new authority's name.";
    if (!f.authority_kind) e.authority_kind = 'Choose what kind of authority it is.';
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{1,39}$/.test(f.source_code.trim())) {
    e.source_code = '2-40 letters, digits, dots, dashes or underscores (e.g. UGC-012).';
  }
  if (f.title.trim().length < 5) e.title = 'Enter the official title (at least 5 characters).';
  if (f.official_url && !URL_RE.test(f.official_url.trim())) e.official_url = 'Start with http:// or https://.';
  if (f.direct_url && !URL_RE.test(f.direct_url.trim())) e.direct_url = 'Start with http:// or https://.';
  const months = Number(f.review_cadence_months);
  if (!Number.isInteger(months) || months < 1 || months > 120) e.review_cadence_months = '1-120 months.';
  if (f.issued_on && f.issued_on > new Date().toISOString().slice(0, 10)) e.issued_on = 'Cannot be in the future.';
  if (file) {
    const ext = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (f.licensed_content) e.file = 'A licensed standard is kept as a link only; remove the file.';
    else if (!ref.file_extensions.includes(ext)) e.file = `Unsupported type ${ext}. Use ${ref.file_extensions.join(', ')}.`;
    else if (file.size > ref.max_file_mb * 1024 * 1024) e.file = `Larger than ${ref.max_file_mb} MB.`;
    else if (file.size === 0) e.file = 'The file is empty.';
  }
  return e;
}

function startingStatus(f: NewSource, file: File | null) {
  if (file) return 'Downloaded (file stored, SHA-256 recorded)';
  if (f.licensed_content) return 'Licensed - link only';
  if (f.official_url || f.direct_url) return 'Found - link only';
  return 'To find';
}

export const AddSourceButton: React.FC<{ onAdded: (doc: SourceDocument) => void }> = ({ onAdded }) => {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<SourceDocument | null>(null);
  return (
    <div className="space-y-3">
      {saved && !open && (
        <div className="rounded-lg border border-success-line bg-success-bg p-3 text-sm text-ink-700 flex items-start gap-2">
          <CheckCircle2 className="w-4 h-4 text-success shrink-0 mt-0.5" />
          <p className="flex-1">
            <strong>{saved.source_code}</strong> added as a draft
            {saved.latest_version ? <> &middot; status: {saved.latest_version.collection_status_label}</> : null}.
            It is in the list below; approve its version there when it has been checked.
          </p>
          <button className="btn-icon" aria-label="Dismiss" onClick={() => setSaved(null)}><X className="w-4 h-4" /></button>
        </div>
      )}
      {open ? (
        <AddSourceForm
          onCancel={() => setOpen(false)}
          onSaved={(doc) => { setOpen(false); setSaved(doc); onAdded(doc); }}
        />
      ) : (
        <button className="btn-primary btn-sm" onClick={() => { setSaved(null); setOpen(true); }}>
          <Plus className="w-4 h-4" /> Add source
        </button>
      )}
    </div>
  );
};

const AddSourceForm: React.FC<{ onCancel: () => void; onSaved: (doc: SourceDocument) => void }> = ({ onCancel, onSaved }) => {
  const ref = useApiResource<SourceReference>(() => getSourceReference(), []);
  const [f, setF] = useState<NewSource>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k: keyof NewSource) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const value = e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value;
    setF((prev) => ({ ...prev, [k]: value }));
    setErrors((prev) => ({ ...prev, [k]: undefined }));
  };
  const status = useMemo(() => startingStatus(f, file), [f, file]);

  if (ref.loading) return <LoadingState message="Loading form…" />;
  if (ref.error || !ref.data) return <ErrorState message={ref.error || 'Could not load the form.'} onRetry={ref.refetch} />;
  const r = ref.data;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    const local = checkLocally(f, file, r);
    setErrors(local);
    if (Object.keys(local).length) { setFormError('Please fix the highlighted fields.'); return; }
    setBusy(true);
    try {
      const payload = { ...f, authority: f.authority === NEW_AUTHORITY ? '' : f.authority,
        source_code: f.source_code.trim(), title: f.title.trim() };
      const { data } = await createSource(payload, f.licensed_content ? null : file);
      onSaved(data);
    } catch (err: any) {
      const body = err?.response?.data;
      if (body?.errors) { setErrors(body.errors); setFormError(body.detail || 'Please fix the highlighted fields.'); }
      else if (err?.response?.status === 403) setFormError('Only InGage staff can add sources.');
      else setFormError(body?.detail || 'Could not save the source. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const field = (k: keyof NewSource | 'file', label: string, input: React.ReactNode, hint?: string) => (
    <label className="block space-y-1 min-w-0">
      <span className="text-xs font-semibold text-ink-700">{label}</span>
      {input}
      {errors[k] ? <span className="block text-xs text-danger">{errors[k]}</span>
        : hint ? <span className="block text-[11px] text-ink-500">{hint}</span> : null}
    </label>
  );
  const cls = (k: keyof NewSource | 'file') => `input w-full text-sm ${errors[k] ? 'input-error' : ''}`;

  return (
    <form onSubmit={submit} className="glass-card p-5 space-y-4" noValidate>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-ink-900">Add a source</h3>
        <button type="button" className="btn-icon" aria-label="Close" onClick={onCancel}><X className="w-4 h-4" /></button>
      </div>
      {formError && <div className="p-3 bg-danger-bg border border-danger-line rounded-lg text-sm text-danger">{formError}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {field('authority', 'Authority *', (
          <select className={cls('authority')} value={f.authority} onChange={set('authority')}>
            <option value="">Choose…</option>
            {r.authorities.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name}</option>)}
            <option value={NEW_AUTHORITY}>+ New authority…</option>
          </select>
        ))}
        {field('category', 'Library category', (
          <>
            <input className={cls('category')} list="source-categories" value={f.category} onChange={set('category')}
              placeholder="e.g. 2. Governance & quality" />
            <datalist id="source-categories">{r.categories.map((c) => <option key={c} value={c} />)}</datalist>
          </>
        ), 'Starts with its number, as in the Source Register.')}
        {f.authority === NEW_AUTHORITY && (
          <>
            {field('authority_name', 'New authority name *', (
              <input className={cls('authority_name')} value={f.authority_name} onChange={set('authority_name')}
                placeholder="e.g. National Board of Accreditation" />
            ))}
            {field('authority_kind', 'Authority kind *', (
              <select className={cls('authority_kind')} value={f.authority_kind} onChange={set('authority_kind')}>
                <option value="">Choose…</option>
                {r.authority_kinds.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
            ))}
          </>
        )}
        {field('source_code', 'Source code *', (
          <input className={cls('source_code')} value={f.source_code} onChange={set('source_code')} placeholder="e.g. UGC-012" />
        ), 'Unique; used everywhere to refer to this source.')}
        {field('source_role', 'Source role', (
          <select className={cls('source_role')} value={f.source_role} onChange={set('source_role')}>
            <option value="">Not set (flagged for review)</option>
            {r.source_roles.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
          </select>
        ))}
      </div>

      {field('title', 'Official title (exact) *', (
        <input className={cls('title')} value={f.title} onChange={set('title')} />
      ))}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {field('official_url', 'Official page URL', (
          <input className={cls('official_url')} value={f.official_url} onChange={set('official_url')} placeholder="https://www.ugc.gov.in/…" />
        ), 'The official page that lists the document.')}
        {field('direct_url', 'Direct document URL', (
          <input className={cls('direct_url')} value={f.direct_url} onChange={set('direct_url')} placeholder="https://…/document.pdf" />
        ))}
        {field('document_type', 'Document type', (
          <>
            <input className={cls('document_type')} list="source-doc-types" value={f.document_type} onChange={set('document_type')}
              placeholder="e.g. Regulation, Guideline" />
            <datalist id="source-doc-types">{r.document_types.map((t) => <option key={t} value={t} />)}</datalist>
          </>
        ))}
        {field('applies_to', 'Applies to', (
          <input className={cls('applies_to')} value={f.applies_to} onChange={set('applies_to')} placeholder="e.g. All UGC-recognised institutions" />
        ))}
        {field('programme_scope', 'Programme / trade scope', (
          <input className={cls('programme_scope')} value={f.programme_scope} onChange={set('programme_scope')} />
        ))}
        {field('review_cadence_months', 'Review cadence (months)', (
          <input type="number" min={1} max={120} className={cls('review_cadence_months')} value={f.review_cadence_months}
            onChange={set('review_cadence_months')} />
        ))}
        {field('version_label', 'Version / edition', (
          <input className={cls('version_label')} value={f.version_label} onChange={set('version_label')} placeholder="e.g. 2025 (blank = unversioned)" />
        ))}
        {field('issued_on', 'Issued on', (
          <input type="date" className={cls('issued_on')} value={f.issued_on} onChange={set('issued_on')} />
        ))}
        {field('effective_from', 'Effective from', (
          <input type="date" className={cls('effective_from')} value={f.effective_from} onChange={set('effective_from')} />
        ))}
      </div>

      <label className="flex items-center gap-2 text-sm text-ink-700">
        <input type="checkbox" checked={f.licensed_content} onChange={set('licensed_content')} />
        Licensed standard (e.g. ISO) — keep as a link only, never store the file
      </label>

      {!f.licensed_content && field('file', `Document file (optional, up to ${r.max_file_mb} MB)`, (
        <div className={`flex items-center gap-2 ${errors.file ? 'text-danger' : ''}`}>
          <label className="btn-secondary btn-sm cursor-pointer">
            <Upload className="w-3.5 h-3.5" /> {file ? 'Change file' : 'Choose file'}
            <input type="file" className="hidden" accept={r.file_extensions.join(',')}
              onChange={(e) => { setFile(e.target.files?.[0] || null); setErrors((p) => ({ ...p, file: undefined })); }} />
          </label>
          {file && (
            <span className="text-xs text-ink-700 truncate">
              {file.name} ({Math.max(1, Math.round(file.size / 1024))} KB)
              <button type="button" className="ml-2 text-danger" onClick={() => setFile(null)}>remove</button>
            </span>
          )}
        </div>
      ), `Supported: ${r.file_extensions.join(', ')}. Stored once with its SHA-256 checksum.`)}

      {field('notes', 'Notes', (
        <textarea className={cls('notes')} rows={2} value={f.notes} onChange={set('notes')} />
      ))}

      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <p className="text-xs text-ink-500">Will be saved as a <strong>draft</strong> version · status: <strong>{status}</strong></p>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary btn-sm" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="submit" className="btn-primary btn-sm" disabled={busy}>{busy ? 'Saving…' : 'Save source'}</button>
        </div>
      </div>
    </form>
  );
};
