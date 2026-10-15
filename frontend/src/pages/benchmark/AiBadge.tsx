import React from 'react';
import { Bot } from 'lucide-react';

/** Marks benchmark content written by AI (fully automatic drafting, not reviewed by an expert). */
export const AiBadge: React.FC<{ model?: string }> = ({ model }) =>
  model ? (
    <span className="badge badge-warning inline-flex items-center gap-1" title={`Written by AI (${model}); not reviewed by an expert`}>
      <Bot className="w-3 h-3" /> AI-generated
    </span>
  ) : null;
