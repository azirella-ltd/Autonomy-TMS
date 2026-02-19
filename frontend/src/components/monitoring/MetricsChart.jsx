/**
 * Metrics Chart Component
 * Phase 6 Sprint 3: Monitoring & Observability
 *
 * Displays metrics data in various chart formats.
 * Features:
 * - Bar charts for counters
 * - Line charts for histograms
 * - Gauge displays for current values
 * - Automatic data filtering and formatting
 *
 * Migrated to Autonomy UI Kit (Tailwind CSS + lucide-react)
 */

import React from 'react';
import {
  Card,
  Badge,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Progress,
} from '../common';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const MetricsChart = ({ data, type, title, filterPrefix }) => {
  // Filter data by prefix
  const filterData = (data, prefix) => {
    if (!data || !prefix) return data;

    if (typeof data === 'object' && !Array.isArray(data)) {
      return Object.entries(data).reduce((acc, [key, value]) => {
        if (key.includes(prefix)) {
          acc[key] = value;
        }
        return acc;
      }, {});
    }

    return data;
  };

  // Format metric name for display
  const formatMetricName = (name) => {
    // Remove prefix
    if (filterPrefix) {
      name = name.replace(filterPrefix, '').replace(/^[{_}]+/, '');
    }

    // Extract labels if present (e.g., {method="GET",path="/api/games"})
    const labelsMatch = name.match(/\{([^}]+)\}/);
    if (labelsMatch) {
      const labels = labelsMatch[1]
        .split(',')
        .map((l) => {
          const [key, val] = l.split('=');
          return `${key}: ${val.replace(/"/g, '')}`;
        })
        .join(', ');
      return labels;
    }

    // Format snake_case to Title Case
    return name
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Render based on type
  const filteredData = filterData(data, filterPrefix);

  if (!filteredData || Object.keys(filteredData).length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-sm text-muted-foreground">No data available</p>
      </div>
    );
  }

  // Counter chart (bar chart)
  if (type === 'counter') {
    const chartData = Object.entries(filteredData).map(([name, value]) => ({
      name: formatMetricName(name),
      value: value,
    }));

    return (
      <div>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="name"
              angle={-45}
              textAnchor="end"
              height={100}
              fontSize={10}
            />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#1976d2" />
          </BarChart>
        </ResponsiveContainer>

        {/* Table view */}
        <TableContainer className="mt-4 border rounded-md">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell className="font-medium">Metric</TableCell>
                <TableCell className="font-medium text-right">Count</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {chartData.map((row, index) => (
                <TableRow key={index}>
                  <TableCell className="text-xs">{row.name}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant="default" size="sm">
                      {row.value}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
    );
  }

  // Histogram chart (statistics table)
  if (type === 'histogram') {
    return (
      <div>
        <TableContainer className="border rounded-md">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell className="font-medium">Metric</TableCell>
                <TableCell className="font-medium text-right">Count</TableCell>
                <TableCell className="font-medium text-right">Mean</TableCell>
                <TableCell className="font-medium text-right">P50</TableCell>
                <TableCell className="font-medium text-right">P95</TableCell>
                <TableCell className="font-medium text-right">P99</TableCell>
                <TableCell className="font-medium text-right">Max</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(filteredData).map(([name, stats], index) => (
                <TableRow key={index}>
                  <TableCell className="text-xs">
                    {formatMetricName(name)}
                  </TableCell>
                  <TableCell className="text-right">{stats.count || 0}</TableCell>
                  <TableCell className="text-right">
                    {stats.mean ? stats.mean.toFixed(3) : 'N/A'}
                  </TableCell>
                  <TableCell className="text-right">
                    {stats.p50 ? stats.p50.toFixed(3) : 'N/A'}
                  </TableCell>
                  <TableCell className="text-right">
                    {stats.p95 ? stats.p95.toFixed(3) : 'N/A'}
                  </TableCell>
                  <TableCell className="text-right">
                    {stats.p99 ? stats.p99.toFixed(3) : 'N/A'}
                  </TableCell>
                  <TableCell className="text-right">
                    {stats.max ? stats.max.toFixed(3) : 'N/A'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
    );
  }

  // Gauge chart (progress bars)
  if (type === 'gauge') {
    return (
      <div>
        {Object.entries(filteredData).map(([name, value], index) => {
          const displayValue = typeof value === 'number' ? value : 0;
          const maxValue = Math.max(100, displayValue * 1.2); // Auto-scale

          return (
            <div key={index} className="mb-6">
              <div className="flex justify-between mb-2">
                <span className="text-sm">{formatMetricName(name)}</span>
                <span className="text-sm font-medium">
                  {displayValue.toFixed(0)}
                </span>
              </div>
              <Progress
                value={displayValue}
                max={maxValue}
                size="lg"
                className="h-2.5 rounded"
              />
            </div>
          );
        })}

        {/* Summary table */}
        <TableContainer className="mt-4 border rounded-md">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell className="font-medium">Metric</TableCell>
                <TableCell className="font-medium text-right">Current Value</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(filteredData).map(([name, value], index) => (
                <TableRow key={index}>
                  <TableCell className="text-xs">
                    {formatMetricName(name)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant="default" size="sm">
                      {typeof value === 'number' ? value.toFixed(2) : value}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
    );
  }

  // Default: simple table
  return (
    <TableContainer className="border rounded-md">
      <Table>
        <TableHead>
          <TableRow>
            <TableCell className="font-medium">Metric</TableCell>
            <TableCell className="font-medium text-right">Value</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {Object.entries(filteredData).map(([name, value], index) => (
            <TableRow key={index}>
              <TableCell className="text-xs">
                {formatMetricName(name)}
              </TableCell>
              <TableCell className="text-right">
                {typeof value === 'object'
                  ? JSON.stringify(value)
                  : String(value)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

export default MetricsChart;
