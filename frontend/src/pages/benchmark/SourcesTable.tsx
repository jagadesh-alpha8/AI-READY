import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { SourceDocument, SourceVersion } from '../../api/benchmarks';

/**
 * The Source Library as a read-only table: one row per source (its latest version) with only the register
 * details staff need -- code, title, authority, category, role, document type, applies to and the three links.
 * An empty cell shows **Missing**. Below the `lg` breakpoint the same fields render as cards.
 */

const Missing: React.FC = () => (
  <span className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold bg-line-100 text-ink-500">Missing</span>
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
  width?: string;
}

const text = (s: string | null | undefined) => (s && s.trim() ? s : null);

const COLUMNS: Column[] = [
  { key: 'title', label: 'Title', width: 'min-w-[240px]', value: (d) => text(d.title) },
  { key: 'authority', label: 'Authority', value: (d) => (d.authority ? <span title={d.authority_name}>{d.authority}</span> : null) },
  { key: 'category', label: 'Category', width: 'min-w-[140px]', value: (d) => text(d.category) },
  { key: 'role', label: 'Source Role', width: 'min-w-[130px]', value: (d) => text(d.source_role_label) },
  { key: 'type', label: 'Document Type', value: (d) => text(d.document_type) },
  { key: 'applies', label: 'Applies To', width: 'min-w-[160px]', value: (d) => text(d.applies_to) },
  { key: 'official', label: 'Official URL', value: (d) => (d.official_url ? <Link href={d.official_url} label="Official page" /> : null) },
  { key: 'direct', label: 'Direct URL', value: (_d, v) => (v?.direct_url ? <Link href={v.direct_url} label="Document" /> : null) },
  { key: 'drive', label: 'Drive Link', value: (_d, v) => (v?.drive_url ? <Link href={v.drive_url} label="Drive" /> : null) },
];

function cell(col: Column, d: SourceDocument, v: SourceVersion | null) {
  const value = col.value(d, v);
  return value === null || value === undefined || value === '' ? <Missing /> : value;
}

export const SourcesTable: React.FC<{ docs: SourceDocument[] }> = ({ docs }) => (
  <>
    {/* Wide screens: the table, scrolling inside its own box so the header row stays visible going down and
        the code column stays visible going sideways. */}
    <div className="hidden lg:block glass-card overflow-auto max-h-[75vh]">
      <table className="w-full text-xs text-left border-collapse">
        <thead className="text-ink-500">
          <tr>
            <th className="sticky top-0 z-20 bg-surface px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200 text-right">S.No</th>
            <th className="sticky left-0 top-0 z-30 bg-surface px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200">Source Code</th>
            {COLUMNS.map((c) => (
              <th key={c.key} className="sticky top-0 z-20 bg-surface px-3 py-2 font-semibold whitespace-nowrap border-b border-line-200">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {docs.map((d, i) => (
            <tr key={d.id} className="align-top border-b border-line-100 hover:bg-surface/60">
              <td className="px-3 py-2 text-right tabular-nums text-ink-500">{i + 1}</td>
              <td className="sticky left-0 z-10 bg-card px-3 py-2 whitespace-nowrap font-mono font-semibold text-ink-900">{d.source_code}</td>
              {COLUMNS.map((c) => (
                <td key={c.key} className={`px-3 py-2 text-ink-700 ${c.width || 'whitespace-nowrap'}`}>{cell(c, d, d.latest_version)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>

    {/* Smaller screens: one card per source with the same fields. */}
    <div className="lg:hidden space-y-2">
      {docs.map((d, i) => (
        <div key={d.id} className="glass-card p-3 text-xs space-y-2">
          <p className="font-mono font-semibold text-ink-900"><span className="text-ink-500 mr-2">{i + 1}.</span>{d.source_code}</p>
          <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
            {COLUMNS.map((c) => (
              <React.Fragment key={c.key}>
                <dt className="text-ink-500 whitespace-nowrap">{c.label}</dt>
                <dd className="text-ink-700 min-w-0 break-words">{cell(c, d, d.latest_version)}</dd>
              </React.Fragment>
            ))}
          </dl>
        </div>
      ))}
    </div>
  </>
);
