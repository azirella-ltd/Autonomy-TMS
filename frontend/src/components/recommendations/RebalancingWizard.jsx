import React, { useState } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../common';
import {
  Play,
  Save,
  RefreshCw,
  TrendingUp,
  Truck,
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react';
import { api } from '../../services/api';

/**
 * RebalancingWizard Component
 *
 * Network-wide inventory rebalancing with LP optimization.
 * Features:
 * - Run demo or custom rebalancing optimization
 * - View transfer recommendations with priority
 * - Save recommendations for execution workflow
 * - Configure optimization parameters
 */
const RebalancingWizard = ({ configId, onRecommendationsSaved }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Optimization parameters
  const [params, setParams] = useState({
    planning_horizon_days: 7,
    min_transfer_quantity: 10,
    target_service_level: 0.95,
  });

  // Results
  const [result, setResult] = useState(null);
  const [expandedRec, setExpandedRec] = useState(null);

  // Run demo rebalancing
  const runDemoRebalancing = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post('/rebalancing/demo');
      setResult(response.data);
      setSuccess('Rebalancing optimization completed successfully');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run rebalancing optimization');
    } finally {
      setLoading(false);
    }
  };

  // Run rebalancing with config
  const runRebalancing = async () => {
    if (!configId) {
      runDemoRebalancing();
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post('/rebalancing/optimize', {
        config_id: configId,
        ...params,
      });
      setResult(response.data);
      setSuccess('Rebalancing optimization completed successfully');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run rebalancing optimization');
    } finally {
      setLoading(false);
    }
  };

  // Save recommendations
  const saveRecommendations = async () => {
    if (!result || result.recommendations.length === 0) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/rebalancing/save-recommendations', {
        config_id: configId,
        ...params,
      });
      setSuccess(`Saved ${response.data.saved_count} recommendations for review`);
      if (onRecommendationsSaved) {
        onRecommendationsSaved(response.data);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save recommendations');
    } finally {
      setLoading(false);
    }
  };

  const getPriorityVariant = (priority) => {
    switch (priority) {
      case 'critical': return 'destructive';
      case 'high': return 'warning';
      case 'medium': return 'info';
      case 'low': return 'secondary';
      default: return 'secondary';
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 className="text-xl font-semibold mb-1">Inventory Rebalancing</h2>
          <p className="text-sm text-muted-foreground">
            Optimize inventory distribution across your network using linear programming
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={runDemoRebalancing}
            disabled={loading}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Run Demo
          </Button>
          <Button
            onClick={runRebalancing}
            disabled={loading}
          >
            {loading ? <Spinner className="h-4 w-4 mr-2" /> : <Play className="h-4 w-4 mr-2" />}
            {loading ? 'Optimizing...' : 'Run Optimization'}
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert className="mb-4 bg-green-50 border-green-200">
          <AlertDescription className="text-green-800">{success}</AlertDescription>
        </Alert>
      )}

      {/* Parameters */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <h3 className="font-medium mb-4">Optimization Parameters</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <Label>Planning Horizon: {params.planning_horizon_days} days</Label>
              <input
                type="range"
                value={params.planning_horizon_days}
                onChange={(e) => setParams({ ...params, planning_horizon_days: parseInt(e.target.value) })}
                min={1}
                max={30}
                className="w-full mt-2 accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>1d</span>
                <span>7d</span>
                <span>14d</span>
                <span>30d</span>
              </div>
            </div>
            <div>
              <Label htmlFor="min-transfer">Min Transfer Quantity</Label>
              <Input
                id="min-transfer"
                type="number"
                value={params.min_transfer_quantity}
                onChange={(e) => setParams({ ...params, min_transfer_quantity: parseFloat(e.target.value) })}
                min={1}
                step={1}
                className="mt-2"
              />
            </div>
            <div>
              <Label>Target Service Level: {(params.target_service_level * 100).toFixed(0)}%</Label>
              <input
                type="range"
                value={params.target_service_level}
                onChange={(e) => setParams({ ...params, target_service_level: parseFloat(e.target.value) })}
                min={0.8}
                max={0.99}
                step={0.01}
                className="w-full mt-2 accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>80%</span>
                <span>90%</span>
                <span>95%</span>
                <span>99%</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground mb-1">Cost Before</p>
                <p className="text-2xl font-bold">{formatCurrency(result.total_cost_before)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground mb-1">Cost After</p>
                <p className="text-2xl font-bold text-green-600">{formatCurrency(result.total_cost_after)}</p>
              </CardContent>
            </Card>
            <Card className="bg-green-50 border-green-200">
              <CardContent className="pt-6">
                <p className="text-sm text-green-700 mb-1">Total Savings</p>
                <p className="text-2xl font-bold text-green-700">{formatCurrency(result.total_savings)}</p>
                <p className="text-sm text-green-600">({result.savings_percentage}% reduction)</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground mb-1">Recommendations</p>
                <p className="text-2xl font-bold">{result.recommendation_count}</p>
                <p className="text-xs text-muted-foreground">{result.optimization_status}</p>
              </CardContent>
            </Card>
          </div>

          {/* Recommendations Table */}
          {result.recommendations.length > 0 && (
            <Card className="mb-6">
              <div className="p-4 flex justify-between items-center border-b">
                <h3 className="font-semibold">Transfer Recommendations</h3>
                <Button onClick={saveRecommendations} disabled={loading}>
                  <Save className="h-4 w-4 mr-2" />
                  Save All Recommendations
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Priority</TableHead>
                    <TableHead>From</TableHead>
                    <TableHead>To</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Transport Cost</TableHead>
                    <TableHead className="text-right">Cost Saving</TableHead>
                    <TableHead>Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.recommendations.map((rec, index) => (
                    <React.Fragment key={index}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => setExpandedRec(expandedRec === index ? null : index)}
                      >
                        <TableCell>
                          <Badge variant={getPriorityVariant(rec.priority)}>
                            {rec.priority.toUpperCase()}
                          </Badge>
                        </TableCell>
                        <TableCell>{rec.source_node_name}</TableCell>
                        <TableCell>{rec.dest_node_name}</TableCell>
                        <TableCell className="text-right font-medium">
                          {rec.quantity.toLocaleString()} units
                        </TableCell>
                        <TableCell className="text-right text-destructive">
                          {formatCurrency(rec.transport_cost)}
                        </TableCell>
                        <TableCell className={`text-right font-medium ${rec.cost_saving > 0 ? 'text-green-600' : 'text-destructive'}`}>
                          {formatCurrency(rec.cost_saving)}
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="icon">
                            {expandedRec === index ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedRec === index && (
                        <TableRow>
                          <TableCell colSpan={7} className="bg-muted/30">
                            <div className="py-2 px-4 flex items-center gap-2">
                              <Info className="h-4 w-4 text-muted-foreground" />
                              <span className="text-sm text-muted-foreground">{rec.reason}</span>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {/* No recommendations */}
          {result.recommendations.length === 0 && (
            <Card className="p-8 text-center">
              <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">Network is Balanced</h3>
              <p className="text-muted-foreground">
                No rebalancing transfers are recommended. Your inventory distribution is already optimal.
              </p>
            </Card>
          )}

          {/* Computation info */}
          <p className="text-xs text-muted-foreground text-right">
            Optimization completed in {result.computation_time_ms.toFixed(1)}ms
          </p>
        </>
      )}

      {/* Empty state */}
      {!result && !loading && (
        <Card className="p-8 text-center">
          <Truck className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">Run Rebalancing Optimization</h3>
          <p className="text-muted-foreground mb-4">
            Click "Run Demo" to see sample rebalancing recommendations, or configure parameters and run with your supply chain.
          </p>
          <Button onClick={runDemoRebalancing}>
            <Play className="h-4 w-4 mr-2" />
            Run Demo
          </Button>
        </Card>
      )}
    </div>
  );
};

export default RebalancingWizard;
