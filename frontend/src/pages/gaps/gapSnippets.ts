/**
 * The Gap Dashboard's Source Snippet column, as pure functions (`npm test` runs them on Node directly).
 * Only what the API recorded is shown: the linked fact's snippet and page, or -- for a conflict -- each
 * side's document, page and snippet (gap.conflict_sides). Nothing is filled in.
 */
import type { Gap } from '../../types/gaps.ts';

export interface SnippetEntry {
  /** 'Source A' / 'Source B' for a conflict; '' for a single fact. */
  label: string;
  /** The side's document (conflicts only -- a single fact's document is already in the Source column). */
  document: string | null;
  page: string | null;
  snippet: string | null;
}

/** Characters shown before the preview is cut (the full text is on hover and on "Show full"). */
export const PREVIEW_CHARS = 90;

const present = (v: string | null | undefined) => (v && v.trim() ? v : null);

/** What the cell lists: two entries for a conflict, one for a gap on a fact, none without a fact. */
export function gapSnippets(gap: Pick<Gap, 'gap_type' | 'source_fact_id' | 'conflict_sides' | 'source_snippet' | 'source_page'>): SnippetEntry[] {
  if (gap.gap_type === 'conflict' && gap.conflict_sides && gap.conflict_sides.length > 0) {
    return gap.conflict_sides.map((side) => ({
      label: `Source ${side.side}`,
      document: present(side.document_name),
      page: present(side.page),
      snippet: present(side.snippet),
    }));
  }
  if (!gap.source_fact_id) return [];
  return [{ label: '', document: null, page: present(gap.source_page), snippet: present(gap.source_snippet) }];
}

/** A short preview, cut at a word boundary where one is near. */
export function snippetPreview(text: string, max = PREVIEW_CHARS): { text: string; truncated: boolean } {
  const flat = text.replace(/\s+/g, ' ').trim();
  if (flat.length <= max) return { text: flat, truncated: false };
  const cut = flat.slice(0, max);
  const space = cut.lastIndexOf(' ');
  return { text: `${(space > max * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`, truncated: true };
}

/** The snippet text a search should match (both sides of a conflict, and their documents). */
export function snippetSearchText(gap: Parameters<typeof gapSnippets>[0]): string[] {
  return gapSnippets(gap).flatMap((e) => [e.snippet, e.document]).filter((v): v is string => !!v);
}
