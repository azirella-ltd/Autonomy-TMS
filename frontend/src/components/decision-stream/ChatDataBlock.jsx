/**
 * ChatDataBlock — Renders structured data blocks inline in Decision Stream chat.
 *
 * Supports block_type:
 *   - metrics_row:  Array of KPI metric cards
 *   - table:        Data table with columns/rows
 *   - inventory_bar: Inventory position visualization
 *   - alert:        Alert/warning box
 */

import React from 'react';
import { Badge, Card, CardContent } from '../common';
import { cn } from '../../lib/utils/cn';
import {
  TrendingUp,
  TrendingDown,
  Package,
  BarChart3,
  AlertTriangle,
} from 'lucide-react';

const MetricCard = ({ label, value, unit, status, trend }) => {
  const statusColors = {
    success: 'text-emerald-600 bg-emerald-50 border-emerald-200',
    warning: 'text-amber-600 bg-amber-50 border-amber-200',
    destructive: 'text-red-600 bg-red-50 border-red-200',
    info: 'text-blue-600 bg-blue-50 border-blue-200',
  };

  return (
    <div
      className={cn(
        'flex flex-col gap-0.5 px-3 py-2 rounded-md border text-xs min-w-[100px]',
        status ? statusColors[status] || 'bg-muted/40 border-border' : 'bg-muted/40 border-border'
      )}
    >
      <span className="text-muted-foreground truncate">{label}</span>
      <span className="font-semibold text-sm">
        {value}
        {unit ? <span className="text-muted-foreground ml-0.5 font-normal">{unit}</span> : null}
      </span>
    </div>
  );
};

const DataTable = ({ columns, rows }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr className="border-b border-border">
          {columns.map((col, i) => (
            <th key={i} className="text-left px-2 py-1.5 font-medium text-muted-foreground">
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri} className="border-b border-border/50 hover:bg-muted/30">
            {row.map((cell, ci) => (
              <td key={ci} className="px-2 py-1.5 tabular-nums">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ChatDataBlock = ({ block }) => {
  if (!block || !block.block_type) return null;

  const { block_type, title, data } = block;

  const icon = {
    metrics_row: <BarChart3 className="h-3.5 w-3.5" />,
    table: <Package className="h-3.5 w-3.5" />,
    inventory_bar: <Package className="h-3.5 w-3.5" />,
    alert: <AlertTriangle className="h-3.5 w-3.5" />,
  }[block_type] || null;

  return (
    <div className="mt-2 rounded-md border bg-card/80 overflow-hidden">
      {title && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/40 border-b text-xs font-medium text-muted-foreground">
          {icon}
          {title}
        </div>
      )}
      <div className="p-2">
        {block_type === 'metrics_row' && data?.metrics && (
          <div className="flex flex-wrap gap-2">
            {data.metrics.map((m, i) => (
              <MetricCard key={i} {...m} />
            ))}
          </div>
        )}

        {block_type === 'table' && data?.columns && data?.rows && (
          <DataTable columns={data.columns} rows={data.rows} />
        )}

        {block_type === 'alert' && (
          <div
            className={cn(
              'flex items-start gap-2 p-2 rounded text-xs',
              data?.severity === 'critical' ? 'bg-red-50 text-red-700' :
              data?.severity === 'warning' ? 'bg-amber-50 text-amber-700' :
              'bg-blue-50 text-blue-700'
            )}
          >
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
            <span>{data?.message || 'Alert'}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatDataBlock;
