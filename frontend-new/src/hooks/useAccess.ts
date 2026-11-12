import { useAuth } from '../context/AuthContext';
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
    canSee: (page: PageKey) => canSeePage(role, page),
  };
}
