import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, ErrorState, Loading, Notice } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { useResource } from '../hooks/useResource';
import { pathOf } from '../navigation';
import { cancelRun, getQuestions, startRun } from '../services/capability';
import { newKey } from '../utils/capability';
import { listSprintGapsPage } from '../services/gaps';
import { getSprintOverview } from '../services/sprints';
import type { Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { dateTime } from '../utils/format';
import { levelFor, whole } from '../utils/levels';
import { Icon, Stars } from './Icon';

/**
 * The assessment for a college (23 Nov, Harsha's design): four steps from the documents to the final result, where
 * each one stands, and the one thing to do next. InGage staff keep the detailed run panel (pages/Assessment.tsx).
 */
export function AssessmentPage() {
  return <RequireSprint>{(sprint) => <AssessmentBody sprint={sprint} />}</RequireSprint>;
}

type StepState = 'done' | 'current' | 'waiting';

function AssessmentBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const cap = useCapability(sprint.id);
  const overview = useResource(() => getSprintOverview(sprint.id), `ws-ov:${sprint.id}`);
  const questions = useResource(() => getQuestions(sprint.id, cap.provisionalId), `ws-aq:${cap.provisionalId}`, !!cap.provisionalId);
  const conflicts = useResource<number>(async () => {
    const res = await listSprintGapsPage(sprint.id, { gap_type: 'conflict', status: 'open', page_size: 1 });
    return { data: res.data.count };
  }, `ws-conf:${sprint.id}`);
  const [confirming, setConfirming] = useState(false);
  const [key] = useState(newKey);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  if (cap.loading && !cap.runs.data) return <Loading label="Loading your assessment…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;

  const docs = overview.data?.documents;
  const processed = docs?.processed ?? 0;
  const result = cap.assessment?.result;
  const score = result?.score ?? null;
  const final = cap.stage === 'final';
  const progress = questions.data?.progress;
  const asked = progress?.questions ?? 0;
  const open = progress?.open ?? 0;
  const toCheck = progress?.to_check ?? 0;
  const disagree = conflicts.data || 0;
  const hasResult = score != null;
  const failed = cap.newest?.status === 'failed' && !cap.running;

  const steps: { title: string; text: string; state: StepState; link?: { to: string; label: string } }[] = [
    {
      title: 'Your documents', state: processed > 0 ? 'done' : 'current',
      text: processed > 0 ? `${processed} document${processed === 1 ? '' : 's'} read${disagree ? `; ${disagree} fact${disagree === 1 ? '' : 's'} to settle` : ''}.`
        : 'Send the documents that show your AI practice.',
      link: { to: pathOf(processed > 0 && disagree ? 'gaps' : 'uploads'), label: processed > 0 && disagree ? 'Settle facts' : 'Documents' },
    },
    {
      title: 'Stage 1 result', state: hasResult ? 'done' : cap.running ? 'current' : processed > 0 ? 'current' : 'waiting',
      text: cap.running ? 'Reading your documents now. This takes a while; you can leave this page.'
        : hasResult ? (final ? 'Done: your documents were read and scored.' : `From your documents: ${whole(score)} out of 100.`) : 'We read your documents against 216 practices in nine areas.',
    },
    {
      title: 'Follow-up questions', state: final ? 'done' : hasResult ? 'current' : 'waiting',
      text: final ? 'Closed.' : hasResult ? (asked ? `${asked - open} of ${asked} answered${toCheck ? `, ${toCheck} to check` : ''}. Answers backed by documents can add to your score.` : 'Questions on what your documents show.')
        : 'After the Stage 1 result.',
      link: hasResult && !final ? { to: pathOf('questionnaire'), label: open ? 'Answer' : 'Review' } : undefined,
    },
    {
      title: 'Final result', state: final ? 'done' : 'waiting',
      text: final ? `Published: ${whole(score)} out of 100.` : 'Published when you finish the follow-up questions.',
      link: final ? { to: pathOf('cri'), label: 'See result' } : undefined,
    },
  ];

  const level = hasResult ? levelFor(score) : null;
  const canRun = can('sprint.manage') && cap.enabled && !cap.running;
  const disagreeText = disagree ? `${disagree} fact${disagree === 1 ? '' : 's'} where your documents disagree ${disagree === 1 ? 'is' : 'are'} not settled yet. ` +
    'The assessment reads the documents as they are now, so settle them first if you can. ' : '';

  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="ws-steps" role="list">
        {steps.map((s, i) => (
          <div key={s.title} role="listitem" className={`ws-step ${s.state}`}>
            <span className="ws-step-mark">{s.state === 'done' ? <Icon name="check" size={14} /> : i + 1}</span>
            <div>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
              {s.link && <Link className="text-btn" to={s.link.to}>{s.link.label} <Icon name="chevron" size={13} /></Link>}
            </div>
          </div>
        ))}
      </div>

      <div className="ws-grid-2" style={{ marginTop: 24 }}>
        <section className="surface surface-pad">
          {cap.running ? (
            <>
              <h2>Your assessment is running</h2>
              <p className="muted" style={{ marginTop: 8 }}>Started {dateTime(cap.newest?.created_at)}. We are reading your documents against each practice and quoting what we find. This page updates by itself.</p>
              <div className="meter" style={{ marginTop: 18 }}><i style={{ width: '45%' }} className="ws-pulse" /></div>
              {can('sprint.manage') && cap.newest && (
                <button className="secondary-button" style={{ marginTop: 18 }} onClick={async () => {
                  try { await cancelRun(sprint.id, cap.newest!.id); await cap.runs.refetch(); setMsg({ tone: 'success', text: 'The assessment was stopped.' }); }
                  catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
                }}>Stop the assessment</button>
              )}
            </>
          ) : hasResult && level ? (
            <>
              <div className="ws-row" style={{ justifyContent: 'space-between' }}>
                <h2>{final ? 'Your final result' : 'Your Stage 1 result'}</h2>
                <span className="tag">{final ? 'Final' : 'From your documents'}</span>
              </div>
              <div className="ws-row" style={{ marginTop: 16, gap: 18 }}>
                <span className="ws-big-number">{whole(score)}</span>
                <div><Stars stars={level.stars} size={20} /><div style={{ fontWeight: 650, color: 'var(--green)' }}>{level.name}{final ? '' : ' so far'}</div></div>
              </div>
              <p className="muted" style={{ marginTop: 12 }}>{level.meaning}</p>
              <div className="ws-row" style={{ marginTop: 18 }}>
                <Link className="primary-action" to={pathOf(final ? 'cri' : open ? 'questionnaire' : 'cri')}>{final ? 'See your result' : open ? 'Answer the follow-up questions' : 'See your result'}</Link>
                <Link className="secondary-button" to={pathOf('reports')}>Reports</Link>
              </div>
            </>
          ) : (
            <>
              <h2>Run your assessment</h2>
              <p className="muted" style={{ marginTop: 8 }}>We read every document you sent against 216 practices in nine areas of AI readiness, and quote the passage behind each finding. You get your Stage 1 result, then follow-up questions to complete it.</p>
              {failed && <Notice tone="error">The last attempt could not finish, so nothing was published. You can run it again.</Notice>}
              {disagree > 0 && <Notice tone="info">{disagreeText}<Link to={pathOf('gaps')}>Settle them</Link></Notice>}
              {canRun ? <button className="primary-action" style={{ marginTop: 16 }} disabled={processed === 0} onClick={() => setConfirming(true)}>Run the assessment</button>
                : !cap.enabled ? <p className="muted" style={{ marginTop: 12 }}>Assessments are switched off on this server for now.</p> : null}
              {processed === 0 && <p className="muted" style={{ marginTop: 10 }}>Send your documents first.</p>}
            </>
          )}
        </section>

        <aside className="surface surface-pad">
          <h2>How it works</h2>
          <ol className="ws-plain-list" style={{ marginTop: 12 }}>
            <li><strong>Your documents are the evidence.</strong> A practice counts when a document shows it; a quote and its page back every finding.</li>
            <li><strong>Part of the credit is held.</strong> A quarter of what each document shows is held until your follow-up answers confirm how far it goes.</li>
            <li><strong>Nothing missing lowers your score.</strong> A practice we did not find may still exist: send the document and it can be counted.</li>
            <li><strong>Five levels, one star for every 20 points</strong>, from Starting out to Leading.</li>
          </ol>
        </aside>
      </div>

      {confirming && (
        <ActionDialog
          title="Run the assessment?"
          description={`${disagreeText}We read the documents you have sent so far. Documents you send later can be added through the follow-up questions.`}
          fields={[]}
          confirmLabel="Run the assessment"
          onSubmit={async () => {
            await startRun(sprint.id, key);
            await cap.runs.refetch();   // the panel shows it running, then the result
          }}
          onClose={() => setConfirming(false)}
        />
      )}
    </>
  );
}
