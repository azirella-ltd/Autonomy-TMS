import React, { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { Alert } from '../common/Alert';
import { Table, TableBody, TableCell, TableRow } from '../common/Table';

/**
 * Distribution Preview Component
 *
 * Visualizes stochastic distribution with histogram and statistics.
 *
 * Features:
 * - Histogram visualization of sample data
 * - Summary statistics (mean, std, percentiles, min, max)
 * - Reference lines for mean and median
 * - Automatic binning for continuous distributions
 * - Support for discrete distributions
 *
 * Props:
 * - data: Sample data from backend (array of numbers or {samples, stats} object)
 * - config: Distribution configuration (for display)
 * - loading: Show loading state
 * - error: Error message
 */

const DistributionPreview = ({ data = null, config = null, loading = false, error = null }) => {
  // Calculate statistics from samples
  const stats = useMemo(() => {
    if (!data) return null;

    // Handle both array and object format
    const samples = Array.isArray(data) ? data : data.samples || [];
    const providedStats = Array.isArray(data) ? null : data.stats;

    if (providedStats) {
      return providedStats;
    }

    if (samples.length === 0) {
      return null;
    }

    // Calculate statistics
    const sorted = [...samples].sort((a, b) => a - b);
    const n = sorted.length;
    const sum = sorted.reduce((a, b) => a + b, 0);
    const mean = sum / n;
    const variance = sorted.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / n;
    const stddev = Math.sqrt(variance);

    const getPercentile = (p) => {
      const idx = Math.floor(n * p / 100);
      return sorted[Math.min(idx, n - 1)];
    };

    return {
      count: n,
      mean: mean,
      std: stddev,
      min: sorted[0],
      max: sorted[n - 1],
      median: getPercentile(50),
      p5: getPercentile(5),
      p25: getPercentile(25),
      p75: getPercentile(75),
      p95: getPercentile(95)
    };
  }, [data]);

  // Create histogram data
  const histogramData = useMemo(() => {
    if (!data || !stats) return [];

    const samples = Array.isArray(data) ? data : data.samples || [];
    if (samples.length === 0) return [];

    // Determine number of bins (Sturges' rule)
    const numBins = Math.min(30, Math.ceil(Math.log2(samples.length) + 1));

    // Check if discrete (all integers)
    const allIntegers = samples.every(s => Number.isInteger(s));

    if (allIntegers) {
      // Discrete distribution: one bin per unique value
      const counts = {};
      samples.forEach(val => {
        counts[val] = (counts[val] || 0) + 1;
      });

      return Object.keys(counts)
        .map(val => ({
          bin: Number(val),
          count: counts[val],
          label: String(val)
        }))
        .sort((a, b) => a.bin - b.bin);
    } else {
      // Continuous distribution: create bins
      const min = stats.min;
      const max = stats.max;
      const binWidth = (max - min) / numBins;

      const bins = Array.from({ length: numBins }, (_, i) => ({
        binStart: min + i * binWidth,
        binEnd: min + (i + 1) * binWidth,
        count: 0
      }));

      // Count samples in each bin
      samples.forEach(val => {
        const binIdx = Math.min(Math.floor((val - min) / binWidth), numBins - 1);
        if (binIdx >= 0 && binIdx < bins.length) {
          bins[binIdx].count++;
        }
      });

      // Format bins for chart
      return bins.map((bin, idx) => ({
        bin: (bin.binStart + bin.binEnd) / 2,
        count: bin.count,
        label: idx === 0 || idx === bins.length - 1 || idx % 3 === 0
          ? `${bin.binStart.toFixed(1)}-${bin.binEnd.toFixed(1)}`
          : ''
      }));
    }
  }, [data, stats]);

  if (loading) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">
          Generating preview...
        </p>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="error" className="mb-4">
        {error}
      </Alert>
    );
  }

  if (!data || !stats) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">
          No preview data available. Click "Generate Preview" to see distribution shape.
        </p>
      </Card>
    );
  }

  // Custom tooltip for the chart
  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <Card className="p-2">
          <p className="text-sm">
            Count: {payload[0].value}
          </p>
        </Card>
      );
    }
    return null;
  };

  return (
    <div>
      {/* Histogram */}
      <Card className="p-4 mb-4">
        <h3 className="text-lg font-semibold mb-4">
          Distribution Shape
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={histogramData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              label={{ value: 'Value', position: 'insideBottom', offset: -10 }}
            />
            <YAxis
              label={{ value: 'Frequency', angle: -90, position: 'insideLeft' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="count" fill="#1976d2" />
            <ReferenceLine x={stats.mean} stroke="red" strokeDasharray="3 3" label="Mean" />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Statistics Table */}
      <Card className="p-4">
        <h3 className="text-lg font-semibold mb-4">
          Summary Statistics
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Central Tendency */}
          <div>
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell className="font-semibold">Mean ({'\u03BC'})</TableCell>
                  <TableCell className="text-right">{stats.mean.toFixed(3)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">Median</TableCell>
                  <TableCell className="text-right">{stats.median.toFixed(3)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">Std Dev ({'\u03C3'})</TableCell>
                  <TableCell className="text-right">{stats.std.toFixed(3)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">CV (%)</TableCell>
                  <TableCell className="text-right">
                    {stats.mean !== 0 ? ((stats.std / Math.abs(stats.mean)) * 100).toFixed(1) : 'N/A'}%
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>

          {/* Range & Percentiles */}
          <div>
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell className="font-semibold">Minimum</TableCell>
                  <TableCell className="text-right">{stats.min.toFixed(3)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">Maximum</TableCell>
                  <TableCell className="text-right">{stats.max.toFixed(3)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">5th-95th %ile</TableCell>
                  <TableCell className="text-right">
                    {stats.p5.toFixed(2)} - {stats.p95.toFixed(2)}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-semibold">IQR (25-75)</TableCell>
                  <TableCell className="text-right">
                    {stats.p25.toFixed(2)} - {stats.p75.toFixed(2)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Configuration Display */}
        {config && (
          <div className="mt-4">
            <p className="text-sm text-muted-foreground">
              <strong>Configuration:</strong> {config.type}
              {config.mean !== undefined && ` (\u03BC=${config.mean})`}
              {config.stddev !== undefined && ` (\u03C3=${config.stddev})`}
              {config.min !== undefined && ` [min=${config.min}]`}
              {config.max !== undefined && ` [max=${config.max}]`}
            </p>
          </div>
        )}

        {/* Sample Size */}
        <div className="mt-2">
          <Badge variant="secondary" size="sm">{stats.count} samples</Badge>
        </div>
      </Card>
    </div>
  );
};

export default DistributionPreview;
