import React from 'react';
import { Bot } from 'lucide-react';

/** Marks benchmark content drafted by AI. It reaches a release only after a reviewer confirms the benchmark. */
export const AiBadge: React.FC<{ model?: string }> = ({ model }) =>
  model ? (
    <span className="badge badge-warning inline-flex items-center gap-1" title={`Drafted by AI (${model}); a reviewer must confirm the benchmark before it can be released`}>
      <Bot className="w-3 h-3" /> AI draft
    </span>
  ) : null;
