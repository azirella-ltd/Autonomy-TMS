/**
 * Digest Message Component
 *
 * Renders the LLM-synthesized digest text with embedded DecisionCard
 * components inline in the message stream. The digest is the first
 * "message" in the Decision Stream conversation.
 */
import React from 'react';
import Markdown from 'react-markdown';
import { Bot, Sparkles } from 'lucide-react';
import DecisionCard from './DecisionCard';
import { cn } from '../../lib/utils/cn';

const AIAvatar = () => (
  <div
    className={cn(
      'h-9 w-9 rounded-full flex items-center justify-center flex-shrink-0',
      'bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600',
      'shadow-[0_0_10px_rgba(139,92,246,0.4)]'
    )}
  >
    <Sparkles className="h-4 w-4 text-white" />
  </div>
);

const DigestMessage = ({
  digestText,
  decisions = [],
  onAccept,
  onOverride,
  onAskWhy,
}) => {
  return (
    <div className="flex gap-3 mb-6">
      <AIAvatar />
      <div className="flex-1 min-w-0">
        {/* Digest text bubble */}
        <div className="bg-card border rounded-lg p-4 mb-3">
          <div className="text-sm leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-strong:text-foreground">
            <Markdown>{digestText}</Markdown>
          </div>
        </div>

        {/* Embedded decision cards */}
        {decisions.length > 0 && (
          <div className="space-y-3">
            {decisions.map((decision) => (
              <DecisionCard
                key={`${decision.decision_type}-${decision.id}`}
                decision={decision}
                onAccept={onAccept}
                onOverride={onOverride}
                onAskWhy={onAskWhy}
                compact
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DigestMessage;
