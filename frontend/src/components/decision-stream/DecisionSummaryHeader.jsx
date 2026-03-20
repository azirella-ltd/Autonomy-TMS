/**
 * DecisionSummaryHeader — Urgency × Likelihood matrix and filtering controls.
 *
 * Shows a compact summary table of decisions by urgency level and type,
 * a "surfaced to you" count reflecting user scope, and a Show All toggle
 * to switch between human-attention-required vs all agent decisions.
 */
import { useState, useMemo } from 'react';
import { Eye, EyeOff, Filter, User, MapPin } from 'lucide-react';
import { cn } from '../../lib/utils/cn';

// Urgency tiers matching backend _prioritize_decisions
const URGENCY_TIERS = [
  { key: 'Critical', color: 'bg-red-500', textColor: 'text-red-700', bgLight: 'bg-red-50' },
  { key: 'High', color: 'bg-orange-500', textColor: 'text-orange-700', bgLight: 'bg-orange-50' },
  { key: 'Medium', color: 'bg-yellow-500', textColor: 'text-yellow-700', bgLight: 'bg-yellow-50' },
  { key: 'Low', color: 'bg-blue-400', textColor: 'text-blue-700', bgLight: 'bg-blue-50' },
];

// Decision type labels
const TYPE_LABELS = {
  atp_executor: 'ATP',
  rebalancing: 'Rebalancing',
  po_creation: 'PO Creation',
  order_tracking: 'Order Exception',
  mo_execution: 'MO Execution',
  to_execution: 'TO Execution',
  quality: 'Quality',
  quality_disposition: 'Quality',
  maintenance: 'Maintenance',
  maintenance_scheduling: 'Maintenance',
  subcontracting: 'Subcontracting',
  forecast_adjustment: 'Forecast Adj.',
  inventory_buffer: 'Buffer Adj.',
};

