import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
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
import { DollarSign, ShoppingCart, Layers, TrendingDown, Download, ArrowUpDown } from 'lucide-react';
import AnalyticsSummaryCard from './AnalyticsSummaryCard';
import simulationApi from '../../services/api';

const AggregationAnalytics = ({ gameId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: 'total_savings', direction: 'desc' });

  useEffect(() => {
    fetchMetrics();
  }, [gameId]);

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);

    const result = await simulationApi.getAggregationMetrics(gameId);

    if (result.success) {
      setMetrics(result.data);
    } else {
      setError(result.error);
    }

    setLoading(false);
  };

  const handleSort = (key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const getSortedSitePairs = () => {
    if (!metrics || !metrics.by_site_pair) return [];

    const sorted = [...metrics.by_site_pair].sort((a, b) => {
      const aVal = a[sortConfig.key] || 0;
      const bVal = b[sortConfig.key] || 0;

      if (sortConfig.direction === 'asc') {
        return aVal > bVal ? 1 : -1;
      }
      return aVal < bVal ? 1 : -1;
    });

    return sorted.slice(0, 10); // Top 10
  };

  const SortableHeader = ({ column, label, align = 'left' }) => (
    <TableHead className={align === 'right' ? 'text-right' : ''}>
      <button
        onClick={() => handleSort(column)}
        className="inline-flex items-center gap-1 hover:text-foreground text-muted-foreground transition-colors"
      >
        {label}
        <ArrowUpDown className={`h-3 w-3 ${sortConfig.key === column ? 'text-foreground' : ''}`} />
      </button>
    </TableHead>
  );

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

  if (!metrics || !metrics.aggregation_summary) {
    return (
      <div className="p-6">
        <Alert>
          <AlertDescription>No aggregation data available for this game.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { aggregation_summary, by_round, by_site_pair } = metrics;

  const handleExportCSV = () => {
    simulationApi.exportAggregationCSV(gameId);
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
          title="Total Cost Savings"
          value={`$${aggregation_summary.total_cost_savings.toFixed(2)}`}
          subtitle={`Avg: $${aggregation_summary.avg_cost_savings_per_round.toFixed(2)}/round`}
          icon={DollarSign}
          color="success"
        />
        <AnalyticsSummaryCard
          title="Orders Aggregated"
          value={aggregation_summary.total_orders_aggregated}
          subtitle={`Across ${metrics.total_rounds} rounds`}
          icon={ShoppingCart}
          color="primary"
        />
        <AnalyticsSummaryCard
          title="Groups Created"
          value={aggregation_summary.total_groups_created}
          subtitle="Aggregated order groups"
          icon={Layers}
          color="info"
        />
        <AnalyticsSummaryCard
          title="Efficiency Gain"
          value={`${((1 - aggregation_summary.total_groups_created / Math.max(aggregation_summary.total_orders_aggregated, 1)) * 100).toFixed(1)}%`}
          subtitle="Order reduction"
          icon={TrendingDown}
          color="success"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Cost Savings Over Time */}
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Cost Savings by Round</h3>
            {by_round && by_round.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={by_round}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                  <YAxis label={{ value: 'Cost Savings ($)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip formatter={(value) => `$${value.toFixed(2)}`} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="cost_savings"
                    stroke="#22c55e"
                    strokeWidth={2}
                    name="Cost Savings"
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Alert>
                <AlertDescription>No data available</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Orders Aggregated by Round */}
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Orders Aggregated by Round</h3>
            {by_round && by_round.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={by_round}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                  <YAxis label={{ value: 'Count', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="orders_aggregated" fill="#3b82f6" name="Orders Aggregated" />
                  <Bar dataKey="groups_created" fill="#f59e0b" name="Groups Created" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Alert>
                <AlertDescription>No data available</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Site Pair Summary Table */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Top Site Pairs by Aggregation</h3>
          {by_site_pair && by_site_pair.length > 0 ? (
            <div className="border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHeader column="from_site" label="From Site" />
                    <SortableHeader column="to_site" label="To Site" />
                    <SortableHeader column="groups_created" label="Groups Created" align="right" />
                    <SortableHeader column="total_aggregated" label="Total Aggregated" align="right" />
                    <SortableHeader column="total_savings" label="Total Savings" align="right" />
                    <SortableHeader column="avg_quantity_adjustment" label="Avg Adjustment" align="right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {getSortedSitePairs().map((pair, index) => (
                    <TableRow key={index}>
                      <TableCell>{pair.from_site}</TableCell>
                      <TableCell>{pair.to_site}</TableCell>
                      <TableCell className="text-right">{pair.groups_created}</TableCell>
                      <TableCell className="text-right">{pair.total_aggregated}</TableCell>
                      <TableCell className="text-right">${pair.total_savings.toFixed(2)}</TableCell>
                      <TableCell className="text-right">{pair.avg_quantity_adjustment.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <Alert>
              <AlertDescription>No site pair data available</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AggregationAnalytics;
