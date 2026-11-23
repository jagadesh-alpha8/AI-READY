import { useAuth } from '../context/AuthContext';
import { DEMO_MODE } from '../config/env';
import { canDo, canSeePage, isStaff, type Action, type PageKey } from '../utils/access';

/** The current user's checks, for pages: `const { can } = useAccess(); can('facts.review')`. */
export function useAccess() {
  const { user } = useAuth();
  const role = user?.role;
  return {
    role,
    user,
    staff: isStaff(role),
    can: (action: Action) => canDo(role, action),
    // The demo build hides the Backend status screen (internal: which screens are live or sample).
    canSee: (page: PageKey) => !(DEMO_MODE && page === 'apistatus') && canSeePage(role, page),
  };
}
