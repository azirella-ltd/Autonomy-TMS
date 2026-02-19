import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../common';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { Factory, Gauge, AlertTriangle, CheckCircle, Download } from 'lucide-react';
import AnalyticsSummaryCard from './AnalyticsSummaryCard';
import simulationApi from '../../services/api';

const CapacityAnalytics = ({ gameId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    fetchMetrics();
  }, [gameId]);

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);

    const result = await simulationApi.getCapacityMetrics(gameId);

    if (result.success) {
      setMetrics(result.data);
    } else {
      setError(result.error);
    }

    setLoading(false);
  };

  const getUtilizationColor = (utilization) => {
    if (utilization >= 90) return '#ef4444'; // Red
    if (utilization >= 70) return '#f59e0b'; // Orange
    return '#22c55e'; // Green
  };

  const getUtilizationBadge = (utilization) => {
    if (utilization >= 90) {
      return <Badge variant="destructive">Critical</Badge>;
    }
    if (utilization >= 70) {
      return <Badge variant="warning">High</Badge>;
    }
    return <Badge variant="success">Normal</Badge>;
  };

  const countBottlenecks = () => {
    if (!metrics || !metrics.by_site) return 0;
    return metrics.by_site.filter(site => site.utilization_pct >= 90).length;
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!metrics || !metrics.capacity_summary) {
    return (
      <div className="p-6">
        <Alert>
          <AlertDescription>No capacity data available for this game.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { capacity_summary, by_site, by_round } = metrics;
  const bottleneckCount = countBottlenecks();

  const handleExportCSV = () => {
    simulationApi.exportCapacityCSV(gameId);
  };

  return (
    <div className="p-6">
      {/* Export Button */}
      <div className="flex justify-end mb-4">
        <Button
          variant="outline"
          leftIcon={<Download className="h-4 w-4" />}
          onClick={handleExportCSV}
        >
          Export CSV
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6 mb-8">
        <AnalyticsSummaryCard
          title="Sites with Capacity"
          value={capacity_summary.sites_with_capacity}
          subtitle="Capacity constraints"
          icon={Factory}
          color="primary"
        />
        <AnalyticsSummaryCard
          title="Total Capacity"
          value={capacity_summary.total_capacity.toFixed(0)}
          subtitle="Units per period"
          icon={Gauge}
          color="info"
        />
        <AnalyticsSummaryCard
          title="Avg Utilization"
          value={`${capacity_summary.avg_utilization.toFixed(1)}%`}
          subtitle="Across all sites"
          icon={CheckCircle}
          color={capacity_summary.avg_utilization >= 70 ? 'warning' : 'success'}
        />
        <AnalyticsSummaryCard
          title="Bottlenecks"
          value={bottleneckCount}
          subtitle=">90% utilization"
          icon={AlertTriangle}
          color={bottleneckCount > 0 ? 'error' : 'success'}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Capacity Utilization by Site */}
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Capacity Utilization by Site</h3>
            {by_site && by_site.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart
                  data={by_site}
                  layout="vertical"
                  margin={{ left: 100 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    label={{ value: 'Utilization (%)', position: 'insideBottom', offset: -5 }}
                  />
                  <YAxis type="category" dataKey="site" width={90} />
                  <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  <Bar
                    dataKey="utilization_pct"
                    name="Utilization"
                    fill="#3b82f6"
                    shape={(props) => {
                      const { x, y, width, height, utilization_pct } = props;
                      const fillColor = getUtilizationColor(utilization_pct);
                      return (
                        <rect
                          x={x}
                          y={y}
                          width={width}
                          height={height}
                          fill={fillColor}
                        />
                      );
                    }}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Alert>
                <AlertDescription>No site data available</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Utilization Over Time */}
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Utilization Over Time</h3>
            {by_round && by_round.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={by_round}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                  <YAxis
                    domain={[0, 100]}
                    label={{ value: 'Utilization (%)', angle: -90, position: 'insideLeft' }}
                  />
                  <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="utilization_pct"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    name="Utilization"
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Alert>
                <AlertDescription>No time series data available</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Site Capacity Table */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Site Capacity Details</h3>
          {by_site && by_site.length > 0 ? (
            <div className="border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Site</TableHead>
                    <TableHead className="text-right">Max Capacity</TableHead>
                    <TableHead className="text-right">Total Used</TableHead>
                    <TableHead className="text-right">Utilization</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {by_site.map((site, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <span className="font-medium">{site.site}</span>
                      </TableCell>
                      <TableCell className="text-right">{site.max_capacity.toFixed(0)}</TableCell>
                      <TableCell className="text-right">{site.total_used.toFixed(0)}</TableCell>
                      <TableCell className="text-right">
                        <span
                          className="font-semibold"
                          style={{ color: getUtilizationColor(site.utilization_pct) }}
                        >
                          {site.utilization_pct.toFixed(1)}%
                        </span>
                      </TableCell>
                      <TableCell className="text-center">
                        {getUtilizationBadge(site.utilization_pct)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <Alert>
              <AlertDescription>No site data available</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CapacityAnalytics;
