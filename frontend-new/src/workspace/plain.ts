/**
 * Plain presentation rules shared by the screens, matching the back end's capability/presentation.py so the screens
 * and the leadership report say the same thing: which quotation shows a strength best, explanation text without
 * criterion-file codes or a document named twice. The first steps and the checklist are not worked out here: the
 * server sends them finished (run.next_steps, capability/next_steps.py), so screens and reports cannot differ.
 */

const STAGE: Record<string, number> = { F: 0, A: 1, O: 2 };
export const stageOf = (conditionId: string) => STAGE[conditionId.split('.').pop()?.[0] || 'F'] ?? 3;

const squash = (t: string) => t.replace(/\s+/g, ' ').trim();

/** A document's name as a reader sees it: no extension, single spaces. */
export const docLabel = (filename: string) => squash(filename.replace(/\.[A-Za-z0-9]{2,4}$/, ''));

function cut(text: string, limit: number) {
  if (text.length <= limit) return text;
  const c = text.slice(0, limit);
  return `${c.slice(0, c.lastIndexOf(' '))}…`;
}

/** The part of a quotation a card shows: whole sentences up to the limit, else cut at a word. */
export function displayQuote(text: string, limit = 190) {
  const t = squash(text || '');
  if (t.length <= limit) return t;
  let out = '';
  for (const sentence of t.split(/(?<=[.!?])\s+/)) {
    if (out.length + sentence.length + 1 > limit) break;
    out = `${out} ${sentence}`.trim();
  }
  return out.length >= 40 ? out : cut(t, limit);
}

const VERB = /\b(is|are|was|were|has|have|had|provides?|conducts?|offers?|organi[sz]ed|established|approved|completed|trained|includes?|uses?|maintains?|supports?|introduced|adopted|enables?|covers?|focus(es|ing)?|participated|delivered|implemented|created|set up)\b/i;
const AI_WORDS = /\b(AI|artificial intelligence|machine learning|deep learning|generative|neural)\b/i;

/** How well a quotation shows a strength: 0 for headings, titles, codes and table rows. */
export function quoteQuality(text: string, credit: number) {
  const t = displayQuote(text);
  const letters = t.replace(/[^A-Za-z]/g, '');
  if (t.length < 40 || !letters || t.startsWith('[') || t.includes('|') || /^(S\.?\s?No|Sl\.?\s?No)/i.test(t)) return 0;
  if ((letters.replace(/[^A-Z]/g, '').length / letters.length) > 0.5 || /^[A-Z0-9]*\d[A-Z0-9]*\s*:/.test(t)) return 0;
  let score = 1 + (credit >= 1 ? 1 : 0);
  if (AI_WORDS.test(t)) score += 1;
  if (VERB.test(t)) score += 1.5;
  if (t.length >= 60 && t.length <= 230) score += 0.5;
  if (!t.endsWith('…')) score += 0.5;
  return score;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Explanation text made easier to read: criterion-file codes become words; a document named again becomes "the same document". */
export function cleanText(text: string | null | undefined, names: string[]) {
  let t = squash(text || '');
  if (!t) return '';
  t = t.replace(/\b[Cc]riteria\s+\d+\s*-\s*(?:[0-9]+(?:\.[0-9]+)*[a-z]?|[a-z])\b/g, 'the NAAC criterion files');
  t = t.replace(/(the NAAC criterion files)(,? (?:and|or) the NAAC criterion files)+/g, '$1');
  for (const name of names) {
    let seen = 0;
    t = t.replace(new RegExp(`(\\b[Tt]he\\s+)?${escape(name)}`, 'g'), (m, the: string | undefined, offset: number) => {
      seen += 1;
      if (seen === 1) return m;
      const start = offset === 0 || ['.', ''].includes(t.slice(Math.max(0, offset - 2), offset).trim());
      return `${(the || '').startsWith('T') || start ? 'The' : 'the'} same document`;
    });
  }
  return t;
}
