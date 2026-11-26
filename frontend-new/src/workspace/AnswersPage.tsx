import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import { useResource } from '../hooks/useResource';
import { pathOf } from '../navigation';
import { getQuestions, type Layer2Question, type Layer2Response } from '../services/capability';
import type { Sprint } from '../types/api';
import { pillarName } from '../utils/capability';
import { dateTime, tidyText } from '../utils/format';

/**
 * Assessment › Your answers (merged website design, 27 Nov 2026): every follow-up question answered so far, with
 * what came of each answer. Read from the question list the follow-up page already uses (?list=1).
 */
export function AnswersPage() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

/** What came of an answer, in a few words. */
export function answerState(r: Layer2Response): { label: string; tone: 'ok' | 'wait' | 'none' } {
  if (r.kind === 'dont_know') return { label: 'Skipped', tone: 'none' };
  if (r.choice === 'not_yet') return { label: 'Not yet in place', tone: 'none' };
  if (r.status === 'pending') return { label: 'Being checked against your documents', tone: 'wait' };
  return r.supported ? { label: 'Supported by a document', tone: 'ok' } : { label: 'No supporting document found', tone: 'none' };
}

const question = (q: Layer2Question) => q.text.split('\n')[0];

function Body({ sprint }: { sprint: Sprint }) {
  const cap = useCapability(sprint.id);
  const runId = cap.provisionalId;
  const list = useResource(() => getQuestions(sprint.id, runId), `answers:${runId}`, !!runId);
  if (cap.loading || (runId && list.loading && !list.data)) return <Loading label="Loading your answers…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (list.error) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />;
  if (!runId) return <Empty title="No follow-up questions yet">They come with your Stage 1 result.</Empty>;
  const all = list.data?.questions || [];
  const answered = all.filter((q) => q.response);
  const marked = all.filter((q) => !q.response && q.to_check);
  const open = list.data?.progress.open ?? 0;
  const closed = !!list.data?.progress.closed || !!list.data?.progress.final_run_id;
  return (
    <div className="ws-answers">
      <p className="muted">
        {answered.length} of {list.data?.progress.questions ?? all.length} questions answered
        {marked.length ? `, ${marked.length} marked “I need to check”` : ''}.
        {!closed && open > 0 && <> <Link className="text-btn" to={pathOf('questionnaire')}>Answer the next question</Link></>}
      </p>
      {!answered.length && !marked.length ? (
        <Empty title="No answers yet">Your answers appear here as you give them.</Empty>
      ) : (
        <ol className="ws-answer-list">
          {marked.map((q) => (
            <li key={q.id}>
              <div className="ws-answer-top"><small>{pillarName(q.indicator_code.split('.')[0])}</small><span className="tag amber">I need to check</span></div>
              <strong>{question(q)}</strong>
              {!closed && <Link className="text-btn" to={`${pathOf('questionnaire')}?question=${q.id}`}>Answer it now</Link>}
            </li>
          ))}
          {answered.map((q) => {
            const r = q.response!;
            const state = answerState(r);
            return (
              <li key={q.id}>
                <div className="ws-answer-top"><small>{pillarName(q.indicator_code.split('.')[0])}</small>
                  <span className={`tag ${state.tone === 'ok' ? '' : state.tone === 'wait' ? 'blue' : 'gray'}`}>{state.label}</span></div>
                <strong>{question(q)}</strong>
                {r.answer && <p>{tidyText(r.answer)}</p>}
                <small>{r.document_ids.length ? `${r.document_ids.length} document${r.document_ids.length === 1 ? '' : 's'} attached · ` : 'No document attached · '}{dateTime(r.created_at)}</small>
                {r.follow_up && <p className="muted"><em>We asked one more thing:</em> {r.follow_up}</p>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
