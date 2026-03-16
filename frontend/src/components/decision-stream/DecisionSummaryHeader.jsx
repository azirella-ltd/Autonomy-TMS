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
      // Auto-actioned = low urgency + high confidence (agent acted autonomously)
      const isAuto = (d.urgency_score || 0) < 0.3 && (d.likelihood_score || 0) > 0.7;
      if (isAuto) counts[key].automated++;
    });
    // Sort by urgency tier order, then likelihood
    const urgencyOrder = { Critical: 0, High: 1, Medium: 2, Low: 3, Routine: 4 };
    return Object.values(counts).sort((a, b) =>
      (urgencyOrder[a.urgency] ?? 9) - (urgencyOrder[b.urgency] ?? 9)
      || a.likelihood.localeCompare(b.likelihood)
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
  const needsAttention = decisions.filter(d =>
    d.urgency === 'Critical' || d.urgency === 'High'
  ).length;

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

          {/* Show All toggle */}
          <button
            onClick={onToggleShowAll}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
              showAll
                ? 'bg-violet-100 text-violet-700 hover:bg-violet-200'
                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            )}
          >
            {showAll ? (
              <><Eye className="h-3 w-3" /> Show All</>
            ) : (
              <><EyeOff className="h-3 w-3" /> Needs Attention</>
            )}
          </button>
        </div>
      </div>

      {/* Urgency × Likelihood list + Type breakdown */}
      <div className="flex gap-4 flex-wrap">
        {/* Compact combo list — only shows combos that exist */}
        <div className="border rounded-lg overflow-hidden flex-1 min-w-[320px]">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-muted/30">
                <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Urgency</th>
                <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Likelihood</th>
                <th className="px-3 py-1.5 text-center font-medium text-muted-foreground">Count</th>
                <th className="px-3 py-1.5 text-center font-medium text-muted-foreground">Automated</th>
              </tr>
            </thead>
            <tbody>
              {combos.map(({ urgency, likelihood, count, automated }, i) => {
                const tier = URGENCY_TIERS.find(t => t.key === urgency) || URGENCY_TIERS[2];
                return (
                  <tr key={i} className={cn('border-t', tier.bgLight)}>
                    <td className="px-3 py-1.5">
                      <div className="flex items-center gap-1.5">
                        <div className={cn('h-2 w-2 rounded-full', tier.color)} />
                        <span className={cn('font-medium', tier.textColor)}>{urgency}</span>
                      </div>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{likelihood}</td>
                    <td className="px-3 py-1.5 text-center tabular-nums font-semibold">{count}</td>
                    <td className="px-3 py-1.5 text-center tabular-nums">
                      {automated > 0 ? (
                        <span className="text-green-600 font-medium">{automated}</span>
                      ) : (
                        <span className="text-muted-foreground/30">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Type breakdown */}
        <div className="min-w-[180px]">
          <div className="text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
            By Type
          </div>
          <div className="space-y-1">
            {typeCounts.map(([label, count]) => (
              <div key={label} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{label}</span>
                <span className="tabular-nums font-semibold">{count}</span>
              </div>
            ))}
          </div>
          {needsAttention > 0 && (
            <div className="mt-2 pt-2 border-t text-xs">
              <span className="text-red-600 font-semibold">{needsAttention}</span>
              <span className="text-muted-foreground ml-1">need human judgment</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DecisionSummaryHeader;
