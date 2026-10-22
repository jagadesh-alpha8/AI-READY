import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, FileText, Info, Send } from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { getScore } from '../../api/scoring';
import { listSprintGaps } from '../../api/gaps';
import { listSprintDocuments } from '../../api/documents';
import { listRecommendations } from '../../api/recommendations';
import { searchEvidence } from '../../api/evidence';
import type { EvidenceResult } from '../../api/evidence';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { PageHeader } from '../../components/PageHeader';
import type { Gap, Recommendation, Scorecard, Sprint, SprintDocument } from '../../types';

/**
 * AI Copilot — answers about this institution's readiness, from its own data.
 *
 * ⚠ What this is, precisely: questions about the score, gaps, documents and
 * next steps are answered **deterministically** from the live API — real
 * figures, no model involved. Anything else is sent to the vector store's
 * semantic search, which returns the institution's own document passages,
 * each cited to a document and page.
 *
 * What it is NOT: a language model. There is no chat endpoint on the backend
 * and no LLM call anywhere in this file. It recognises a fixed set of
 * intents and otherwise searches documents. The page says so, because a chat
 * box is the single easiest thing in this product to mistake for more than
 * it is.
 *
 * This is also the first screen to use the vector store the backend has had
 * all along — spec §4.2 allows exactly this: retrieval is advisory, and it
 * never touches official scoring.
 */

interface Citation {
  document: string;
  page: number | null;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  time: string;
  /** Where the answer came from — a screen, or documents and pages. */
  sources?: Citation[];
  note?: string;
}

const SUGGESTIONS = [
  'What is our CRI score?',
  'What are our biggest gaps?',
  'Which documents are missing?',
  'What should we do next?',
];

function timestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** A readable excerpt of a retrieved chunk. Chunks run to ~1,200 characters;
 * quoting one whole buries the answer it contains. Cut on a word boundary so
 * the quote does not end mid-word, and let the citation carry the rest. */
function excerpt(text: string, limit = 320): string {
  const clean = text.trim().replace(/\s+/g, ' ');
  if (clean.length <= limit) return clean;
  const cut = clean.slice(0, limit);
  return `${cut.slice(0, cut.lastIndexOf(' '))}…`;
}

function has(text: string, ...words: string[]): boolean {
  const lower = text.toLowerCase();
  return words.some((w) => lower.includes(w));
}

