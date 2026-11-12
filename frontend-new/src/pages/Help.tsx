import { Link } from 'react-router-dom';
import { PageHeading } from '../components/ui';
import { pathOf } from '../navigation';
import type { PageKey } from '../utils/access';

const TOPICS: [string, string, PageKey][] = [
  ['Onboarding assistance', 'Set up the institution, scope and audit sprint.', 'onboarding'],
  ['Evidence support', 'Upload, extraction, mapping and review questions.', 'uploads'],
  ['Assessment help', 'Conditions, scores, confidence and eligibility.', 'cri'],
  ['Transformation support', 'Goals, tasks, timelines and stage plans.', 'plan'],
  ['Technical support', 'Access, performance or integration issues.', 'admin'],
  ['Roles and access', 'Who can see and do what.', 'team'],
];

export function Help() {
  return (
    <>
      <PageHeading page="help" />
      <div className="feature-grid">
        {TOPICS.map(([title, text, page], i) => (
          <Link key={title} to={pathOf(page)} className="feature-card">
            <div className="feature-icon">{String(i + 1).padStart(2, '0')}</div>
            <h3>{title}</h3><p>{text}</p>
            <div className="feature-meta"><span>Guide</span><b>Open →</b></div>
          </Link>
        ))}
      </div>
    </>
  );
}
