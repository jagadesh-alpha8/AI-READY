import type { Cycle } from '../types/api';
import { date } from '../utils/format';

/** Choose which benchmark assessment cycle (frozen release + profile snapshot) a screen shows. */
export function CyclePicker({ cycles, value, onChange }: { cycles: Cycle[]; value: string; onChange: (id: string) => void }) {
  if (cycles.length <= 1) return null;
  return (
    <label className="field inline">
      <span>Assessment cycle</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {cycles.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.release_label} · {date(c.created_at)}</option>)}
      </select>
    </label>
  );
}
