import React, { useState } from 'react';

import type { Gap } from '../../types';
import { gapSnippets, snippetPreview } from './gapSnippets.ts';

/**
 * The Source Snippet cell: a short preview of each snippet (the full text on hover, or in place with
 * "Show full"), with its page -- and, for a conflict, Source A and Source B apart with their documents.
 * "—" where nothing was recorded. All text is rendered as React text (escaped), never as markup.
 */
export const GapSnippetCell: React.FC<{ gap: Gap }> = ({ gap }) => {
  const [expanded, setExpanded] = useState(false);
  const entries = gapSnippets(gap);
  if (entries.length === 0) return <span className="text-ink-500">—</span>;

  const anyTruncated = entries.some((e) => e.snippet && snippetPreview(e.snippet).truncated);
  return (
    <div className="space-y-1.5 text-xs">
      {entries.map((e) => {
        const preview = e.snippet ? snippetPreview(e.snippet) : null;
        return (
          <div key={e.label || 'fact'} className="min-w-0">
            {(e.label || e.document) && (
              <p className="not-italic font-semibold text-ink-700 truncate" title={e.document || undefined}>
                {e.label}{e.label && e.document ? ' · ' : ''}{e.document && <span className="font-normal text-ink-500">{e.document}</span>}
              </p>
            )}
            {e.snippet && preview ? (
              <p className={`italic text-ink-600 ${expanded ? 'whitespace-pre-wrap break-words' : ''}`}
                title={preview.truncated && !expanded ? e.snippet : undefined}>
                &ldquo;{expanded ? e.snippet : preview.text}&rdquo;
                {e.page && <span className="not-italic text-ink-500"> (p. {e.page})</span>}
              </p>
            ) : (
              <p className="text-ink-500">—{e.page && <span> (p. {e.page})</span>}</p>
            )}
          </div>
        );
      })}
      {anyTruncated && (
        <button type="button" className="text-[11px] font-semibold text-brand-800 hover:underline"
          aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show less' : 'Show full snippet'}
        </button>
      )}
    </div>
  );
};
