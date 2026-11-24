import { ICONS } from '../components/icons';

/** One of the design preview's icons (lucide). */
export function Icon({ name, size }: { name: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" style={size ? { width: size, height: size } : undefined}
      dangerouslySetInnerHTML={{ __html: ICONS[name] || ICONS.grid }} />
  );
}

/** Stars for a readiness level, filled and empty, with the name read out. */
export function Stars({ stars, size = 18, label }: { stars: number; size?: number; label?: string }) {
  return (
    <span className="ws-stars" role="img" aria-label={label || `${stars} of 5 stars`} style={{ fontSize: size }}>
      {[1, 2, 3, 4, 5].map((i) => <span key={i} className={i <= stars ? 'on' : ''} aria-hidden="true">★</span>)}
    </span>
  );
}
