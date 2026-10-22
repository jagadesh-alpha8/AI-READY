import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import type { SourceDocument, SourceVersion } from '../../api/benchmarks';
import { SourceDetailsAI, SourceVersionPanel } from './SourceVersionPanel';

/**
 * The Source Library as a table: one row per source (its latest version), every
 * register detail in its own column, and **Missing** in any empty cell so staff
 * can see at a glance what still has to be collected.
 *
 * Read-only presentation of the existing list API -- no data or workflow changes.
 * The version's approval state (draft / approved) is its own column, separate from
 * the document's Current Status (the collector's reading, e.g. "Current"). Each row
 * expands to the version panel with the existing actions (fetch & verify, approve,
 * draft requirements, review), its review flags and links. Below the `lg`
 * breakpoint the same rows render as expandable cards.
 */

const COLLECTION_BADGE: Record<string, string> = {
  downloaded: 'badge-success',
  link_only: 'badge-brand',
  licensed_link_only: 'badge-brand',
  to_find: 'badge-neutral',
  blocked: 'badge-warning',
  not_available: 'badge-danger',
};

const APPROVAL: Record<SourceVersion['status'], { label: string; badge: string }> = {
  draft: { label: 'Draft', badge: 'badge-warning' },
  active: { label: 'Approved', badge: 'badge-success' },
  superseded: { label: 'Superseded', badge: 'badge-neutral' },
  withdrawn: { label: 'Withdrawn', badge: 'badge-danger' },
};

const INTAKE_LABEL: Record<SourceVersion['intake_status'], string> = {
  not_run: 'not checked',
  verified: 'verified',
  computed: 'stored',
  mismatch: 'checksum mismatch',
  failed: 'fetch failed',
  skipped: 'skipped',
};

/** An empty value, never hidden. `expected` = empty on purpose (e.g. a licensed file). */
const Missing: React.FC<{ expected?: string }> = ({ expected }) =>
  expected ? (
    <span className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold bg-line-100 text-ink-500" title={expected}>
      Missing
    </span>
  ) : (
    <span className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold bg-danger-bg text-danger border border-danger-line">
      Missing
    </span>
  );

const Link: React.FC<{ href: string; label: string }> = ({ href, label }) => (
  <a className="text-brand-700 hover:underline inline-flex items-center gap-1" href={href} target="_blank" rel="noreferrer" title={href}>
    {label} <ExternalLink className="w-3 h-3" />
  </a>
);

interface Column {
  key: string;
  label: string;
  /** null/'' = Missing. */
  value: (d: SourceDocument, v: SourceVersion | null) => React.ReactNode;
  /** Why an empty value is expected for this row (shown muted instead of red). */
  expected?: (d: SourceDocument, v: SourceVersion | null) => string | undefined;
  width?: string;
}

const licensed = (d: SourceDocument) => (d.licensed_content ? 'Licensed standard: kept as a link only, the file is never stored.' : undefined);
const text = (s: string | null | undefined) => (s && s.trim() ? s : null);

const COLUMNS: Column[] = [
  { key: 'title', label: 'Title', width: 'min-w-[240px]', value: (d) => text(d.title) },
  { key: 'authority', label: 'Authority', value: (d) => (d.authority ? <span title={d.authority_name}>{d.authority}</span> : null) },
  { key: 'category', label: 'Category', width: 'min-w-[140px]', value: (d) => text(d.category) },
  { key: 'role', label: 'Source Role', width: 'min-w-[130px]', value: (d) => text(d.source_role_label) },
  { key: 'type', label: 'Document Type', value: (d) => text(d.document_type) },
  { key: 'applies', label: 'Applies To', width: 'min-w-[160px]', value: (d) => text(d.applies_to) },
  { key: 'version', label: 'Version', value: (_d, v) => (v && v.version_label !== 'unversioned' ? v.version_label : null) },
  { key: 'issued', label: 'Issued Date', value: (_d, v) => v?.issued_on || null },
  { key: 'current', label: 'Current Status', value: (_d, v) => text(v?.reported_status) },
  {
    key: 'collection', label: 'Collection Status',
    value: (_d, v) => (v ? <span className={`badge ${COLLECTION_BADGE[v.collection_status] || 'badge-neutral'}`}>{v.collection_status_label}</span> : null),
  },
  { key: 'official', label: 'Official Page URL', value: (d) => (d.official_url ? <Link href={d.official_url} label="Official page" /> : null) },
  { key: 'direct', label: 'Direct Document URL', value: (_d, v) => (v?.direct_url ? <Link href={v.direct_url} label="Document" /> : null) },
  {
    key: 'file', label: 'Stored File', expected: licensed,
    value: (_d, v) => (v?.file_uri ? <span title={v.intake_note}>Stored · {INTAKE_LABEL[v.intake_status]}</span> : null),
  },
  { key: 'size', label: 'File Size', expected: licensed, value: (_d, v) => (v?.file_size_kb != null ? `${v.file_size_kb} KB` : null) },
  { key: 'pages', label: 'Pages', expected: licensed, value: (_d, v) => (v?.pages != null ? v.pages : null) },
  {
    key: 'sha', label: 'SHA-256', expected: licensed,
    value: (_d, v) => (v?.checksum_sha256 ? <span className="font-mono" title={v.checksum_sha256}>{v.checksum_sha256.slice(0, 12)}…</span> : null),
  },
  {
    key: 'reqs', label: 'Requirements to Review',
    value: (_d, v) => (v ? (v.pending_candidates > 0 ? <span className="badge badge-warning">{v.pending_candidates}</span> : '0') : null),
  },
];

