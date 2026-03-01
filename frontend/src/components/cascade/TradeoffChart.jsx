/**
 * Tradeoff Chart
 *
 * Scatter plot showing SupBP candidate methods on a Cost vs OTIF frontier.
 * Pareto frontier line highlighted. Hover shows method details.
 */
import React, { useMemo } from 'react';
import { Box, Paper, Typography, Chip } from '@mui/material';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ZAxis, Legend,
} from 'recharts';

const METHOD_COLORS = {
  REORDER_POINT_V1: '#1976d2',
  PERIODIC_REVIEW_V1: '#388e3c',
  MIN_COST_EOQ_V1: '#f57c00',
  SERVICE_MAXIMIZED_V1: '#c62828',
  PARAMETRIC_CFA_V1: '#7b1fa2',
  MRP_STANDARD_V1: '#00838f',
  SAFETY_STOCK_OPTIMIZED_V1: '#6d4c41',
  CUSTOMER_UPLOAD: '#455a64',
};

const METHOD_LABELS = {
  REORDER_POINT_V1: 'Reorder Point (R,Q)',
  PERIODIC_REVIEW_V1: 'Periodic Review (s,S)',
  MIN_COST_EOQ_V1: 'Min Cost EOQ',
  SERVICE_MAXIMIZED_V1: 'Service Maximized',
  PARAMETRIC_CFA_V1: 'Parametric CFA',
  MRP_STANDARD_V1: 'Standard MRP',
  SAFETY_STOCK_OPTIMIZED_V1: 'Safety Stock Optimized',
  CUSTOMER_UPLOAD: 'Customer Upload',
};

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <Paper sx={{ p: 1.5 }} elevation={3}>
      <Typography variant="subtitle2">{METHOD_LABELS[data.method] || data.method}</Typography>
      <Typography variant="body2">Cost: ${data.cost?.toLocaleString()}</Typography>
      <Typography variant="body2">OTIF: {(data.otif * 100).toFixed(1)}%</Typography>
      {data.dos != null && <Typography variant="body2">DOS: {data.dos.toFixed(1)}</Typography>}
      {data.orders != null && <Typography variant="body2">Orders: {data.orders}</Typography>}
    </Paper>
  );
};

const TradeoffChart = ({ candidates, tradeoffFrontier, selectedMethod, onSelect, height = 350 }) => {
  const chartData = useMemo(() => {
    if (!candidates?.length) return [];
    return candidates.map(c => ({
      method: c.method,
      cost: c.projected_cost || 0,
      otif: c.projected_otif || 0,
      dos: c.projected_dos,
      orders: c.orders?.length,
      label: METHOD_LABELS[c.method] || c.method,
      color: METHOD_COLORS[c.method] || '#666',
      isSelected: c.method === selectedMethod,
    }));
  }, [candidates, selectedMethod]);

  // Compute pareto frontier points
  const paretoPoints = useMemo(() => {
    if (tradeoffFrontier?.length) {
      return tradeoffFrontier.sort((a, b) => a.cost - b.cost);
    }
    // Compute from data: sort by cost, keep only those with increasing OTIF
    const sorted = [...chartData].sort((a, b) => a.cost - b.cost);
    const frontier = [];
    let maxOtif = -1;
    for (const pt of sorted) {
      if (pt.otif > maxOtif) {
        frontier.push(pt);
        maxOtif = pt.otif;
      }
    }
    return frontier;
  }, [chartData, tradeoffFrontier]);

  if (!chartData.length) {
    return (
      <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          No candidate data available for tradeoff analysis.
        </Typography>
      </Paper>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Cost vs Service Tradeoff Frontier
      </Typography>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="cost"
            name="Total Cost"
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            label={{ value: 'Total Cost ($)', position: 'bottom', offset: -5 }}
          />
          <YAxis
            type="number"
            dataKey="otif"
            name="OTIF"
            domain={[0.8, 1.0]}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            label={{ value: 'Projected OTIF', angle: -90, position: 'insideLeft' }}
          />
          <ZAxis range={[80, 200]} />
          <Tooltip content={<CustomTooltip />} />
          <Scatter
            data={chartData}
            fill="#1976d2"
            onClick={(data) => onSelect?.(data.method)}
            cursor="pointer"
            shape={(props) => {
              const { cx, cy, payload } = props;
              const isSelected = payload.isSelected;
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={isSelected ? 10 : 7}
                  fill={payload.color}
                  stroke={isSelected ? '#000' : payload.color}
                  strokeWidth={isSelected ? 3 : 1}
                  opacity={isSelected ? 1 : 0.8}
                />
              );
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>

      {/* Legend */}
      <Box display="flex" flexWrap="wrap" gap={1} mt={1} justifyContent="center">
        {chartData.map(d => (
          <Chip
            key={d.method}
            label={d.label}
            size="small"
            onClick={() => onSelect?.(d.method)}
            sx={{
              bgcolor: d.isSelected ? d.color : 'transparent',
              color: d.isSelected ? '#fff' : d.color,
              borderColor: d.color,
              cursor: 'pointer',
            }}
            variant={d.isSelected ? 'filled' : 'outlined'}
          />
        ))}
      </Box>
    </Box>
  );
};

export default TradeoffChart;
