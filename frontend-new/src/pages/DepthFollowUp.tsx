import { useMemo } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, SampleTable, Stat, Table } from '../components/ui';
import { useCapability } from '../hooks/useCapability';
import type { Sprint } from '../types/api';
import { isPartCredit } from '../utils/capability';

/** Defaults from the A2 depth skeleton (backend/config/settings.py DEPTH_*); the API does not expose them yet. */
const MAX_QUESTIONS = 25;
const MISSING_SLOTS = 10;

/**
 * A2 "follow-up questions about the depth of evidence" (docs/capability/DEPTH_FOLLOW_UP_HANDOFF.md).
 * The backend stage runs only through the depth_* management commands and has no HTTP API yet, so this screen shows
 * what it can derive from the latest real assessment (which conditions would get depth questions and which key
 * indicators a "do you have anything?" question) and keeps the response and judging steps as labelled sample data.
 */
export function DepthFollowUp() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const cap = useCapability(sprint.id);
  const a = cap.assessment;

  const plan = useMemo(() => {
    if (!a) return null;
    const records = new Map(a.records.map((r) => [r.condition_id, r]));
    const credited: { id: string; indicator: string; text: string; credit: number }[] = [];
    const missing = new Map<string, { code: string; name: string; conditions: number }>();
    for (const i of a.result.indicators) {
      for (const c of i.conditions) {
        const rec = records.get(c.id);
        const credit = typeof rec?.credit === 'number' ? rec.credit : c.state === 'met' ? 1 : 0;
        if (credit > 0) credited.push({ id: c.id, indicator: i.code, text: c.text, credit });
        else {
          const m = missing.get(i.code) || { code: i.code, name: i.name, conditions: 0 };
          m.conditions += 1;
          missing.set(i.code, m);
        }
      }
    }
    credited.sort((x, y) => y.credit - x.credit);
    return { credited, missing: Array.from(missing.values()) };
  }, [a]);

  const depthSlots = MAX_QUESTIONS - Math.min(MISSING_SLOTS, plan?.missing.length ?? 0);

  return (
    <>
      <PageHeading page="depth" />
      <Notice tone="info">
        This stage is new in A2 and runs after the provisional assessment. It never changes an assessment, its score or its reports:
        depth is reported as a separate depth index until the credit decision is made.
      </Notice>
      {cap.loading ? <Loading /> : cap.error ? <ErrorState error={cap.error} /> : !a || !plan ? (
        <Empty title="No completed assessment" action={<PageLink to="assessment" className="primary-action">Run an assessment</PageLink>}>
          Depth questions are drawn from a completed assessment run.
        </Empty>
      ) : (
        <>
          <div className="stat-grid">
            <Stat label="Credited conditions" value={plan.credited.length} note="Each can get depth questions" />
            <Stat label="Key indicators with nothing credited" value={plan.missing.length} note={`One "do you have anything?" question each, up to ${MISSING_SLOTS}`} />
            <Stat label="Question budget" value={MAX_QUESTIONS} note={`${depthSlots} for depth, ${Math.min(MISSING_SLOTS, plan.missing.length)} for missing evidence`} />
            <Stat label="Scoring" value={isPartCredit(a.result) ? 'Part credit' : 'Conditions'} note="Depth needs part-credit runs to weigh credit" />
          </div>
          <Panel title="Conditions that would get depth questions" sub="Highest weight × credit first; the model asks only about quality dimensions the quotes do not already answer">
            {!plan.credited.length ? <p className="muted">Nothing is credited yet.</p> : (
              <Table columns={['Condition', 'Indicator', 'Requirement', 'Credit']}>
                {plan.credited.slice(0, depthSlots).map((c) => (
                  <tr key={c.id}><td><b>{c.id}</b></td><td>{c.indicator}</td><td><span className="clamp-2">{c.text}</span></td><td>{Math.round(c.credit * 100)}%</td></tr>
                ))}
              </Table>
            )}
          </Panel>
          <Panel title='Key indicators that would get a "do you have anything?" question' sub="Built from the condition texts and their typical evidence forms, without a model call">
            {!plan.missing.length ? <p className="muted">Every key indicator has some credit.</p> : (
              <Table columns={['Indicator', 'Name', 'Uncredited conditions']}>
                {plan.missing.slice(0, MISSING_SLOTS).map((m) => <tr key={m.code}><td><b>{m.code}</b></td><td>{m.name}</td><td>{m.conditions}</td></tr>)}
              </Table>
            )}
          </Panel>
        </>
      )}
      <Dummy code="R-10" title="Institution responses and depth levels"
        note="Not yet in the backend API: questions, responses and judgments are created by the depth_questions, depth_load_responses and depth_judge commands. An answer counts as supported only when a document backs it.">
        <SampleTable columns={['Condition', 'Question', 'Response', 'Supported', 'Depth level']} rows={[
          ['AIQIF-C4.1-a', 'How many teaching hours did the faculty AI programme run, and was it accredited?', '40 hours, AICTE ATAL FDP', 'Yes (certificate)', 'Substantiated'],
          ['AIQIF-C4.1-b', 'How many of the faculty completed it, out of how many?', '62 of 180', 'No document', 'Evidenced (capped one level)'],
          ['AIQIF-C2.3-a', 'Who reviews the AI policy, and how often?', "Don't know", '—', 'Evidenced'],
        ]} />
      </Dummy>
      <Dummy code="R-10" title="Open decisions (settings)" note="Held as backend settings until Harsha and Vijay decide; shown here with the handoff's defaults.">
        <SampleTable columns={['Decision', 'Default']} rows={[
          ['Can an answer lower a score?', 'Only an answer that contradicts the credited evidence'],
          ['How much credit does depth carry?', 'Undecided: depth index only, no credit change'],
          ['An answer without a document', 'Caps the level one step lower'],
          ['Who approves past cases?', 'Django admin, to be decided'],
        ]} />
      </Dummy>
    </>
  );
}
