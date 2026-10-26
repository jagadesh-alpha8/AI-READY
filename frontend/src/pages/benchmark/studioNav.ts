import { useSearchParams } from 'react-router-dom';

/**
 * Moving between Benchmark Studio sections with what to show there, kept in the URL so every jump can be
 * reversed with Back and survives a refresh:
 *   ?tab=explorer&code=AIQIF-C1.1      an indicator in Benchmark Library (opened)
 *   ?tab=sources&source=UGC-005        one source in the Source Library
 */
export type StudioTarget =
  | { tab: 'explorer'; code: string }
  | { tab: 'sources'; source: string };

export function studioHref(t: StudioTarget): string {
  const p = new URLSearchParams({ tab: t.tab });
  if (t.tab === 'explorer') p.set('code', t.code);
  if (t.tab === 'sources') p.set('source', t.source);
  return `/benchmark-studio?${p.toString()}`;
}

/** One URL parameter of the current Studio view, and a way to clear it. */
export function useStudioParam(name: 'code' | 'source') {
  const [params, setParams] = useSearchParams();
  const value = params.get(name) || '';
  const clear = () => setParams((p) => { p.delete(name); return p; }, { replace: true });
  return [value, clear] as const;
}
