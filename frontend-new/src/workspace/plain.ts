/**
 * Plain presentation rules shared by the screens, matching the back end's capability/presentation.py so the screens
 * and the leadership report say the same thing: which quotation shows a strength best, explanation text without
 * criterion-file codes or a document named twice, and the first steps in each area.
 */
import type { ConditionRecord, Result } from '../types/capability';
import { areaTitle } from '../utils/areaTitles';
import { pillarName } from '../utils/capability';

const STAGE: Record<string, number> = { F: 0, A: 1, O: 2 };
export const stageOf = (conditionId: string) => STAGE[conditionId.split('.').pop()?.[0] || 'F'] ?? 3;
const STAGE_STEP = ['Set up', 'Put in use', 'Measure the results'];

/** A suggested lead for an area's actions when no foundation goal names one (a suggestion, never an assignment). */
export const DEFAULT_LEADS: Record<string, string> = {
  'AIQIF-C1': 'Leadership team and IQAC', 'AIQIF-C2': 'Data protection and IT leads',
  'AIQIF-C3': 'Programme and curriculum leads', 'AIQIF-C4': 'Academic development lead',
  'AIQIF-C5': 'Student learning and placement leads', 'AIQIF-C6': 'IT and data leads',
  'AIQIF-C7': 'Research and innovation lead', 'AIQIF-C8': 'Service owners and partnerships lead',
  'AIQIF-C9': 'IQAC coordinator',
};

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

export interface FirstStep {
  code: string; title: string; areaCode: string; area: string; points: number; step: string;
  show: string[]; lead: string;
}

/**
 * What to do next: for each key indicator, the practices at its first unfinished stage (at most two) and the overall
 * points they add when shown in full; the areas with the most to gain and the focus areas get their best step first,
 * then the largest gains, at most two per area and `limit` in all.
 */
export function chooseActions(result: Result, records: Map<string, ConditionRecord>, leads: Record<string, string>,
  priorityAreas: string[], limit = 6, perArea = 2): FirstStep[] {
  const total = result.indicators.reduce((n, i) => n + (i.weight_units || 0), 0);
  const credit = (id: string) => { const r = records.get(id); return r?.credit ?? (r?.state === 'met' ? 1 : 0); };
  const candidates: FirstStep[] = [];
  for (const ind of result.indicators) {
    const open = ind.conditions.map((c) => ({ c, cr: credit(c.id) })).filter((x) => x.cr < 1);
    if (!open.length) continue;
    const first = Math.min(...open.map((x) => stageOf(x.c.id)));
    const chosen = open.filter((x) => stageOf(x.c.id) === first).sort((a, b) => a.cr - b.cr).slice(0, 2);
    const weight = total ? (ind.weight_units || 0) / total : 1 / result.indicators.length;
    const areaCode = ind.pillar || ind.code.split('.')[0];
    candidates.push({
      code: ind.code, title: areaTitle(ind.code, ind.name), areaCode, area: pillarName(areaCode),
      points: chosen.reduce((n, x) => n + ((1 - x.cr) / ind.conditions.length) * 100 * weight, 0),
      step: STAGE_STEP[first] || 'Show',
      show: chosen.map((x) => `${x.c.text}${x.cr > 0 ? ' (partly shown)' : ''}`),
      lead: chosen.map((x) => leads[x.c.id]).find(Boolean) || DEFAULT_LEADS[areaCode] || '',
    });
  }
  candidates.sort((a, b) => b.points - a.points);
  const picked: FirstStep[] = [];
  const count = new Map<string, number>();
  const take = (a: FirstStep) => { picked.push(a); count.set(a.areaCode, (count.get(a.areaCode) || 0) + 1); };
  for (const code of Array.from(new Set(priorityAreas))) {
    const best = candidates.find((a) => a.areaCode === code && !picked.includes(a));
    if (best && picked.length < limit) take(best);
  }
  for (const a of candidates) {
    if (picked.length >= limit) break;
    if (!picked.includes(a) && (count.get(a.areaCode) || 0) < perArea) take(a);
  }
  return picked.sort((a, b) => b.points - a.points);
}

/** Every first step, for the Recommended actions screen: one per key indicator with something unfinished. */
export function allActions(result: Result, records: Map<string, ConditionRecord>, leads: Record<string, string>) {
  return chooseActions(result, records, leads, [], 1000, 1000);
}
