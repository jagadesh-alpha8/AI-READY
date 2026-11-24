/**
 * Readiness levels: stars and a plain name for every score (Siddharth, 23 Nov: replaces Silver / Gold / Platinum /
 * Diamond, which read as commercial). One star per 20 points, so every college has a level, the lowest included.
 * The bands are provisional until calibrated across colleges; the back end uses the same table
 * (apps/scoring/capability/action_plan.py LEVELS). Change both together.
 */
export interface Level { stars: number; name: string; from: number; meaning: string }

export const LEVELS: Level[] = [
  { stars: 1, name: 'Starting out', from: 0, meaning: 'A few AI practices are in place. Most areas have yet to start.' },
  { stars: 2, name: 'Getting there', from: 20, meaning: 'Foundations are in place in some areas. AI is not yet part of everyday teaching and operations.' },
  { stars: 3, name: 'Prepared', from: 40, meaning: 'Foundations are in place in most areas, and AI is in use in several of them.' },
  { stars: 4, name: 'Advanced', from: 60, meaning: 'AI is in regular use across most areas, with results being reviewed.' },
  { stars: 5, name: 'Leading', from: 80, meaning: 'AI is embedded across the institution, with measured results and continuous improvement.' },
];

export function levelFor(score: number | null | undefined): Level & { next: Level | null; pointsToNext: number } {
  const s = Math.max(0, Math.min(100, score ?? 0));
  const index = LEVELS.reduce((found, level, i) => (s >= level.from ? i : found), 0);
  const next = LEVELS[index + 1] ?? null;
  return { ...LEVELS[index], next, pointsToNext: next ? Math.ceil(next.from - s) : 0 };
}

/** "★★☆☆☆" for screen readers and plain text; the Stars component draws them. */
export const starText = (stars: number) => '★'.repeat(stars) + '☆'.repeat(5 - stars);

/** Scores as people read them: whole numbers. */
export const whole = (n: number | null | undefined) => (n == null || !Number.isFinite(n) ? '—' : String(Math.round(n)));
