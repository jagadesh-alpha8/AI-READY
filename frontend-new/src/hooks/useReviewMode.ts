import { useEffect, useState } from 'react';
import { storage } from '../utils/storage';

const KEY = 'aircampus_review_mode';
const EVENT = 'aircampus:review-mode';

/**
 * Review mode marks every screen with its backend status (live / partly sample / needs a backend decision).
 * Off by default; remembered per browser; every component using the hook switches together.
 */
export function useReviewMode(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => storage.get(KEY) === '1');
  useEffect(() => {
    const sync = () => setOn(storage.get(KEY) === '1');
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);
  const set = (next: boolean) => {
    if (next) storage.set(KEY, '1'); else storage.remove(KEY);
    window.dispatchEvent(new Event(EVENT));
  };
  return [on, set];
}
