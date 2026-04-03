/**
 * Lot Sizing Analysis Page
 *
 * Shows order sizing analysis from the live supply plan:
 * - Summary cards (avg order qty, MOQ, frequency, total orders)
 * - Order size distribution histogram
 * - Product-level order analysis table with EOQ comparison
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Spinner,
  Alert,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  Package,
  TrendingUp,
  Calendar,
  ShoppingCart,
  BarChart3,
  ArrowUpDown,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

const LotSizingAnalysis = () => {
  const { effectiveConfigId, loading: configLoading } = useActiveConfig();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortField, setSortField] = useState('total_qty');
  const [sortDir, setSortDir] = useState('desc');

  useEffect(() => {
    if (!effectiveConfigId) return;

    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await api.get('/lot-sizing/order-analysis', {
          params: { config_id: effectiveConfigId, plan_version: 'live' },
        });
        setData(response.data);
      } catch (err) {
        console.error('Error fetching order sizing analysis:', err);
        setError(err.response?.data?.detail || 'Failed to load order sizing analysis.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [effectiveConfigId]);

  const sortedProducts = useMemo(() => {
    if (!data?.by_product) return [];
    return [...data.by_product].sort((a, b) => {
      const aVal = a[sortField] ?? 0;
      const bVal = b[sortField] ?? 0;
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
    });
  }, [data, sortField, sortDir]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const formatNumber = (value) => {
    if (value == null || isNaN(value)) return '--';
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
  };

  const SortHeader = ({ field, children }) => (
    <TableHead
      className="text-right cursor-pointer select-none hover:bg-muted/50"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center justify-end gap-1">
        {children}
        {sortField === field && (
          <ArrowUpDown className="h-3 w-3 text-muted-foreground" />
        )}
      </div>
    </TableHead>
  );

  if (configLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6">
        <Alert variant="destructive">
          <strong>Error:</strong> {error}
        </Alert>
      </div>
    );
  }

  if (!data || data.summary.total_orders === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Order Sizing Analysis</h1>
          <p className="text-sm text-muted-foreground">
            Analyze order quantities in the current Plan of Record
          </p>
        </div>
        <Alert variant="info">
          No supply plan orders found. Run provisioning to generate the Plan of Record.
        </Alert>
      </div>
    );
  }

  const { summary, distribution, by_product } = data;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Order Sizing Analysis</h1>
        <p className="text-sm text-muted-foreground">
          Order quantity analysis from the live Plan of Record across {summary.product_count} products and {summary.site_count} sites
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Package className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Avg Order Qty</p>
                <p className="text-2xl font-bold">{formatNumber(summary.avg_order_qty)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-100 rounded-lg">
                <TrendingUp className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Min Order Qty</p>
                <p className="text-2xl font-bold">{formatNumber(summary.min_order_qty)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <Calendar className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Orders / Week</p>
                <p className="text-2xl font-bold">{summary.orders_per_week}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 rounded-lg">
                <ShoppingCart className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Orders</p>
                <p className="text-2xl font-bold">{formatNumber(summary.total_orders)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Order Size Distribution */}
      {distribution.length > 0 && (
        <Card className="mb-6">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-5 w-5 text-muted-foreground" />
              <h2 className="text-lg font-semibold">Order Size Distribution</h2>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={distribution}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="range" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} />
                <RechartsTooltip
                  formatter={(value) => [value, 'Orders']}
                  labelFormatter={(label) => `Qty Range: ${label}`}
                />
                <Bar dataKey="count" name="Order Count" radius={[4, 4, 0, 0]}>
                  {distribution.map((_, index) => (
                    <Cell
                      key={index}
                      fill={index === distribution.length - 1 ? '#6366f1' : '#818cf8'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Product-level Order Analysis */}
      <Card>
        <CardContent className="pt-4">
          <h2 className="text-lg font-semibold mb-4">Product Order Analysis</h2>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <SortHeader field="order_count">Orders</SortHeader>
                  <SortHeader field="avg_qty">Avg Qty</SortHeader>
                  <SortHeader field="total_qty">Total Qty</SortHeader>
                  <SortHeader field="min_qty">Min</SortHeader>
                  <SortHeader field="max_qty">Max</SortHeader>
                  <SortHeader field="avg_days_between">Avg Days Between</SortHeader>
                  <SortHeader field="eoq">EOQ</SortHeader>
                  <TableHead className="text-right">EOQ vs Actual</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedProducts.map((row) => {
                  const eoqDiff = row.eoq > 0
                    ? ((row.avg_qty - row.eoq) / row.eoq * 100).toFixed(0)
                    : null;
                  const isOverEoq = eoqDiff !== null && parseFloat(eoqDiff) > 10;
                  const isUnderEoq = eoqDiff !== null && parseFloat(eoqDiff) < -10;

                  return (
                    <TableRow key={row.product_id}>
                      <TableCell>
                        <div className="max-w-[200px] truncate" title={row.product_name}>
                          {row.product_name}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">{row.order_count}</TableCell>
                      <TableCell className="text-right font-medium">{formatNumber(row.avg_qty)}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.total_qty)}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.min_qty)}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.max_qty)}</TableCell>
                      <TableCell className="text-right">
                        {row.avg_days_between > 0 ? `${row.avg_days_between}d` : '--'}
                      </TableCell>
                      <TableCell className="text-right">{formatNumber(row.eoq)}</TableCell>
                      <TableCell className="text-right">
                        {eoqDiff !== null ? (
                          <Badge variant={isOverEoq ? 'warning' : isUnderEoq ? 'info' : 'success'}>
                            {eoqDiff > 0 ? '+' : ''}{eoqDiff}%
                          </Badge>
                        ) : (
                          '--'
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            EOQ calculated using default ordering cost ($500) and 25% annual holding cost rate.
            Values within 10% of EOQ are considered well-sized.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default LotSizingAnalysis;
