/**
 * AzirellaPopup — Scrollable, persistent conversation popup for the "Azirella" feature.
 *
 * Replaces all 6 inline response panels from TopNavbar.jsx with a unified
 * conversation-thread UI anchored below the navbar input bar.
 *
 * Purely presentational — all logic/state management stays in TopNavbar.
 */

import React, { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import {
  X,
  Sparkles,
  Loader2,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Pin,
  PinOff,
} from 'lucide-react';
import Markdown from 'react-markdown';
import { cn } from '../lib/utils/cn';

// ─── Message Bubble ─────────────────────────────────────────────────────────────
const MessageBubble = ({ role, children }) => {
  if (role === 'user') {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-violet-500 text-white px-4 py-2.5 text-sm leading-relaxed">
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5 mb-3">
      <img src="/Azirella_logo.png" alt="" className="h-7 w-7 rounded-full object-cover object-[center_40%] flex-shrink-0" aria-hidden="true" />
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-accent/60 border border-border px-4 py-2.5 text-sm leading-relaxed text-foreground">
        {children}
      </div>
    </div>
  );
};

// ─── Build Messages ─────────────────────────────────────────────────────────────
// Constructs the conversation thread array from the current props state.
function buildMessages({
  userPrompt,
  analysisResult,
  streamMessages,
  isStreaming,
  directiveResult,
  rephrasedPrompt,
  onRephrasedChange,
  onSubmitRephrased,
  onSubmitCompound,
  onActivateDirective,
  onSkipDirective,
  onNavigate,
  onPromoteStrategy,
  submitting,
  clarifications,
  onClarificationAnswer,
  onClarificationSubmit,
}) {
  const messages = [];

  // ── 1. User prompt ──────────────────────────────────────────────────────────
  if (userPrompt) {
    messages.push({ role: 'user', key: 'user-prompt', content: userPrompt });
  }

  if (!analysisResult && !directiveResult && !isStreaming) {
    // Still waiting for analysis
    if (userPrompt) {
      messages.push({
        role: 'system',
        key: 'loading',
        content: (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>Analyzing...</span>
          </div>
        ),
      });
    }
    return messages;
  }

  const intent = analysisResult?.intent;

  // ─── QUESTION FLOW ────────────────────────────────────────────────────────
  if (intent === 'question') {
    messages.push({
      role: 'system',
      key: 'question-answer',
      content: (
        <div>
          <div className="font-medium text-foreground mb-1.5">Answer</div>
          <div className="whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
            {analysisResult.answer || 'No answer available.'}
          </div>
          {analysisResult.target_page && (
            <button
              onClick={() =>
                onNavigate?.(analysisResult.target_page, {
                  filters: analysisResult.filters || {},
                  fromAzirella: true,
                })
              }
              className="mt-3 flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
            >
              <ChevronRight className="h-3.5 w-3.5" />
              Go to {analysisResult.target_page_label || 'relevant page'}
            </button>
          )}
        </div>
      ),
    });
    return messages;
  }

  // ─── AMBIGUOUS / UNKNOWN FLOW ─────────────────────────────────────────────
  if (intent === 'unknown' || analysisResult?.clarification_needed) {
    messages.push({
      role: 'system',
      key: 'ambiguous',
      content: (
        <div>
          <div className="font-medium text-foreground mb-1.5">
            Clarification needed
          </div>
          <p className="text-sm text-foreground mb-3">
            {analysisResult.question ||
              "I'm not sure if this is a directive or a question. Could you clarify?"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => onSkipDirective?.()}
              className="flex-1 px-3 py-1.5 rounded-full text-xs font-medium bg-violet-500 text-white hover:bg-violet-600 transition-colors"
            >
              It's a directive
            </button>
            <button
              onClick={() => onActivateDirective?.()}
              className="flex-1 px-3 py-1.5 rounded-full text-xs font-medium bg-blue-500 text-white hover:bg-blue-600 transition-colors"
            >
              It's a question
            </button>
          </div>
        </div>
      ),
    });
    return messages;
  }

  // ─── SCENARIO QUESTION FLOW ───────────────────────────────────────────────
  if (intent === 'scenario_question' && analysisResult?.answer) {
    // Event injection banner
    if (analysisResult.event_summary) {
      messages.push({
        role: 'system',
        key: 'scenario-event-banner',
        content: (
          <div className="flex items-center gap-2 text-xs bg-violet-500/10 text-violet-700 dark:text-violet-300 rounded-md px-2.5 py-1.5">
            <Sparkles className="h-3 w-3 flex-shrink-0" />
            <span>{analysisResult.event_summary}</span>
          </div>
        ),
      });
    }

    // Fulfillment badge
    const canFulfill = analysisResult.can_fulfill;
    messages.push({
      role: 'system',
      key: 'scenario-analysis',
      content: (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="font-medium text-foreground">Scenario Analysis</span>
            {canFulfill === true && (
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-600">
                Can Fulfill
              </span>
            )}
            {canFulfill === false && (
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-red-500/10 text-red-600">
                Cannot Fulfill
              </span>
            )}
          </div>
          <div className="prose prose-sm dark:prose-invert max-h-80 overflow-y-auto text-foreground leading-relaxed [&_table]:text-xs [&_table]:w-full [&_th]:px-2 [&_th]:py-1 [&_td]:px-2 [&_td]:py-1 [&_th]:text-left [&_th]:font-medium [&_th]:border-b [&_th]:border-border [&_td]:border-b [&_td]:border-border/50 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1.5 [&_ul]:text-xs [&_li]:my-0.5">
            <Markdown>{analysisResult.answer}</Markdown>
          </div>
          <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-border">
            {analysisResult.confidence_note && (
              <span className="text-[10px] text-muted-foreground italic">
                {analysisResult.confidence_note}
              </span>
            )}
            <button
              onClick={() =>
                onNavigate?.('/scenario-events', {
                  configId: analysisResult.target_config_id,
                  eventId: analysisResult.event_id,
                  fromAzirella: true,
                })
              }
              className="flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors ml-auto"
            >
              <ChevronRight className="h-3.5 w-3.5" />
              Open in Scenario Events
            </button>
          </div>
        </div>
      ),
    });
    return messages;
  }

  // ─── COMPOUND FLOW ────────────────────────────────────────────────────────
  if (intent === 'compound') {
    // Understanding message with action badges
    if (analysisResult.actions) {
      messages.push({
        role: 'system',
        key: 'compound-understanding',
        content: (
          <div>
            <div className="font-medium text-foreground mb-2">
              I see both a new order and a directive:
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {analysisResult.actions.map((action, i) => (
                <span
                  key={i}
                  className={cn(
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                    action.action_type === 'demand_signal'
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300'
                      : 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300',
                  )}
                >
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      action.action_type === 'demand_signal'
                        ? 'bg-blue-500'
                        : 'bg-violet-500',
                    )}
                  />
                  {action.action_type === 'demand_signal'
                    ? action.demand_signal_type === 'order'
                      ? 'New Order'
                      : 'Forecast Change'
                    : 'Directive'}
                </span>
              ))}
            </div>
          </div>
        ),
      });
    }

    // Feasibility / what-if or rephrased prompt
    if (analysisResult.is_complete) {
      // Show feasibility check
      if (analysisResult.feasibility) {
        const feas = analysisResult.feasibility;
        const canFulfill = feas.can_fulfill;
        messages.push({
          role: 'system',
          key: 'compound-feasibility',
          content: (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                {canFulfill ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : (
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                )}
                <span className="font-medium text-foreground">
                  {canFulfill
                    ? `Can fulfill ${feas.fill_pct || '100'}%`
                    : `Short ${feas.shortage || 'some'} units`}
                </span>
              </div>
              {feas.details && (
                <p className="text-xs text-muted-foreground">{feas.details}</p>
              )}
            </div>
          ),
        });
      }

      // Directive activation question
      if (analysisResult.has_directive) {
        messages.push({
          role: 'system',
          key: 'compound-directive-ask',
          content: (
            <div>
              <p className="text-sm text-foreground mb-3">
                Should I also activate the directive?
              </p>
              <div className="flex flex-col gap-2">
                <button
                  onClick={onSubmitCompound}
                  disabled={submitting}
                  className="w-full px-3 py-1.5 rounded-full text-xs font-medium bg-violet-500 text-white hover:bg-violet-600 transition-colors disabled:opacity-50"
                >
                  Compare strategies
                </button>
                <div className="flex gap-2">
                  <button
                    onClick={onActivateDirective}
                    disabled={submitting}
                    className="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    Yes, activate directly
                  </button>
                  <button
                    onClick={onSkipDirective}
                    disabled={submitting}
                    className="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    No, just create order
                  </button>
                </div>
              </div>
            </div>
          ),
        });
      }
    }
  }

  // ─── REPHRASED PROMPT (for directive or compound with gaps) ────────────────
  if (
    rephrasedPrompt &&
    intent !== 'question' &&
    intent !== 'unknown' &&
    !analysisResult?.clarification_needed &&
    !(intent === 'scenario_question' && analysisResult?.answer)
  ) {
    // Build the enriched prompt display with color-coded additions
    // Original user text stays white, Azirella additions are purple,
    // ? placeholders are large, bold, and red
    const enrichedDisplay = (() => {
      const text = rephrasedPrompt || '';
      const original = userPrompt || '';

      // Split enriched text into segments: original text vs added text vs placeholders
      const parts = [];
      let remaining = text;

      // Find ? placeholders and mark them
      const segments = remaining.split(/(\?)/g);
      segments.forEach((seg, i) => {
        if (seg === '?') {
          parts.push(
            <span key={`q${i}`} className="text-red-500 text-xl font-black mx-0.5 animate-pulse">?</span>
          );
        } else if (seg.trim()) {
          // Check if this segment was in the original text
          const isOriginal = original.toLowerCase().includes(seg.trim().toLowerCase().substring(0, 15));
          parts.push(
            <span
              key={`s${i}`}
              className={isOriginal ? 'text-foreground' : 'text-violet-500 font-medium'}
            >
              {seg}
            </span>
          );
        }
      });

      return parts;
    })();

    messages.push({
      role: 'system',
      key: 'rephrased',
      content: (
        <div>
          <div className="font-medium text-foreground mb-1.5 flex items-center gap-2">
            <span>Azirella understood this as:</span>
          </div>

          {/* Rich prompt display — color-coded */}
          <div className="rounded-md border border-violet-200 bg-violet-50/30 px-3 py-2.5 text-sm leading-relaxed mb-2">
            {enrichedDisplay}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground mb-2">
            <span>Your words</span>
            <span className="text-violet-500 font-medium">Added context</span>
            <span className="text-red-500 font-bold text-sm">?</span>
            <span>Needs your input</span>
          </div>

          {/* Editable fallback textarea (collapsed by default) */}
          <details className="mb-2">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              Edit as text
            </summary>
            <textarea
              value={rephrasedPrompt}
              onChange={(e) => onRephrasedChange?.(e.target.value)}
              rows={3}
              className={cn(
                'w-full mt-1 rounded-md border border-border bg-background px-3 py-2 text-sm',
                'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                'font-medium leading-relaxed',
              )}
            />
          </details>

          <div className="flex items-center justify-between pt-2 border-t border-border">
            <span className="text-xs text-muted-foreground">
              {(rephrasedPrompt || '').includes('?')
                ? 'Replace the ? marks, then submit'
                : 'Looks good — submit to execute'}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  onRephrasedChange?.('');
                  // Reset — user can start over
                }}
                className="px-2.5 py-1.5 rounded-full text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={onSubmitRephrased}
                disabled={submitting}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all',
                  !submitting
                    ? 'bg-violet-500 text-white hover:bg-violet-600'
                    : 'bg-muted text-muted-foreground cursor-not-allowed',
                )}
              >
                {submitting ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3 w-3" />
                )}
                Submit
              </button>
            </div>
          </div>
        </div>
      ),
    });
  }

  // ─── FIELD-BY-FIELD CLARIFICATION (fallback when no rephrased prompt) ─────
  const missingFields = analysisResult?.missing_fields || [];
  if (
    !rephrasedPrompt &&
    missingFields.length > 0 &&
    intent !== 'question' &&
    intent !== 'unknown' &&
    !analysisResult?.clarification_needed &&
    !(intent === 'scenario_question' && analysisResult?.answer)
  ) {
    const answeredCount = missingFields.filter(
      (m) => clarifications?.[m.field]?.trim?.(),
    ).length;
    const totalMissing = missingFields.length;
    const allAnswered = answeredCount === totalMissing && totalMissing > 0;

    messages.push({
      role: 'system',
      key: 'clarification-fields',
      content: (
        <div>
          <div className="font-medium text-foreground mb-1.5">
            A few clarifying questions
          </div>

          {/* Parsed context */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
            <span className="truncate italic">"{userPrompt}"</span>
            <ChevronRight className="h-3 w-3 flex-shrink-0" />
            <span className="capitalize">
              {analysisResult.target_layer} layer
            </span>
            {analysisResult.confidence > 0 && (
              <span className="ml-1">
                ({Math.round(analysisResult.confidence * 100)}%)
              </span>
            )}
          </div>

          {/* Missing fields */}
          <div className="space-y-2.5">
            {missingFields.map((mf) => (
              <div key={mf.field}>
                <label className="block text-xs font-medium text-foreground mb-1">
                  {mf.question}
                </label>
                {mf.type === 'select' && mf.options?.length > 0 ? (
                  <select
                    value={clarifications?.[mf.field] || ''}
                    onChange={(e) =>
                      onClarificationAnswer?.(mf.field, e.target.value)
                    }
                    className={cn(
                      'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                      'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                    )}
                  >
                    <option value="">Select...</option>
                    {mf.options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : mf.type === 'number' ? (
                  <input
                    type="number"
                    value={clarifications?.[mf.field] || ''}
                    onChange={(e) =>
                      onClarificationAnswer?.(mf.field, e.target.value)
                    }
                    placeholder="e.g. 10"
                    className={cn(
                      'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                      'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                    )}
                  />
                ) : (
                  <input
                    type="text"
                    value={clarifications?.[mf.field] || ''}
                    onChange={(e) =>
                      onClarificationAnswer?.(mf.field, e.target.value)
                    }
                    placeholder="Type your answer..."
                    className={cn(
                      'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                      'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                    )}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Submit button */}
          <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-border">
            <span className="text-xs text-muted-foreground">
              {answeredCount} of {totalMissing} answered
            </span>
            <button
              onClick={onClarificationSubmit}
              disabled={!allAnswered || submitting}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all',
                allAnswered && !submitting
                  ? 'bg-violet-500 text-white hover:bg-violet-600'
                  : 'bg-muted text-muted-foreground cursor-not-allowed',
              )}
            >
              {submitting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3 w-3" />
              )}
              {intent?.startsWith('scenario') ? 'Run scenario' : 'Submit directive'}
            </button>
          </div>
        </div>
      ),
    });
  }

  // ─── STREAMING PROGRESS (compound SSE) ────────────────────────────────────
  if (isStreaming && streamMessages && streamMessages.length > 0) {
    const lastMsg = streamMessages[streamMessages.length - 1];
    const isDone = lastMsg?.type === 'complete' || lastMsg?.type === 'error';

    messages.push({
      role: 'system',
      key: 'streaming',
      content: (
        <div>
          <div className="font-medium text-foreground mb-2">Processing...</div>
          <div className="space-y-1 text-xs">
            {streamMessages.map((msg, i) => {
              // ── baseline_result: fulfillment summary box ──
              if (msg.type === 'baseline_result') {
                return (
                  <div
                    key={i}
                    className={cn(
                      'p-2.5 rounded-lg text-xs mt-1',
                      msg.can_fulfill
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
                        : 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
                    )}
                  >
                    <div className="font-semibold">
                      {msg.can_fulfill ? 'Can fulfill' : `Shortfall: ${msg.shortage} units`}
                    </div>
                    <div>
                      Promised: {msg.promised} of {msg.requested} ({msg.fill_rate_pct}%)
                    </div>
                  </div>
                );
              }

              // ── strategies_ready: strategy option cards ──
              if (msg.type === 'strategies_ready') {
                return (
                  <div key={i} className="grid gap-2 mt-2">
                    {msg.strategies?.map((s, si) => (
                      <div key={si} className="border border-border rounded-lg p-2.5 text-xs">
                        <div className="font-semibold text-foreground">{s.name}</div>
                        <div className="text-muted-foreground mt-0.5">{s.description}</div>
                      </div>
                    ))}
                  </div>
                );
              }

              // ── strategy_eval: per-strategy evaluation progress ──
              if (msg.type === 'strategy_eval') {
                return (
                  <div key={i} className="flex items-center gap-2 py-0.5">
                    {msg.status === 'evaluating' ? (
                      <Loader2 className="h-3 w-3 animate-spin text-violet-500 flex-shrink-0" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3 text-emerald-500 flex-shrink-0" />
                    )}
                    <span className={cn(
                      'text-foreground',
                      msg.status === 'complete' && 'font-medium',
                    )}>
                      {msg.strategy_name || msg.message}
                    </span>
                    {msg.status === 'complete' && msg.scorecard?.fill_rate_pct != null && (
                      <span className="text-muted-foreground ml-auto">
                        {msg.scorecard.fill_rate_pct}% fill
                      </span>
                    )}
                  </div>
                );
              }

              // ── comparison_ready: full comparison table ──
              if (msg.type === 'comparison_ready') {
                const { scenarios = [], recommendation_index = 0 } = msg;
                return (
                  <div key={i} className="overflow-x-auto mt-2">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-1.5 px-2 font-medium">Metric</th>
                          {scenarios.map((s, si) => (
                            <th key={si} className="text-center py-1.5 px-2 font-medium">
                              {s.name} {si === recommendation_index && '\u2605'}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {/* Fill Rate */}
                        <tr className="border-b border-border/50">
                          <td className="py-1.5 px-2 text-muted-foreground">Fill Rate</td>
                          {scenarios.map((s, si) => {
                            const val = s.scorecard?.fill_rate_pct ?? '\u2014';
                            const isBest = si === recommendation_index;
                            return (
                              <td key={si} className={cn('text-center py-1.5 px-2', isBest && 'text-emerald-600 font-semibold')}>
                                {val}%
                              </td>
                            );
                          })}
                        </tr>
                        {/* Additional Cost */}
                        <tr className="border-b border-border/50">
                          <td className="py-1.5 px-2 text-muted-foreground">Additional Cost</td>
                          {scenarios.map((s, si) => (
                            <td key={si} className="text-center py-1.5 px-2">
                              {s.estimated_additional_cost ? `$${s.estimated_additional_cost.toLocaleString()}` : '$0'}
                            </td>
                          ))}
                        </tr>
                        {/* Customers Affected */}
                        <tr className="border-b border-border/50">
                          <td className="py-1.5 px-2 text-muted-foreground">Customers Affected</td>
                          {scenarios.map((s, si) => (
                            <td key={si} className="text-center py-1.5 px-2">
                              {s.affected_customers?.length ?? 0}
                            </td>
                          ))}
                        </tr>
                        {/* Net Benefit */}
                        <tr>
                          <td className="py-1.5 px-2 font-medium">Net Benefit</td>
                          {scenarios.map((s, si) => {
                            const val = s.scorecard?.net_benefit ?? 0;
                            const isBest = si === recommendation_index;
                            return (
                              <td key={si} className={cn('text-center py-1.5 px-2 font-semibold', isBest && 'text-emerald-600')}>
                                {val.toFixed(2)}
                              </td>
                            );
                          })}
                        </tr>
                      </tbody>
                    </table>

                    {/* Recommendation */}
                    <div className="mt-3 flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">Recommended:</span>
                      <span className="text-xs font-semibold text-emerald-600">
                        {scenarios[recommendation_index]?.name} {'\u2605'}
                      </span>
                    </div>

                    {/* AIIO: Auto-selected notice — user overrides via Decision Stream */}
                    <div className="mt-2 px-2.5 py-2 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700">
                      <span className="font-semibold">Auto-selected:</span>{' '}
                      {scenarios[recommendation_index]?.name} (best trade-off).
                      Review in the Decision Stream to inspect reasoning or override.
                    </div>
                  </div>
                );
              }

              // ── action_executed: individual strategy action applied ──
              if (msg.type === 'action_executed') {
                return (
                  <div key={i} className="flex items-start gap-2 font-mono">
                    <span className="text-muted-foreground flex-shrink-0">{'\u251C\u2500\u2500'}</span>
                    <span className={cn(
                      'text-xs',
                      msg.success ? 'text-emerald-600' : 'text-red-500',
                    )}>
                      {msg.success ? '\u2714' : '\u2718'} {msg.message}
                    </span>
                  </div>
                );
              }

              // ── auto_promoted: AIIO decision applied ──
              if (msg.type === 'auto_promoted') {
                return (
                  <div key={i} className="p-2.5 rounded-lg bg-violet-50 border border-violet-200 text-xs mt-1">
                    <div className="font-semibold text-violet-700">
                      {'\u2714'} {msg.selected_strategy} applied
                    </div>
                    <div className="text-violet-600 mt-1">{msg.message}</div>
                  </div>
                );
              }

              // ── Default: tree-prefix rendering ──
              return (
                <div key={i} className="flex items-start gap-2 font-mono">
                  <span className="text-muted-foreground flex-shrink-0">
                    {msg.type === 'complete'
                      ? '\u2514\u2500\u2500'
                      : msg.type === 'error'
                        ? '\u2514\u2500\u2500 !'
                        : '\u251C\u2500\u2500'}
                  </span>
                  <span
                    className={cn(
                      msg.type === 'error'
                        ? 'text-destructive'
                        : msg.type === 'complete'
                          ? 'text-emerald-600 font-semibold'
                          : msg.type === 'action_complete'
                            ? 'text-blue-600'
                            : 'text-foreground',
                    )}
                  >
                    {msg.message}
                  </span>
                </div>
              );
            })}
            {!isDone && (
              <div className="flex items-center gap-2 text-muted-foreground font-mono">
                <span>{'\u2502'}  </span>
                <Loader2 className="h-3 w-3 animate-spin" />
              </div>
            )}
          </div>
        </div>
      ),
    });
  }

  // ─── DIRECTIVE RESULT (final feedback) ────────────────────────────────────
  if (directiveResult) {
    // Build a human-readable summary
    const intent = directiveResult.parsed_intent || 'directive';
    const isApplied = directiveResult.status === 'APPLIED';
    const actions = directiveResult.routed_actions || [];
    const scenarioAction = actions.find(a => a.action === 'scenario_event_injected');
    const trmActions = actions.filter(a => a.layer || a.trm_type);

    let summaryText = '';
    const scenarioAnswer = directiveResult._scenario_answer;
    const eventSummary = directiveResult._event_summary || scenarioAction?.summary;

    if (eventSummary) {
      summaryText = eventSummary;
    } else if (scenarioAction) {
      summaryText = scenarioAction.summary || `Scenario event injected: ${scenarioAction.event_type}`;
    } else if (trmActions.length > 0) {
      const trms = trmActions.map(a => (a.trm_type || a.layer || '').replace(/_/g, ' ')).join(', ');
      summaryText = `Routed to ${trmActions.length} agent${trmActions.length > 1 ? 's' : ''}: ${trms}`;
    } else if (isApplied) {
      summaryText = `${(directiveResult.directive_type || 'directive').replace(/_/g, ' ')} applied to ${directiveResult.target_layer || 'operational'} layer`;
    } else {
      summaryText = 'Directive recorded';
    }

    messages.push({
      role: 'system',
      key: 'directive-result',
      content: (
        <div>
          {/* Status badge */}
          <div className="flex items-center gap-2 mb-2">
            <span className={cn(
              'px-2 py-0.5 rounded-full text-xs font-medium',
              isApplied ? 'bg-emerald-500/10 text-emerald-600' : 'bg-blue-500/10 text-blue-600',
            )}>
              {isApplied ? 'Applied' : directiveResult.status}
            </span>
            <span className="text-xs text-muted-foreground">
              {Math.round(directiveResult.parser_confidence * 100)}% confidence
            </span>
          </div>

          {/* Human-readable summary */}
          <p className="text-sm font-medium">{summaryText}</p>

          {/* Scenario question answer */}
          {scenarioAnswer && (
            <div className="mt-2 text-xs text-foreground bg-muted/50 rounded-md px-3 py-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
              {typeof scenarioAnswer === 'string' && scenarioAnswer.length > 300
                ? scenarioAnswer.slice(0, 300) + '…'
                : scenarioAnswer}
            </div>
          )}

          {/* Fulfillment indicator for scenario questions */}
          {directiveResult._can_fulfill != null && (
            <div className={cn(
              'mt-1.5 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium',
              directiveResult._can_fulfill
                ? 'bg-emerald-500/10 text-emerald-600'
                : 'bg-red-500/10 text-red-600',
            )}>
              {directiveResult._can_fulfill ? '✓ Can fulfill' : '✗ Cannot fulfill'}
            </div>
          )}

          {/* Action details (for non-scenario directives) */}
          {trmActions.length > 0 && !scenarioAction && !eventSummary && (
            <div className="mt-2 space-y-1">
              {trmActions.slice(0, 5).map((a, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400 flex-shrink-0" />
                  <span>{(a.trm_type || a.layer || '').replace(/_/g, ' ')}</span>
                  {a.action && <span className="text-[10px]">— {a.action}</span>}
                </div>
              ))}
            </div>
          )}

          {/* Navigation links */}
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={() => onNavigate('/decision-stream', { fromAzirella: true })}
              className="flex items-center gap-1.5 text-xs font-medium text-violet-600 hover:text-violet-700 transition-colors"
            >
              <span>→</span>
              Decision Stream
            </button>
            {(scenarioAction || directiveResult._target_config_id) && (
              <button
                onClick={() => onNavigate('/scenario-events', {
                  configId: directiveResult._target_config_id || scenarioAction?.target_config_id,
                  fromAzirella: true,
                })}
                className="flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
              >
                <span>→</span>
                Scenario Events
              </button>
            )}
          </div>
        </div>
      ),
    });
  }

  return messages;
}

// ─── AzirellaPopup Component ────────────────────────────────────────────────────
const AzirellaPopup = ({
  open,
  onClose,
  userPrompt,
  analysisResult,
  streamMessages,
  isStreaming,
  directiveResult,
  rephrasedPrompt,
  onRephrasedChange,
  onSubmitRephrased,
  onSubmitCompound,
  onActivateDirective,
  onSkipDirective,
  onNavigate,
  onPromoteStrategy,
  submitting,
  clarifications,
  onClarificationAnswer,
  onClarificationSubmit,
  onRequestClarificationVoice,
}) => {
  const scrollRef = useRef(null);
  const [held, setHeld] = useState(false);
  const autoDismissTimer = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [analysisResult, streamMessages, directiveResult, rephrasedPrompt, isStreaming]);

  // Build the conversation thread
  const messages = useMemo(
    () =>
      buildMessages({
        userPrompt,
        analysisResult,
        streamMessages,
        isStreaming,
        directiveResult,
        rephrasedPrompt,
        onRephrasedChange,
        onSubmitRephrased,
        onSubmitCompound,
        onActivateDirective,
        onSkipDirective,
        onNavigate,
        onPromoteStrategy,
        submitting,
        clarifications,
        onClarificationAnswer,
        onClarificationSubmit,
      }),
    // Intentionally include callbacks so interactive content re-renders correctly
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      userPrompt,
      analysisResult,
      streamMessages,
      isStreaming,
      directiveResult,
      rephrasedPrompt,
      submitting,
      clarifications,
    ],
  );

  // Determine whether Done should be shown (only when interaction is "complete")
  const isComplete =
    // Question answered
    analysisResult?.intent === 'question' ||
    // Scenario question answered
    (analysisResult?.intent === 'scenario_question' && analysisResult?.answer) ||
    // Directive submitted
    !!directiveResult ||
    // Streaming finished
    (streamMessages?.length > 0 &&
      (streamMessages[streamMessages.length - 1]?.type === 'complete' ||
        streamMessages[streamMessages.length - 1]?.type === 'error'));

  // Does the LLM need more info? (clarification fields present, or ambiguous/unknown)
  const needsClarification =
    (analysisResult?.missing_fields?.length > 0 && !directiveResult) ||
    analysisResult?.intent === 'unknown' ||
    analysisResult?.clarification_needed ||
    (!!rephrasedPrompt && !directiveResult);

  // ── Auto-dismiss after 10s when complete (unless held or needs clarification) ──
  useEffect(() => {
    clearTimeout(autoDismissTimer.current);
    if (open && isComplete && !held && !needsClarification) {
      autoDismissTimer.current = setTimeout(() => {
        onClose?.();
      }, 10000);
    }
    return () => clearTimeout(autoDismissTimer.current);
  }, [open, isComplete, held, needsClarification, onClose]);

  // Reset hold state when popup reopens with new content
  useEffect(() => {
    if (open) setHeld(false);
  }, [userPrompt, open]);

  // ── Voice prompt when clarification is needed ──
  const hasFiredVoiceRef = useRef(null);
  useEffect(() => {
    if (needsClarification && open && hasFiredVoiceRef.current !== userPrompt) {
      hasFiredVoiceRef.current = userPrompt;
      onRequestClarificationVoice?.();
    }
  }, [needsClarification, open, userPrompt, onRequestClarificationVoice]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop — semi-transparent, does NOT dismiss on click */}
      <div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]" />

      {/* Popup container */}
      <div
        className={cn(
          'fixed top-20 left-1/2 -translate-x-1/2 z-50',
          'w-full max-w-xl mx-4',
          'bg-popover border border-border rounded-xl shadow-2xl',
          'flex flex-col',
          'max-h-[70vh]',
          'animate-in fade-in slide-in-from-top-2 duration-200',
        )}
      >
        {/* ── Header (sticky) ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <img src="/Azirella_logo.png" alt="" className="h-7 w-7 rounded-full object-cover object-[center_40%] flex-shrink-0" aria-hidden="true" />
            <span className="font-semibold text-sm text-foreground">
              Azirella
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Message thread (scrollable) ─────────────────────────────────── */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-4 py-4 min-h-0"
        >
          {messages.map((msg) => (
            <MessageBubble key={msg.key} role={msg.role}>
              {typeof msg.content === 'string' ? msg.content : msg.content}
            </MessageBubble>
          ))}
        </div>

        {/* ── Footer (sticky) ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            {submitting && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>Processing...</span>
              </div>
            )}
            {/* Auto-dismiss indicator + Hold toggle */}
            {isComplete && !needsClarification && (
              <button
                onClick={() => setHeld(h => !h)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all',
                  held
                    ? 'bg-amber-500/10 text-amber-600 border border-amber-300/50'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent border border-transparent',
                )}
                title={held ? 'Pinned — click to unpin and auto-dismiss' : 'Pin to keep visible'}
              >
                {held ? <Pin className="h-3 w-3" /> : <PinOff className="h-3 w-3" />}
                {held ? 'Pinned' : 'Closes in 10s'}
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className={cn(
              'px-4 py-1.5 rounded-full text-xs font-medium transition-all',
              isComplete
                ? 'bg-violet-500 text-white hover:bg-violet-600'
                : 'border border-border text-muted-foreground hover:text-foreground hover:bg-accent',
            )}
          >
            Done
          </button>
        </div>
      </div>
    </>
  );
};

export default AzirellaPopup;
