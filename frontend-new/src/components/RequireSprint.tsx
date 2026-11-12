import type { ReactNode } from 'react';
import { useSprint } from '../context/SprintContext';
import type { Sprint } from '../types/api';
import { Empty, ErrorState, Loading, PageLink } from './ui';

/** Renders `children(sprint)` once an audit sprint is selected; otherwise the right loading / error / empty state. */
export function RequireSprint({ children }: { children: (sprint: Sprint) => ReactNode }) {
  const { sprint, loading, error, reload } = useSprint();
  if (loading && !sprint) return <Loading label="Loading audit sprints…" />;
  if (error && !sprint) return <ErrorState error={error} onRetry={() => void reload()} />;
  if (!sprint) {
    return (
      <Empty title="No audit sprint yet" action={<PageLink to="onboarding" className="primary-action">Start onboarding</PageLink>}>
        This screen works on an audit sprint. Create the institution and its first sprint in onboarding.
      </Empty>
    );
  }
  return <>{children(sprint)}</>;
}
