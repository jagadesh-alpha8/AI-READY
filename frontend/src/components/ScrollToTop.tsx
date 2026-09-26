import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Sends the window back to the top whenever the route changes.
 *
 * Without this, a browser preserves the scroll offset across a client-side
 * navigation: scroll halfway down a long screen — the gap dashboard, say —
 * pick another module from the sidebar, and the new page opens halfway down,
 * mid-sentence. The sidebar is its own scroll container, so it keeps its
 * position, which is what you want; only the page content resets.
 *
 * Keyed on `pathname` alone, deliberately. A change to the query string or
 * hash is a move *within* the same screen (an in-page anchor, a filter), and
 * yanking the reader to the top for one of those would be its own bug.
 */
export const ScrollToTop: React.FC = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    // 'auto', not 'smooth': a new page should already be at the top when it
    // paints, not glide there after the reader has started looking.
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [pathname]);

  return null;
};