const DecisionSummaryHeader = ({
  decisions = [],
  totalAgentDecisions = 0,
  showAll,
  onToggleShowAll,
  activeLevels,
  onToggleLevel,
  canFilterLevels = false,
  userScope,
}) => {
  // Build urgency × likelihood combo list (only combos that exist)
  const combos = useMemo(() => {
    const counts = {};
    decisions.forEach(d => {
      const u = d.urgency || 'Medium';
      const l = d.likelihood || 'Possible';
      const key = `${u}|${l}`;
      if (!counts[key]) counts[key] = { urgency: u, likelihood: l, count: 0, automated: 0 };
      counts[key].count++;
      if (d.auto_actioned) counts[key].automated++;
    });
    // Sort by urgency (highest first), then likelihood ascending (lowest first)
    const urgencyOrder = { Critical: 0, High: 1, Medium: 2, Low: 3, Routine: 4 };
    const likelihoodOrder = { Unlikely: 0, Possible: 1, Likely: 2, Certain: 3 };
    return Object.values(counts).sort((a, b) =>
      (urgencyOrder[a.urgency] ?? 9) - (urgencyOrder[b.urgency] ?? 9)
      || (likelihoodOrder[a.likelihood] ?? 9) - (likelihoodOrder[b.likelihood] ?? 9)
    );
  }, [decisions]);

  // Count by type
  const typeCounts = useMemo(() => {
    const counts = {};
    decisions.forEach(d => {
      const t = d.decision_type || 'unknown';
      const label = TYPE_LABELS[t] || t;
      counts[label] = (counts[label] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [decisions]);

  const surfacedCount = decisions.length;
  const needsAttention = decisions.filter(d => d.needs_attention !== false).length;
  const autoActioned = decisions.filter(d => d.auto_actioned).length;

  return (
    <div className="mb-4 space-y-3">
      {/* Summary row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-2xl font-bold tabular-nums">{surfacedCount}</span>
            <span className="text-sm text-muted-foreground ml-1.5">
              {showAll ? 'total decisions' : 'decisions requiring attention'}
            </span>
          </div>
          {!showAll && totalAgentDecisions > surfacedCount && (
            <span className="text-xs text-muted-foreground">
              of {totalAgentDecisions} total agent decisions
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* User scope indicator */}
          {userScope && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted/50 text-xs text-muted-foreground">
              {userScope.site ? (
                <>
                  <MapPin className="h-3 w-3" />
                  <span>{userScope.site}</span>
                </>
              ) : userScope.role ? (
                <>
                  <User className="h-3 w-3" />
                  <span>{userScope.role}</span>
                </>
              ) : (
                <>
                  <Filter className="h-3 w-3" />
                  <span>All decisions</span>
                </>
              )}
            </div>
          )}

          {/* View mode buttons */}
          <div className="flex rounded-lg border overflow-hidden">
            <button
              onClick={() => showAll && onToggleShowAll()}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors',
                !showAll
                  ? 'bg-red-50 text-red-700 border-r'
                  : 'bg-background text-muted-foreground hover:bg-muted/50 border-r'
              )}
            >
              <EyeOff className="h-3 w-3" />
              Needs Attention
            </button>
            <button
              onClick={() => !showAll && onToggleShowAll()}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors',
                showAll
                  ? 'bg-violet-50 text-violet-700'
                  : 'bg-background text-muted-foreground hover:bg-muted/50'
              )}
            >
              <Eye className="h-3 w-3" />
              Show All
            </button>
          </div>
        </div>
      </div>

      {/* Compact summary bar — urgency counts + levels inline */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Urgency badges */}
        <div className="flex items-center gap-2">
          {URGENCY_TIERS.map(tier => {
            const count = decisions.filter(d => (d.urgency || 'Medium') === tier.key).length;
            if (count === 0) return null;
            return (
              <div key={tier.key} className={cn('flex items-center gap-1 px-2 py-0.5 rounded-full text-xs', tier.bgLight)}>
                <div className={cn('h-1.5 w-1.5 rounded-full', tier.color)} />
                <span className={cn('font-medium', tier.textColor)}>{count}</span>
                <span className="text-muted-foreground">{tier.key}</span>
              </div>
            );
          })}
          {(() => {
            const routine = decisions.filter(d => (d.urgency || '') === 'Routine').length;
            return routine > 0 ? (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-50">
                <div className="h-1.5 w-1.5 rounded-full bg-gray-400" />
                <span className="font-medium text-gray-600">{routine}</span>
                <span className="text-muted-foreground">Routine</span>
              </div>
            ) : null;
          })()}
        </div>

        <span className="text-muted-foreground/30">|</span>

        {/* Level badges */}
        <div className="flex items-center gap-2">
          {(() => {
            const LEVELS = [
              { key: 'strategic', label: 'Strategic', color: 'text-purple-600', bg: 'bg-purple-50' },
              { key: 'tactical', label: 'Tactical', color: 'text-blue-600', bg: 'bg-blue-50' },
              { key: 'operational', label: 'Operational', color: 'text-amber-600', bg: 'bg-amber-50' },
              { key: 'execution', label: 'Execution', color: 'text-gray-600', bg: 'bg-gray-50' },
            ];
            return LEVELS.map(lvl => {
              const count = decisions.filter(d => (d.decision_level || 'execution') === lvl.key).length;
              if (count === 0) return null;
              const Tag = canFilterLevels ? 'button' : 'span';
              const isActive = !activeLevels || activeLevels.has(lvl.key);
              return (
                <Tag
                  key={lvl.key}
                  onClick={canFilterLevels ? () => onToggleLevel?.(lvl.key) : undefined}
                  className={cn(
                    'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-opacity',
                    lvl.bg,
                    canFilterLevels ? 'cursor-pointer hover:ring-1 hover:ring-inset hover:ring-current' : '',
                    activeLevels && !isActive ? 'opacity-30' : '',
                  )}
                >
                  <span className={cn('font-medium', lvl.color)}>{count}</span>
                  <span className={lvl.color}>{lvl.label}</span>
                </Tag>
              );
            });
          })()}
        </div>

        <span className="text-muted-foreground/30">|</span>

        {/* Action summary */}
        <div className="flex items-center gap-3 text-xs">
          {needsAttention > 0 && (
            <span><span className="text-red-600 font-semibold">{needsAttention}</span> <span className="text-muted-foreground">need you</span></span>
          )}
          {autoActioned > 0 && (
            <span><span className="text-green-600 font-semibold">{autoActioned}</span> <span className="text-muted-foreground">auto-actioned</span></span>
          )}
        </div>
      </div>

      {/* Old type/level columns removed — now inline badges above */}
    </div>
  );
};

export default DecisionSummaryHeader;
