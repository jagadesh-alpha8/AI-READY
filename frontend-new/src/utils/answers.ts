import type { Layer2Question, Layer2Response } from '../services/capability';

/** What came of an answer, in a few words. */
export function answerState(r: Pick<Layer2Response, 'kind' | 'choice' | 'status' | 'supported'>): { label: string; tone: 'ok' | 'wait' | 'none' } {
  if (r.kind === 'dont_know') return { label: 'Skipped', tone: 'none' };
  if (r.choice === 'not_yet') return { label: 'Not yet in place', tone: 'none' };
  if (r.status === 'pending') return { label: 'Being checked against your documents', tone: 'wait' };
  return r.supported ? { label: 'Supported by a document', tone: 'ok' } : { label: 'No supporting document found', tone: 'none' };
}


/** Where answers stop adding much: the question after which the rest hold less than a sixth of the points (the
 * follow-up audit: the first 30 of test 13's questions held 84 percent). -1 when there is no such point. */
export function littleAfter(qs: Pick<Layer2Question, 'points_at_stake'>[]) {
  const total = qs.reduce((t, q) => t + (q.points_at_stake || 0), 0);
  if (!total) return -1;
  let sum = 0;
  for (let i = 0; i < qs.length; i += 1) {
    sum += qs[i].points_at_stake || 0;
    if (sum >= total * 0.85) return i < qs.length - 1 ? i + 1 : -1;
  }
  return -1;
}

