import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Empty } from '../components/ui';
import type { useCapability } from '../hooks/useCapability';
import { pathOf } from '../navigation';

/**
 * A result screen with nothing to show. When a result exists but InGage has not published it yet
 * (capability/publication.py), the college is told it is being prepared, never asked to run the assessment again.
 */
export function NoResult({ cap, children, action }: {
  cap: Pick<ReturnType<typeof useCapability>, 'shown'>; children: ReactNode; action?: ReactNode;
}) {
  if (cap.shown.preparing) {
    return (
      <Empty title="Your result is being prepared">
        InGage checks every result before it is shown to you. It appears here as soon as it is published.
      </Empty>
    );
  }
  return (
    <Empty title="No result yet" action={action ?? <Link className="btn primary" to={pathOf('assessment')}>Go to the assessment</Link>}>
      {children}
    </Empty>
  );
}