export const AICopilot: React.FC = () => {
  // The selected sprint is shared by every page (context/SelectedSprintContext.tsx).
  const { sprintId: selectedSprintId } = useSelectedSprint();
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  const { data: sprints, loading: sprintsLoading, error: sprintsError, refetch: refetchSprints } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = selectedSprintId;

  const { data: scorecard } = useApiResource<Scorecard>(
    () => getScore(activeSprintId), [activeSprintId], !!activeSprintId,
  );
  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId), [activeSprintId], !!activeSprintId,
  );
  const { data: documents } = useApiResource<SprintDocument[]>(
    () => listSprintDocuments(activeSprintId), [activeSprintId], !!activeSprintId,
  );
  const { data: recommendations } = useApiResource<Recommendation[]>(
    () => listRecommendations(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const openGaps = useMemo(
    () => (gaps ?? []).filter((g) => g.status === 'open' || g.status === 'in_progress'),
    [gaps],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, thinking]);

  // A fresh greeting whenever the sprint changes — the previous answers were
  // about a different institution's data and must not sit above new ones.
  useEffect(() => {
    if (!activeSprintId) return;
    setMessages([{
      id: `open-${activeSprintId}`,
      role: 'assistant',
      time: timestamp(),
      content:
        'Ask about the readiness score, the gaps behind it, missing documents, or what to do next — '
        + 'I answer those from this sprint\'s live data. Anything else I search the uploaded documents for, '
        + 'and cite the page.',
    }]);
  }, [activeSprintId]);

  const reply = (content: string, extras: Partial<Message> = {}) => {
    setMessages((prev) => [
      ...prev,
      { id: `a-${Date.now()}`, role: 'assistant', content, time: timestamp(), ...extras },
    ]);
  };

  /** Deterministic answers, composed from figures already on screen
   * elsewhere. Returns null when no known intent matches. */
  const answerFromData = (q: string): { content: string; sources?: Citation[] } | null => {
    if (has(q, 'cri', 'score', 'readiness index', 'how ready')) {
      if (!scorecard) return { content: 'The score has not been calculated for this sprint yet.' };
      const weakest = [...scorecard.pillar_scores].sort((a, b) => a.raw_score - b.raw_score).slice(0, 3);
      return {
        content:
          `The Campus Readiness Index is ${scorecard.overall_cri.toFixed(1)} / 100, `
          + `at ${(scorecard.overall_confidence * 100).toFixed(0)}% confidence `
          + `(engine ${scorecard.calculation_version}).\n\n`
          + `Weakest pillars:\n`
          + weakest.map((p) => `• ${p.label} — ${p.raw_score.toFixed(1)}`).join('\n')
          + `\n\nIt was built from ${scorecard.evidence_metrics.documents_processed} processed document(s) `
          + `and ${scorecard.evidence_metrics.confirmed_facts} confirmed fact(s).`,
      };
    }

    if (has(q, 'gap', 'weak', 'missing data', 'blocking')) {
      if (openGaps.length === 0) return { content: 'There are no open gaps on this sprint.' };
      const blocking = openGaps.filter((g) => g.priority === 'blocking');
      const top = [...openGaps].sort((a, b) => (b.score_impact || 0) - (a.score_impact || 0)).slice(0, 5);
      return {
        content:
          `There are ${openGaps.length} open gaps, ${blocking.length} of them blocking `
          + `(a baseline cannot be approved while those are open).\n\n`
          + `Highest score impact:\n`
          + top.map((g) => `• ${g.title} — −${(g.score_impact || 0).toFixed(1)} pts`).join('\n'),
      };
    }

    if (has(q, 'document', 'upload', 'evidence missing', 'file')) {
      const docs = documents ?? [];
      const missing = openGaps.filter((g) => g.gap_type === 'missing_document');
      return {
        content:
          `${docs.length} document(s) uploaded, ${docs.filter((d) => d.status === 'processed').length} processed.\n\n`
          + (missing.length > 0
            ? `${missing.length} required document(s) still missing:\n`
              + missing.map((g) => `• ${g.title.replace(/^Missing /, '')}`).join('\n')
            : 'No required documents are outstanding.'),
      };
    }

    if (has(q, 'next', 'recommend', 'should we', 'what to do', 'priority', 'improve')) {
      const recs = (recommendations ?? []).filter((r) => r.status !== 'hidden');
      if (recs.length === 0) {
        return { content: 'No recommendations have been generated for this sprint yet.' };
      }
      const top = [...recs].sort((a, b) => (b.expected_cri_lift || 0) - (a.expected_cri_lift || 0)).slice(0, 4);
      const total = recs.reduce((s, r) => s + (r.expected_cri_lift || 0), 0);
      return {
        content:
          `There are ${recs.length} recommendations, worth about ${total.toFixed(1)} CRI points in total.\n\n`
          + `Highest impact first:\n`
          + top.map((r) => `• ${r.title} — +${(r.expected_cri_lift || 0).toFixed(1)} (${r.timeline})`).join('\n'),
      };
    }

    return null;
  };

  const send = async () => {
    const question = input.trim();
    if (!question || thinking || !activeSprintId) return;

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: question, time: timestamp() },
    ]);
    setInput('');
    setThinking(true);

    const direct = answerFromData(question);
    if (direct) {
      reply(direct.content, { note: 'Answered from this sprint\'s live data.' });
      setThinking(false);
      return;
    }

    // Not a known metric question — look for it in the documents themselves.
    try {
      const { data } = await searchEvidence(activeSprintId, question);
      if (data.count === 0) {
        reply(
          'I could not find anything about that in the uploaded documents. Try different wording, '
          + 'or ask about the score, gaps, documents or next steps — I answer those directly.',
        );
      } else {
        reply(
          data.results.map((r: EvidenceResult) => `“${excerpt(r.text)}”`).join('\n\n'),
          {
            sources: data.results.map((r) => ({
              document: r.document_name || 'Untitled document',
              page: r.page_number,
            })),
            note: 'Found in this institution\'s own documents.',
          },
        );
      }
    } catch (err) {
      reply(getErrorMessage(
        err,
        'Document search is unavailable right now. I can still answer about the score, gaps, documents and next steps.',
      ));
    } finally {
      setThinking(false);
    }
  };

  if (sprintsLoading) return <LoadingState message="Loading sprints…" />;
  if (sprintsError) return <ErrorState message={sprintsError} onRetry={refetchSprints} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Bot}
          title="AI Copilot"
          description="Ask about this institution's readiness. Answers come from its own audit data and documents."
        />
        <EmptyState message="No sprints yet. There is nothing to answer questions about until one runs." />
      </div>
    );
  }

  if (!activeSprintId) return <SelectSprintPrompt />;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Bot}
        title="AI Copilot"
        description="Ask about this institution's readiness. Answers come from its own audit data and documents."
      />


      <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600 min-w-0">
          <strong className="text-info">Not a language model. </strong>
          Questions about the score, gaps, documents and next steps are answered directly from this
          sprint's live data. Anything else searches the uploaded documents and quotes them with a
          page reference. Nothing here is generated prose, and nothing it says can change a score.
        </p>
      </div>

      <div className="glass-card flex flex-col h-[calc(100vh-26rem)] min-h-[24rem] overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 ${
                  message.role === 'user'
                    ? 'bg-brand-500 text-on-brand'
                    : 'bg-surface border border-line-200 text-ink-900'
                }`}
              >
                <p className="text-sm whitespace-pre-line">{message.content}</p>

                {message.sources && message.sources.length > 0 && (
                  <div className="mt-2.5 pt-2.5 border-t border-line-200 space-y-1">
                    {message.sources.map((s, i) => (
                      <p key={i} className="text-[11px] text-ink-500 flex items-start gap-1.5">
                        <FileText className="w-3 h-3 shrink-0 mt-0.5" />
                        <span>
                          {s.document}
                          {s.page ? `, page ${s.page}` : ''}
                        </span>
                      </p>
                    ))}
                  </div>
                )}

                {message.note && (
                  <p className="text-[10px] text-ink-500 mt-1.5 italic">{message.note}</p>
                )}

                <p className={`text-[10px] mt-1 ${message.role === 'user' ? 'opacity-70' : 'text-ink-500'}`}>
                  {message.time}
                </p>
              </div>
            </div>
          ))}

          {thinking && (
            <div className="flex justify-start" aria-live="polite">
              <div className="bg-surface border border-line-200 rounded-2xl px-4 py-3 flex gap-1.5">
                {[0, 0.15, 0.3].map((delay) => (
                  <span
                    key={delay}
                    className="w-1.5 h-1.5 rounded-full bg-ink-500/60 animate-bounce"
                    style={{ animationDelay: `${delay}s` }}
                  />
                ))}
                <span className="sr-only">Looking that up</span>
              </div>
            </div>
          )}

          <div ref={endRef} />
        </div>

        <div className="p-4 border-t border-line-200 space-y-2 shrink-0">
          <div className="flex gap-2 overflow-x-auto pb-0.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setInput(s)}
                className="px-3 py-1 rounded-full text-xs font-medium bg-brand-500/10 text-brand-800 border border-brand-500/25 whitespace-nowrap hover:bg-brand-500/20 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Ask about the score, gaps, documents — or search the uploads…"
              aria-label="Ask a question"
              className="input flex-1"
            />
            <button
              type="button"
              onClick={send}
              disabled={thinking || !input.trim()}
              className="btn-primary shrink-0"
              aria-label="Send"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