function cell(col: Column, d: SourceDocument, v: SourceVersion | null) {
  const value = col.value(d, v);
  return value === null || value === undefined || value === '' ? <Missing expected={col.expected?.(d, v)} /> : value;
}

/** How many details are missing on this row (expected gaps not counted). */
function missingCount(d: SourceDocument) {
  const v = d.latest_version;
  return COLUMNS.filter((c) => {
    const value = c.value(d, v);
    return (value === null || value === undefined || value === '') && !c.expected?.(d, v);
  }).length;
}

const Approval: React.FC<{ v: SourceVersion | null }> = ({ v }) =>
  v ? <span className={`badge ${APPROVAL[v.status].badge}`} title={v.approved_by ? `Approved by ${v.approved_by}` : 'Not approved yet'}>{APPROVAL[v.status].label}</span>
    : <Missing />;

/** What opens under a row: flags, extra links, and the version's actions. */
const RowDetail: React.FC<{ d: SourceDocument; onChanged: () => void }> = ({ d, onChanged }) => {
  const v = d.latest_version;
  return (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-500">
        <span>Authority: {d.authority_name || '—'}</span>
        <span>{d.version_count} version(s)</span>
        {v?.effective_from && <span>Effective from {v.effective_from}</span>}
        {v?.drive_url && <Link href={v.drive_url} label="Drive copy" />}
        {d.licensed_content && <span>Licensed standard (link only)</span>}
      </div>
      {v && v.review_flags.length > 0 && (
        <ul className="rounded-lg bg-warning-bg border border-warning-line p-3 space-y-1 text-ink-700 list-disc pl-6">
          {v.review_flags.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
      <SourceDetailsAI sourceCode={d.source_code} hasText={!!(d.official_url || v?.file_uri)} onChanged={onChanged} />
      {v ? <SourceVersionPanel version={v} onChanged={onChanged} /> : <p className="text-ink-500">No version recorded yet.</p>}
    </div>
  );
};

export const SourcesTable: React.FC<{ docs: SourceDocument[]; onChanged: () => void }> = ({ docs, onChanged }) => {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <>
      {/* Wide screens: the table. The code column stays visible while scrolling sideways. */}
      <div className="hidden lg:block glass-card overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead className="bg-surface text-ink-500">
            <tr>
              <th className="sticky left-0 z-10 bg-surface px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200">Source Code</th>
              <th className="px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200">Approval</th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => {
              const v = d.latest_version;
              const isOpen = open.has(d.id);
              const gaps = missingCount(d);
              return (
                <React.Fragment key={d.id}>
                  <tr className="align-top border-b border-line-100 hover:bg-surface/60">
                    <td className="sticky left-0 z-10 bg-card px-3 py-2 whitespace-nowrap">
                      <button className="inline-flex items-center gap-1 font-mono font-semibold text-ink-900" onClick={() => toggle(d.id)}
                        aria-expanded={isOpen} title="Show version details and actions">
                        {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        {d.source_code}
                      </button>
                      {gaps > 0 && <div className="mt-1 text-[10px] font-semibold text-danger">{gaps} missing</div>}
                    </td>
                    <td className="px-3 py-2"><Approval v={v} /></td>
                    {COLUMNS.map((c) => (
                      <td key={c.key} className={`px-3 py-2 text-ink-700 ${c.width || 'whitespace-nowrap'}`}>{cell(c, d, v)}</td>
                    ))}
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-line-200 bg-surface/40">
                      <td colSpan={COLUMNS.length + 2} className="px-4 py-3"><RowDetail d={d} onChanged={onChanged} /></td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Smaller screens: one expandable card per row, every field listed (Missing included). */}
      <div className="lg:hidden space-y-2">
        {docs.map((d) => {
          const v = d.latest_version;
          const isOpen = open.has(d.id);
          const gaps = missingCount(d);
          return (
            <div key={d.id} className="glass-card p-3 text-xs space-y-2">
              <button className="w-full text-left flex items-start gap-2" onClick={() => toggle(d.id)} aria-expanded={isOpen}>
                {isOpen ? <ChevronDown className="w-4 h-4 shrink-0 mt-0.5" /> : <ChevronRight className="w-4 h-4 shrink-0 mt-0.5" />}
                <span className="min-w-0 flex-1">
                  <span className="font-mono font-semibold text-ink-900">{d.source_code}</span>
                  <span className="block text-ink-700 truncate">{d.title || 'Untitled'}</span>
                </span>
                <span className="flex flex-col items-end gap-1 shrink-0">
                  <Approval v={v} />
                  {gaps > 0 && <span className="text-[10px] font-semibold text-danger">{gaps} missing</span>}
                </span>
              </button>
              {isOpen && (
                <div className="space-y-3 pt-1 border-t border-line-100">
                  <dl className="grid grid-cols-[minmax(0,40%)_1fr] gap-x-3 gap-y-1.5 pt-2">
                    {COLUMNS.map((c) => (
                      <React.Fragment key={c.key}>
                        <dt className="text-ink-500">{c.label}</dt>
                        <dd className="text-ink-700 min-w-0 break-words">{cell(c, d, v)}</dd>
                      </React.Fragment>
                    ))}
                  </dl>
                  <RowDetail d={d} onChanged={onChanged} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
};
