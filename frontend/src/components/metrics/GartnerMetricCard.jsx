/**
 * GartnerMetricCard — Reusable KPI card for Gartner hierarchy metrics
 *
 * Shows: tier badge, metric name/value/unit, target with progress bar,
 * trend indicator, benchmark reference, optional TRM agent attribution.
 */

import React from 'react';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Bot,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { Card, CardContent, Badge, Progress } from '../common';

const TIER_BADGES = {
  tier1: { label: 'ASSESS', className: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' },
  tier2: { label: 'DIAGNOSE', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  tier3: { label: 'CORRECT', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  tier4: { label: 'AI', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
};

const STATUS_STYLES = {
  success: 'border-l-green-500',
  warning: 'border-l-amber-500',
  danger: 'border-l-red-500',
};

const GartnerMetricCard = ({
  label,
  value,
  unit,
  target,
  trend,
  benchmark,
  status = 'success',
  tier,
  agent,
  scorCode,
  lowerIsBetter = false,
  compact = false,
  ciLower,
  ciUpper,
  n,
}) => {
  const tierBadge = tier ? TIER_BADGES[tier] : null;
  const trendPositive = lowerIsBetter ? trend < 0 : trend > 0;
  const trendNegative = lowerIsBetter ? trend > 0 : trend < 0;

  return (
    <Card className={cn('border-l-4', STATUS_STYLES[status] || 'border-l-gray-300')}>
      <CardContent className={compact ? 'p-3' : 'p-4'}>
        {/* Header row: tier badge + SCOR code */}
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1.5">
            {tierBadge && (
              <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded', tierBadge.className)}>
                {tierBadge.label}
              </span>
            )}
            {scorCode && (
              <span className="text-[10px] text-muted-foreground font-mono">{scorCode}</span>
            )}
          </div>
          {agent && (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <Bot className="h-3 w-3" />
              {agent}
            </span>
          )}
        </div>

        {/* Metric name */}
        <p className="text-xs font-medium text-muted-foreground">{label}</p>

        {/* Value + trend */}
        <div className="mt-1 flex items-baseline gap-2">
          <span className={cn('font-bold', compact ? 'text-xl' : 'text-2xl')}>
            {typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}
          </span>
          {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
          {trend !== undefined && trend !== null && (
            <span className={cn(
              'flex items-center text-xs font-medium',
              trendPositive && 'text-green-600',
              trendNegative && 'text-red-600',
              !trendPositive && !trendNegative && 'text-muted-foreground',
            )}>
              {trendPositive && <TrendingUp className="h-3 w-3 mr-0.5" />}
              {trendNegative && <TrendingDown className="h-3 w-3 mr-0.5" />}
              {!trendPositive && !trendNegative && <Minus className="h-3 w-3 mr-0.5" />}
              {trend > 0 ? '+' : ''}{typeof trend === 'number' ? trend.toFixed(1) : trend}
            </span>
          )}
        </div>

        {/* Confidence interval */}
        {ciLower != null && ciUpper != null && (
          <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground" title={`95% CI (n=${n || '?'})`}>
            <span className="font-mono">[{ciLower.toLocaleString(undefined, {maximumFractionDigits: 1})} – {ciUpper.toLocaleString(undefined, {maximumFractionDigits: 1})}]</span>
            {n && <span className="opacity-60">n={n}</span>}
          </div>
        )}

        {/* Target + progress */}
        {target !== undefined && target !== null && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Target: {target}{unit}</span>
              {benchmark && <span className="text-[10px] text-muted-foreground" title="Industry benchmark range">Ref: {benchmark}</span>}
            </div>
            <Progress
              value={Math.min(
                lowerIsBetter
                  ? (target / Math.max(value, 0.01)) * 100
                  : (value / Math.max(target, 0.01)) * 100,
                100
              )}
              className={cn(
                'h-1.5',
                status === 'success' && '[&>div]:bg-green-500',
                status === 'warning' && '[&>div]:bg-amber-500',
                status === 'danger' && '[&>div]:bg-red-500',
              )}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default GartnerMetricCard;
