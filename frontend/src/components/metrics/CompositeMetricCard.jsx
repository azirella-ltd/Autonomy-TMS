/**
 * CompositeMetricCard — For Tier 2 metrics that decompose into sub-components
 *
 * Examples:
 *   POF = OTD x IF x Damage-Free x Documentation
 *   C2C = DIO + DSO - DPO
 *   OFCT = Source + Make + Deliver
 */

import React from 'react';
import {
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { Card, CardContent, Progress } from '../common';

const STATUS_BORDER = {
  success: 'border-l-green-500',
  warning: 'border-l-amber-500',
  danger: 'border-l-red-500',
};

const CompositeMetricCard = ({
  label,
  value,
  unit,
  target,
  trend,
  benchmark,
  status = 'warning',
  scorCode,
  formula,
  components,
  lowerIsBetter = false,
  ciLower,
  ciUpper,
  n,
}) => {
  const trendGood = lowerIsBetter ? trend < 0 : trend > 0;

  return (
    <Card className={cn('border-l-4', STATUS_BORDER[status] || 'border-l-gray-300')}>
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
            DIAGNOSE
          </span>
          {scorCode && (
            <span className="text-[10px] text-muted-foreground font-mono">{scorCode}</span>
          )}
        </div>

        <p className="text-xs font-medium text-muted-foreground">{label}</p>

        {/* Composite value */}
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-bold">
            {typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}
          </span>
          <span className="text-sm text-muted-foreground">{unit}</span>
          {trend !== undefined && (
            <span className={cn(
              'flex items-center text-xs font-medium',
              trendGood ? 'text-green-600' : 'text-red-600',
            )}>
              {trendGood ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
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

        {/* Target + benchmark */}
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span>Target: {target} {unit}</span>
          {benchmark && <span className="text-[10px]">{benchmark}</span>}
        </div>

        {/* Formula */}
        {formula && (
          <p className="text-[10px] text-muted-foreground mt-1 font-mono">{formula}</p>
        )}

        {/* Sub-components */}
        {components && (
          <div className="mt-3 space-y-2 pt-2 border-t">
            {Object.entries(components).map(([key, comp]) => {
              const pct = comp.target
                ? Math.min((comp.value / comp.target) * 100, 100)
                : 50;
              const compStatus = comp.target
                ? (lowerIsBetter
                    ? comp.value <= comp.target
                    : comp.value >= comp.target)
                : true;

              return (
                <div key={key}>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{comp.label}</span>
                    <span className="font-medium">
                      {comp.value} {comp.unit}
                    </span>
                  </div>
                  <Progress
                    value={lowerIsBetter ? Math.min((comp.target / Math.max(comp.value, 0.01)) * 100, 100) : pct}
                    className={cn(
                      'h-1 mt-0.5',
                      compStatus ? '[&>div]:bg-green-500' : '[&>div]:bg-amber-500',
                    )}
                  />
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default CompositeMetricCard;
