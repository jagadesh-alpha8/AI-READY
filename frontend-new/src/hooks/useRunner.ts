import { useState } from 'react';
import { errorMessage } from '../utils/errors';

export type Message = { tone: 'success' | 'error' | 'info' | 'warn'; text: string } | null;

/**
 * One page's action state: which action is running, and the last outcome message.
 * `run(key, fn, ok)` shows `ok` (or the returned string) on success and the server's message on failure.
 */
export function useRunner() {
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState<Message>(null);
  const run = async (key: string, fn: () => Promise<unknown>, ok?: string | ((result: unknown) => string)) => {
    setBusy(key);
    setMsg(null);
    try {
      const result = await fn();
      const text = typeof ok === 'function' ? ok(result) : ok;
      if (text) setMsg({ tone: 'success', text });
      return true;
    } catch (e) {
      setMsg({ tone: 'error', text: errorMessage(e) });
      return false;
    } finally {
      setBusy('');
    }
  };
  return { busy, msg, setMsg, run };
}
