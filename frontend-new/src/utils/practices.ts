import type { ScreenPractice } from '../types/capability';

/** "1 in place, 4 partly, 1 not found": a topic's six practices in words, never as dots. */
export function countsInWords(practices: Pick<ScreenPractice, 'status'>[]) {
  const n = (s: string) => practices.filter((p) => p.status === s).length;
  return [[n('shown'), 'in place'], [n('partly'), 'partly'], [n('missing'), 'not found']]
    .filter(([c]) => c).map(([c, w]) => `${c} ${w}`).join(', ');
}

