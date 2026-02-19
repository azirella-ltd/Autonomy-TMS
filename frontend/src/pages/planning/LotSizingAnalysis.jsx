/**
 * Lot Sizing Analysis Page
 *
 * Interactive tool for comparing lot sizing algorithms and applying them to MPS plans
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Spinner,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  ArrowLeft,
  Play,
  Download,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';

const LotSizingAnalysis = () => {
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(false);
  const [demandSchedule, setDemandSchedule] = useState('');
  const [setupCost, setSetupCost] = useState(500);
  const [holdingCost, setHoldingCost] = useState(2);
  const [unitCost, setUnitCost] = useState(50);
  const [fixedQuantity, setFixedQuantity] = useState(1000);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  // Sample demand
  const loadSampleDemand = () => {
    const sample = [1200, 900, 1000, 1100, 1250, 1150, 1300, 950, 1050, 1100, 1200, 1000, 1150];
    setDemandSchedule(sample.join(', '));
  };

  useEffect(() => {
    loadSampleDemand();
  }, []);

  const handleRunAnalysis = async () => {
    try {
      setLoading(true);
      setError(null);

      const demand = demandSchedule
        .split(',')
        .map((d) => parseFloat(d.trim()))
        .filter((d) => !isNaN(d));

      if (demand.length === 0) {
        setError('Please enter a valid demand schedule (comma-separated numbers)');
        return;
      }

      const response = await api.post('/lot-sizing/compare', {
        demand_schedule: demand,
        start_date: new Date().toISOString().split('T')[0],
        period_days: 7,
        setup_cost: parseFloat(setupCost),
        holding_cost_per_unit_per_period: parseFloat(holdingCost),
        unit_cost: parseFloat(unitCost),
        fixed_quantity: parseFloat(fixedQuantity),
        algorithms: ['LFL', 'EOQ', 'POQ', 'FOQ', 'PPB'],
      });

      setResults(response.data);
    } catch (err) {
      console.error('Error running lot sizing analysis:', err);
      setError(err.response?.data?.detail || 'Failed to run analysis. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const handleExportCSV = async () => {
    try {
      const demand = demandSchedule
        .split(',')
        .map((d) => parseFloat(d.trim()))
        .filter((d) => !isNaN(d));

      const response = await api.post(
        '/lot-sizing/export/csv',
        {
          demand_schedule: demand,
          start_date: new Date().toISOString().split('T')[0],
          period_days: 7,
          setup_cost: parseFloat(setupCost),
          holding_cost_per_unit_per_period: parseFloat(holdingCost),
          unit_cost: parseFloat(unitCost),
          fixed_quantity: parseFloat(fixedQuantity),
          algorithms: ['LFL', 'EOQ', 'POQ', 'FOQ', 'PPB'],
        },
        {
          responseType: 'blob',
        }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'lot_sizing_comparison.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Error exporting CSV:', err);
      setError('Failed to export CSV. Please try again.');
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={() => navigate('/planning/mps')}
          className="mb-4"
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          Back to MPS
        </Button>
        <h1 className="text-2xl font-bold">Lot Sizing Analysis</h1>
        <p className="text-sm text-muted-foreground">
          Compare lot sizing algorithms and optimize production batch sizes
        </p>
      </div>

      {/* Input Section */}
      <div className="grid grid-cols-1 lg:grid-cols-7 gap-6 mb-6">
        <Card className="lg:col-span-4">
          <CardContent className="pt-4">
            <h2 className="text-lg font-semibold mb-4">Demand Schedule</h2>
            <Textarea
              value={demandSchedule}
              onChange={(e) => setDemandSchedule(e.target.value)}
              placeholder="Enter weekly demand (comma-separated). Example: 1000, 1100, 950, 1200, ..."
              rows={3}
              className="mb-2"
            />
            <p className="text-xs text-muted-foreground mb-4">Enter demand quantities separated by commas</p>
            <Button variant="outline" size="sm" onClick={loadSampleDemand}>
              Load Sample Data
            </Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardContent className="pt-4">
            <h2 className="text-lg font-semibold mb-4">Cost Parameters</h2>
            <div className="space-y-4">
              <div>
                <Label>Setup Cost ($)</Label>
                <Input type="number" value={setupCost} onChange={(e) => setSetupCost(e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">Cost per production setup</p>
              </div>
              <div>
                <Label>Holding Cost ($/unit/period)</Label>
                <Input type="number" value={holdingCost} onChange={(e) => setHoldingCost(e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">Cost to hold one unit for one period</p>
              </div>
              <div>
                <Label>Unit Cost ($)</Label>
                <Input type="number" value={unitCost} onChange={(e) => setUnitCost(e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">Production cost per unit</p>
              </div>
              <div>
                <Label>Fixed Order Quantity</Label>
                <Input type="number" value={fixedQuantity} onChange={(e) => setFixedQuantity(e.target.value)} />
                <p className="text-xs text-muted-foreground mt-1">For FOQ algorithm</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Run Button */}
      <div className="flex justify-center gap-4 mb-6">
        <Button size="lg" onClick={handleRunAnalysis} disabled={loading} leftIcon={loading ? <Spinner size="sm" /> : <Play className="h-5 w-5" />}>
          {loading ? 'Analyzing...' : 'Run Lot Sizing Analysis'}
        </Button>
        {results && (
          <Button variant="outline" size="lg" onClick={handleExportCSV} leftIcon={<Download className="h-5 w-5" />}>
            Export CSV
          </Button>
        )}
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {/* Results */}
      {results && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <Card className="bg-green-50 border-green-200">
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Best Algorithm</h3>
                <p className="text-3xl font-bold text-green-700">{results.best_algorithm}</p>
                <p className="text-sm text-green-700">Total Cost: {formatCurrency(results.best_total_cost)}</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Cost Savings vs LFL</h3>
                <p className="text-3xl font-bold text-blue-700">
                  {results.cost_savings_vs_lfl ? formatCurrency(results.cost_savings_vs_lfl) : 'N/A'}
                </p>
                <p className="text-sm text-blue-700">
                  {results.cost_savings_vs_lfl && results.results?.LFL
                    ? `${((results.cost_savings_vs_lfl / results.results.LFL.total_cost) * 100).toFixed(1)}% reduction`
                    : 'Baseline algorithm'}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Comparison Table */}
          <Card className="mb-6">
            <CardContent className="pt-4">
              <h3 className="text-lg font-semibold mb-4">Algorithm Comparison</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Algorithm</TableHead>
                    <TableHead className="text-right">Total Cost</TableHead>
                    <TableHead className="text-right">Setup Cost</TableHead>
                    <TableHead className="text-right">Holding Cost</TableHead>
                    <TableHead className="text-right">Orders</TableHead>
                    <TableHead className="text-right">Avg Inventory</TableHead>
                    <TableHead className="text-right">Savings vs LFL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(results.results || {}).map(([algo, result]) => {
                    const isBest = algo === results.best_algorithm;
                    const savingsVsLfl = results.results.LFL
                      ? ((results.results.LFL.total_cost - result.total_cost) / results.results.LFL.total_cost) * 100
                      : 0;

                    return (
                      <TableRow key={algo} className={isBest ? 'bg-green-50' : ''}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <strong>{algo}</strong>
                            {isBest && <Badge variant="success">Best</Badge>}
                          </div>
                        </TableCell>
                        <TableCell className="text-right font-semibold">{formatCurrency(result.total_cost)}</TableCell>
                        <TableCell className="text-right">{formatCurrency(result.setup_cost_total)}</TableCell>
                        <TableCell className="text-right">{formatCurrency(result.holding_cost_total)}</TableCell>
                        <TableCell className="text-right">{result.number_of_orders}</TableCell>
                        <TableCell className="text-right">{Math.round(result.average_inventory)}</TableCell>
                        <TableCell className="text-right">
                          {savingsVsLfl > 0 ? <Badge variant="success">{savingsVsLfl.toFixed(1)}%</Badge> : '-'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Cost Comparison Chart */}
          <Card className="mb-6">
            <CardContent className="pt-4">
              <h3 className="text-lg font-semibold mb-4">Cost Comparison</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart
                  data={Object.entries(results.results || {}).map(([algo, result]) => ({
                    algorithm: algo,
                    setupCost: result.setup_cost_total,
                    holdingCost: result.holding_cost_total,
                    totalCost: result.total_cost,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="algorithm" />
                  <YAxis />
                  <RechartsTooltip formatter={(value) => formatCurrency(value)} />
                  <Legend />
                  <Bar dataKey="setupCost" name="Setup Cost" fill="#8884d8" stackId="a" />
                  <Bar dataKey="holdingCost" name="Holding Cost" fill="#82ca9d" stackId="a" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Recommendations */}
          <Alert variant="info">
            <strong>Recommendation:</strong> The <strong>{results.best_algorithm}</strong> algorithm provides the lowest
            total cost of {formatCurrency(results.best_total_cost)}.
            {results.cost_savings_vs_lfl && (
              <>
                {' '}
                This represents a savings of {formatCurrency(results.cost_savings_vs_lfl)} (
                {((results.cost_savings_vs_lfl / (results.results?.LFL?.total_cost || 1)) * 100).toFixed(1)}%) compared
                to Lot-for-Lot ordering.
              </>
            )}
          </Alert>
        </>
      )}
    </div>
  );
};

export default LotSizingAnalysis;
