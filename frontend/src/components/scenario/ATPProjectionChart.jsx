/**
 * ATP Projection Chart Component
 *
 * Phase 3: Full ATP/CTP Integration
 * Displays multi-period ATP projection with safety stock threshold,
 * color-coded zones, and detailed tooltips.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - gameId: Game ID
 * - playerId: Player ID
 * - currentRound: Current round number
 * - periods: Number of future periods to project (default 8)
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Alert,
  AlertTitle,
  AlertDescription,
  Spinner,
} from '../common';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';
import {
  AlertTriangle as WarningIcon,
  CheckCircle2 as CheckIcon,
  Info as InfoIcon,
} from 'lucide-react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const ATPProjectionChart = ({
  gameId,
  playerId,
  currentRound,
  periods = 8,
}) => {
  const [projection, setProjection] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [safetyStockThreshold, setSafetyStockThreshold] = useState(100);

  useEffect(() => {
    fetchATPProjection();
  }, [gameId, playerId, currentRound, periods]);

  const fetchATPProjection = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get(
        `/mixed-scenarios/${gameId}/atp-projection/${playerId}?periods=${periods}`
      );

      const projectionData = response.data;

      // Calculate safety stock from first period (or use default)
      if (projectionData.length > 0) {
        // Assume safety stock is 10% of starting inventory or 100 min
        const startingInv = projectionData[0].starting_inventory;
        setSafetyStockThreshold(Math.max(100, Math.floor(startingInv * 0.1)));
      }

      setProjection(projectionData);
    } catch (err) {
      console.error('Error fetching ATP projection:', err);
      setError(err.response?.data?.detail || 'Failed to fetch ATP projection');
    } finally {
      setLoading(false);
    }
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) {
      return null;
    }

    const data = payload[0].payload;

    return (
      <Card className="p-2 bg-white/95 dark:bg-card/95 shadow-lg border">
        <CardContent className="p-2">
          <h4 className="font-semibold text-sm mb-2">Round {data.period}</h4>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Starting Inventory:</span>
              <span className="font-semibold">{data.starting_inventory} units</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Scheduled Receipts:</span>
              <span className="font-semibold text-emerald-600">+{data.scheduled_receipts} units</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Forecasted Demand:</span>
              <span className="font-semibold text-red-600">-{data.forecasted_demand} units</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Planned Allocations:</span>
              <span className="font-semibold text-amber-600">-{data.planned_allocations} units</span>
            </div>
            <div className="flex justify-between gap-4 pt-1.5 border-t border-border">
              <span className="text-muted-foreground font-semibold">Ending ATP:</span>
              <span
                className={cn(
                  'font-semibold',
                  data.ending_atp >= safetyStockThreshold
                    ? 'text-emerald-600'
                    : data.ending_atp > 0
                    ? 'text-amber-600'
                    : 'text-red-600'
                )}
              >
                {data.ending_atp} units
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Cumulative ATP:</span>
              <span className="font-semibold">{data.cumulative_atp} units</span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  // Identify ATP breach periods
  const breachPeriods = projection.filter(p => p.ending_atp < safetyStockThreshold);

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="error">
        <WarningIcon className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!projection || projection.length === 0) {
    return (
      <Alert variant="info">
        <InfoIcon className="h-4 w-4" />
        <AlertDescription>No ATP projection data available</AlertDescription>
      </Alert>
    );
  }

  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">
              ATP Projection (Next {periods} Rounds)
            </h3>
            <div className="flex gap-2">
              {breachPeriods.length === 0 ? (
                <Badge variant="success" className="gap-1">
                  <CheckIcon className="h-3 w-3" />
                  Healthy
                </Badge>
              ) : (
                <Badge variant="warning" className="gap-1">
                  <WarningIcon className="h-3 w-3" />
                  {breachPeriods.length} Projected Shortfall{breachPeriods.length > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
          </div>

          {/* Chart */}
          <div className="w-full h-[400px]">
            <ResponsiveContainer>
              <ComposedChart
                data={projection}
                margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="period"
                  label={{ value: 'Round', position: 'insideBottom', offset: -10 }}
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  label={{ value: 'Units', angle: -90, position: 'insideLeft' }}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  wrapperStyle={{ fontSize: '12px' }}
                />

                {/* Safety stock threshold line */}
                <ReferenceLine
                  y={safetyStockThreshold}
                  stroke="#f59e0b"
                  strokeDasharray="5 5"
                  label={{
                    value: `Safety Stock (${safetyStockThreshold})`,
                    position: 'right',
                    fill: '#f59e0b',
                    fontSize: 11,
                  }}
                />

                {/* Zero line */}
                <ReferenceLine
                  y={0}
                  stroke="#ef4444"
                  strokeWidth={2}
                  label={{
                    value: 'Stockout',
                    position: 'right',
                    fill: '#ef4444',
                    fontSize: 11,
                  }}
                />

                {/* ATP area (green/yellow/red zones) */}
                <Area
                  type="monotone"
                  dataKey="ending_atp"
                  fill="rgba(34, 197, 94, 0.2)"
                  stroke="none"
                />

                {/* ATP line */}
                <Line
                  type="monotone"
                  dataKey="ending_atp"
                  stroke="hsl(var(--primary))"
                  strokeWidth={3}
                  dot={{ fill: 'hsl(var(--primary))', r: 5 }}
                  activeDot={{ r: 7 }}
                  name="Ending ATP"
                />

                {/* Forecasted demand line (dashed) */}
                <Line
                  type="monotone"
                  dataKey="forecasted_demand"
                  stroke="#9333ea"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: '#9333ea', r: 3 }}
                  name="Forecasted Demand"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Warning alerts for projected shortfalls */}
          {breachPeriods.length > 0 && (
            <Alert variant="warning">
              <WarningIcon className="h-4 w-4" />
              <AlertTitle>Projected ATP Shortfalls</AlertTitle>
              <AlertDescription>
                <p className="mb-2">
                  ATP is projected to fall below safety stock threshold in{' '}
                  <strong>
                    {breachPeriods.length} round{breachPeriods.length > 1 ? 's' : ''}
                  </strong>
                  :
                </p>
                <ul className="list-disc ml-4 space-y-1">
                  {breachPeriods.slice(0, 3).map((period) => (
                    <li key={period.period} className="text-xs">
                      <strong>Round {period.period}</strong>: ATP = {period.ending_atp} units
                      (below threshold by {safetyStockThreshold - period.ending_atp} units)
                    </li>
                  ))}
                  {breachPeriods.length > 3 && (
                    <li className="text-xs text-muted-foreground">
                      ... and {breachPeriods.length - 3} more
                    </li>
                  )}
                </ul>
                <p className="text-xs mt-2">
                  Consider expediting replenishment orders to prevent stockouts.
                </p>
              </AlertDescription>
            </Alert>
          )}

          {/* Legend explanation */}
          <div className="p-3 bg-muted/50 rounded-lg">
            <p className="text-xs text-muted-foreground">
              <strong className="text-emerald-600">Green zone</strong> (ATP ≥ Safety Stock): Healthy inventory
              <br />
              <strong className="text-amber-600">Yellow zone</strong> (0 &lt; ATP &lt; Safety Stock): Low inventory, expedite recommended
              <br />
              <strong className="text-red-600">Red zone</strong> (ATP ≤ 0): Stockout projected, urgent action required
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ATPProjectionChart;
