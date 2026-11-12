import { useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, Notice, PageHeading, Panel } from '../components/ui';
import { searchEvidence } from '../services/evidenceSearch';
import type { EvidenceResult, Sprint } from '../types/api';
import { errorMessage, statusOf } from '../utils/errors';

interface Turn { question: string; results: EvidenceResult[] | null; error: string; unavailable: boolean }

export function Advisor() {
  return <RequireSprint>{(sprint) => <AdvisorBody sprint={sprint} />}</RequireSprint>;
}

/** Evidence search: cited passages from the sprint's own documents (no written answers; R-03 is not planned). */
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
      <Panel className="advisor-panel">
        <form className="advisor-ask" onSubmit={ask}>
          <label className="sr-only" htmlFor="advisor-q">Question</label>
          <input id="advisor-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Search this institution's documents…" />
          <button className="primary-action" disabled={busy || !question.trim()}>{busy ? 'Searching…' : 'Search evidence'}</button>
        </form>
        {turns.length === 0 && <Empty title="Search the evidence">For example: “Is there an approved AI policy?” or “How many faculty completed AI training?”</Empty>}
        <div className="activity-list">
          {turns.map((t, i) => (
            <div key={i} className="advisor-turn">
              <div className="activity"><span className="activity-icon">You</span><div><strong>{t.question}</strong></div></div>
              {t.unavailable ? <Notice tone="warn">Evidence search is not available on this server (the vector store is not configured).</Notice>
                : t.error ? <Notice tone="error">{t.error}</Notice>
                  : !t.results?.length ? <p className="muted">No passage in this sprint's documents answers that.</p> : (
                    <div className="advisor-answer">
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
