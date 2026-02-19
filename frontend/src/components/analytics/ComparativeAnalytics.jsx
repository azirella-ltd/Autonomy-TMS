import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Progress,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../common';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { CheckCircle, XCircle, TrendingUp, ArrowLeftRight, Download } from 'lucide-react';
import simulationApi from '../../services/api';

const ComparativeAnalytics = ({ gameId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    fetchMetrics();
  }, [gameId]);

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);

    const result = await simulationApi.getComparativeAnalytics(gameId);

    if (result.success) {
      setMetrics(result.data);
    } else {
      setError(result.error);
    }

    setLoading(false);
  };

  const getEfficiencyColor = (pct) => {
    if (pct >= 50) return 'success';
    if (pct >= 20) return 'warning';
    return 'destructive';
  };

  const prepareComparisonData = () => {
    if (!metrics || !metrics.comparison) return [];

    const { theoretical_without_aggregation, actual_with_aggregation } = metrics.comparison;

    return [
      {
        metric: 'Total Orders',
        without: theoretical_without_aggregation.total_orders,
        with: actual_with_aggregation.total_orders
      },
      {
        metric: 'Total Cost',
        without: theoretical_without_aggregation.total_cost,
        with: actual_with_aggregation.total_cost
      }
    ];
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

  if (!metrics || !metrics.features_enabled) {
    return (
      <div className="p-6">
        <Alert>
          <AlertDescription>No comparative data available for this game.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { features_enabled, comparison, capacity_impact } = metrics;
  const comparisonData = prepareComparisonData();
  const efficiencyGain = comparison?.savings?.efficiency_gain_pct || 0;

  const handleExportCSV = () => {
    simulationApi.exportComparisonCSV(gameId);
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

      {/* Feature Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              {features_enabled.order_aggregation ? (
                <CheckCircle className="h-10 w-10 text-green-500 mr-4" />
              ) : (
                <XCircle className="h-10 w-10 text-red-500 mr-4" />
              )}
              <div>
                <h3 className="text-lg font-semibold">Order Aggregation</h3>
                <Badge variant={features_enabled.order_aggregation ? 'success' : 'secondary'}>
                  {features_enabled.order_aggregation ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
            </div>
            {features_enabled.order_aggregation && comparison && (
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">
                  Orders Reduced: {comparison.savings.orders_reduced}
                </p>
                <p className="text-sm text-muted-foreground">
                  Cost Saved: ${comparison.savings.cost_saved.toFixed(2)}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              {features_enabled.capacity_constraints ? (
                <CheckCircle className="h-10 w-10 text-green-500 mr-4" />
              ) : (
                <XCircle className="h-10 w-10 text-red-500 mr-4" />
              )}
              <div>
                <h3 className="text-lg font-semibold">Capacity Constraints</h3>
                <Badge variant={features_enabled.capacity_constraints ? 'success' : 'secondary'}>
                  {features_enabled.capacity_constraints ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
            </div>
            {features_enabled.capacity_constraints && capacity_impact && (
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">
                  Orders Fulfilled: {capacity_impact.orders_fulfilled}
                </p>
                <p className="text-sm text-muted-foreground">
                  Orders Queued: {capacity_impact.orders_queued}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Efficiency Gains Section */}
      {features_enabled.order_aggregation && comparison && (
        <>
          <Card className="mb-8">
            <CardContent className="pt-6">
              <div className="flex items-center mb-6">
                <TrendingUp className="h-8 w-8 text-green-500 mr-4" />
                <h3 className="text-lg font-semibold">Overall Efficiency Gain</h3>
              </div>

              <div className="mb-4">
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-muted-foreground">
                    Efficiency Improvement
                  </span>
                  <span className="text-sm font-semibold">
                    {efficiencyGain.toFixed(1)}%
                  </span>
                </div>
                <Progress value={Math.min(efficiencyGain, 100)} className="h-2.5" />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-6">
                <div className="text-center p-4 bg-muted/50 rounded-lg">
                  <span className="text-3xl font-bold text-red-500">
                    {comparison.theoretical_without_aggregation.total_orders}
                  </span>
                  <p className="text-sm text-muted-foreground mt-1">
                    Orders Without Features
                  </p>
                </div>
                <div className="flex items-center justify-center">
                  <ArrowLeftRight className="h-10 w-10 text-primary" />
                </div>
                <div className="text-center p-4 bg-green-500/10 rounded-lg">
                  <span className="text-3xl font-bold text-green-500">
                    {comparison.actual_with_aggregation.total_orders}
                  </span>
                  <p className="text-sm text-muted-foreground mt-1">
                    Orders With Features
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Comparison Chart */}
          <Card className="mb-8">
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Feature Impact Comparison</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={comparisonData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="metric" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="without" fill="#ef4444" name="Without Features" />
                  <Bar dataKey="with" fill="#22c55e" name="With Features" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Impact Summary Table */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Impact Summary</h3>
              <div className="border rounded-md">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Metric</TableHead>
                      <TableHead className="text-right">Without Features</TableHead>
                      <TableHead className="text-right">With Features</TableHead>
                      <TableHead className="text-right">Improvement</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell>Total Orders</TableCell>
                      <TableCell className="text-right">
                        {comparison.theoretical_without_aggregation.total_orders}
                      </TableCell>
                      <TableCell className="text-right">
                        {comparison.actual_with_aggregation.total_orders}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant="success">
                          -{comparison.savings.orders_reduced} orders
                        </Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Total Cost</TableCell>
                      <TableCell className="text-right">
                        ${comparison.theoretical_without_aggregation.total_cost.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        ${comparison.actual_with_aggregation.total_cost.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant="success">
                          -${comparison.savings.cost_saved.toFixed(2)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Efficiency Gain</TableCell>
                      <TableCell className="text-right">-</TableCell>
                      <TableCell className="text-right">-</TableCell>
                      <TableCell className="text-right">
                        <Badge variant={getEfficiencyColor(efficiencyGain)}>
                          +{efficiencyGain.toFixed(1)}%
                        </Badge>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* No Features Enabled Message */}
      {!features_enabled.order_aggregation && !features_enabled.capacity_constraints && (
        <Alert className="mt-4">
          <AlertDescription>
            No advanced features are enabled for this game. Enable order aggregation or capacity constraints to see comparative analytics.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
};

export default ComparativeAnalytics;
