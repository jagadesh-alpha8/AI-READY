import React, { useEffect, useRef, useState } from 'react';
import { Bot, Send } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { PageHeader } from '../../components/PageHeader';
import { CHAT_FALLBACK, CHAT_OPENING, CHAT_REPLIES, CHAT_SUGGESTIONS } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's chat page.
 *
 * ⚠ This is a SCRIPTED demo. Replies are matched on a keyword from a fixed
 * list — no model is called, nothing reads the institution's data. Of
 * everything ported, a chat box is the easiest thing to mistake for working
 * AI, so the page says so twice: in the banner, and on the assistant's own
 * status line. */

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

function timestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scriptedReply(question: string): string {
  const lower = question.toLowerCase();
  const hit = CHAT_REPLIES.find((r) => lower.includes(r.keyword));
  return hit ? hit.reply : CHAT_FALLBACK;
}

export const AIChatbot: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    { id: 'opening', role: 'assistant', content: CHAT_OPENING, time: timestamp() },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<number>();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, thinking]);

  // The reply is on a timer; leaving the page mid-"thought" must not set
  // state on an unmounted component.
  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  const send = () => {
    const question = input.trim();
    if (!question || thinking) return;

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: question, time: timestamp() },
    ]);
    setInput('');
    setThinking(true);

    timerRef.current = window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', content: scriptedReply(question), time: timestamp() },
      ]);
      setThinking(false);
    }, 700);
  };

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="Replies are scripted keyword matches — no AI model is called and none of your data is read." />

      <PageHeader
        icon={Bot}
        title="AI Chatbot"
        description="Ask about readiness in plain language. Answers should cite the evidence behind them — that part is not built."
      />

      <div className="glass-card flex flex-col h-[calc(100vh-22rem)] min-h-[26rem] overflow-hidden">
        <div className="p-4 border-b border-line-200 flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-full bg-brand-500/15 border border-brand-500/30 text-brand-800 flex items-center justify-center shrink-0">
            <Bot className="w-[18px] h-[18px]" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-ink-900">AI Readiness Chatbot</p>
            <p className="text-xs text-warning">Scripted demo — not connected to a model</p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 ${
                  message.role === 'user'
                    ? 'bg-brand-500 text-on-brand'
                    : 'bg-surface border border-line-200 text-ink-900'
                }`}
              >
                <p className="text-sm whitespace-pre-line">{message.content}</p>
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
                <span className="sr-only">Composing a reply</span>
              </div>
            </div>
          )}

          <div ref={endRef} />
        </div>

        <div className="p-4 border-t border-line-200 space-y-2 shrink-0">
          <div className="flex gap-2 overflow-x-auto pb-0.5">
            {CHAT_SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setInput(suggestion)}
                className="px-3 py-1 rounded-full text-xs font-medium bg-brand-500/10 text-brand-800 border border-brand-500/25 whitespace-nowrap hover:bg-brand-500/20 transition-colors"
              >
                {suggestion}
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
              placeholder="Ask about gaps, documents, tasks or the CRI score…"
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
