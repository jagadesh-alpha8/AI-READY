import { useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, Empty, Notice, PageHeading, Panel } from '../components/ui';
import { searchEvidence } from '../services/evidenceSearch';
import type { EvidenceResult, Sprint } from '../types/api';
import { errorMessage, statusOf } from '../utils/errors';

interface Turn { question: string; results: EvidenceResult[] | null; error: string; unavailable: boolean }

export function Advisor() {
  return <RequireSprint>{(sprint) => <AdvisorBody sprint={sprint} />}</RequireSprint>;
}

/** Grounded answers only: every passage shown cites the institution's own document and page. */
function AdvisorBody({ sprint }: { sprint: Sprint }) {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async (e: FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    try {
      const res = await searchEvidence(sprint.id, q);
      setTurns((t) => [{ question: q, results: res.data.results, error: '', unavailable: false }, ...t]);
    } catch (err) {
      setTurns((t) => [{ question: q, results: null, error: errorMessage(err), unavailable: statusOf(err) === 503 }, ...t]);
    } finally {
      setBusy(false);
      setQuestion('');
    }
  };

  return (
    <>
      <PageHeading page="copilot" />
      <Dummy title="Written advisor answers" note="The backend offers grounded evidence search, not a conversational answer endpoint. Real questions below return cited passages from this sprint's documents.">
        <div className="advisor-answer">
          <div className="activity"><span className="activity-icon">You</span><div><strong>Why is faculty capability blocking Gold?</strong></div></div>
          <p><b>AI readiness advisor</b>: Gold requires repeatable adoption across departments and measured impact. Current evidence confirms that 63% of faculty completed foundational training, but only 38% of programmes show verified curriculum integration.</p>
          <span className="status neutral">Sample answer</span>
        </div>
      </Dummy>
      <Panel className="advisor-panel">
        <form className="advisor-ask" onSubmit={ask}>
          <label className="sr-only" htmlFor="advisor-q">Question</label>
          <input id="advisor-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about this institution's evidence, score or plan…" />
          <button className="primary-action" disabled={busy || !question.trim()}>{busy ? 'Searching…' : 'Ask advisor'}</button>
        </form>
        {turns.length === 0 && <Empty title="Ask a question">For example: “Is there an approved AI policy?” or “How many faculty completed AI training?”</Empty>}
        <div className="activity-list">
          {turns.map((t, i) => (
            <div key={i} className="advisor-turn">
              <div className="activity"><span className="activity-icon">You</span><div><strong>{t.question}</strong></div></div>
              {t.unavailable ? <Notice tone="warn">Evidence search is not available on this server (the vector store is not configured).</Notice>
                : t.error ? <Notice tone="error">{t.error}</Notice>
                  : !t.results?.length ? <p className="muted">No passage in this sprint's documents answers that.</p> : (
                    <div className="advisor-answer">
                      <strong>AI readiness advisor</strong>
                      {t.results.map((r, j) => (
                        <blockquote key={j}>
                          <p>{r.text}</p>
                          <cite>{r.document_name}{r.page_number != null && `, page ${r.page_number}`} · relevance {(r.score * 100).toFixed(0)}%</cite>
                        </blockquote>
                      ))}
                      <span className="status good">Grounded in {t.results.length} source passage{t.results.length === 1 ? '' : 's'}</span>
                    </div>
                  )}
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}
