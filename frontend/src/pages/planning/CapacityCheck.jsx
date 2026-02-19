/**
 * Capacity Check Page
 *
 * Validates MPS plans against resource capacity constraints using RCCP
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
  Spinner,
  Textarea,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
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
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  Plus,
  Download,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';

const CapacityCheck = () => {
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(false);
  const [productionPlan, setProductionPlan] = useState('');
  const [resources, setResources] = useState([
    { id: 1, name: 'Assembly Line', unitsPerProduct: 0.5, capacity: 600, target: 85 },
    { id: 2, name: 'Labor', unitsPerProduct: 0.25, capacity: 400, target: 90 },
  ]);
  const [strategy, setStrategy] = useState('level');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const loadSamplePlan = () => {
    const sample = [1200, 900, 1000, 1100, 1250, 1150, 1300, 950, 1050, 1100, 1200, 1000, 1150];
    setProductionPlan(sample.join(', '));
  };

  useEffect(() => {
    loadSamplePlan();
  }, []);

  const handleRunCheck = async () => {
    try {
      setLoading(true);
      setError(null);

      // Parse production plan
      const plan = productionPlan
        .split(',')
        .map(q => parseFloat(q.trim()))
        .filter(q => !isNaN(q));

      if (plan.length === 0) {
        setError('Please enter a valid production plan (comma-separated numbers)');
        return;
      }

      // Call backend API
      const response = await api.post('/lot-sizing/capacity-check', {
        production_plan: plan,
        start_date: new Date().toISOString().split('T')[0],
        period_days: 7,
        resources: resources.map(r => ({
          resource_id: `resource_${r.id}`,
          resource_name: r.name,
          units_per_product: r.unitsPerProduct,
          available_capacity: r.capacity,
          utilization_target: r.target / 100, // Convert percentage to decimal
        })),
        strategy: strategy,
      });

      setResult(response.data);

    } catch (err) {
      console.error('Error running capacity check:', err);
      setError(err.response?.data?.detail || 'Failed to run capacity check. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const addResource = () => {
    setResources([
      ...resources,
      { id: resources.length + 1, name: '', unitsPerProduct: 0, capacity: 0, target: 85 },
    ]);
  };

  const updateResource = (id, field, value) => {
    setResources(resources.map(r =>
      r.id === id ? { ...r, [field]: value } : r
    ));
  };

  const removeResource = (id) => {
    setResources(resources.filter(r => r.id !== id));
  };

  const handleExportCSV = async () => {
    try {
      const plan = productionPlan
        .split(',')
        .map(q => parseFloat(q.trim()))
        .filter(q => !isNaN(q));

      const response = await api.post('/lot-sizing/capacity-check/export/csv', {
        production_plan: plan,
        start_date: new Date().toISOString().split('T')[0],
        period_days: 7,
        resources: resources.map(r => ({
          resource_id: `resource_${r.id}`,
          resource_name: r.name,
          units_per_product: r.unitsPerProduct,
          available_capacity: r.capacity,
          utilization_target: r.target / 100,
        })),
        strategy: strategy,
      }, {
        responseType: 'blob'
      });

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'capacity_check_results.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Error exporting CSV:', err);
      setError('Failed to export CSV. Please try again.');
    }
  };

  const getUtilizationColor = (utilization) => {
    if (utilization >= 95) return 'destructive';
    if (utilization >= 85) return 'warning';
    return 'success';
  };

  const getUtilizationIcon = (utilization) => {
    if (utilization >= 95) return <XCircle className="h-5 w-5 text-destructive" />;
    if (utilization >= 85) return <AlertTriangle className="h-5 w-5 text-amber-500" />;
    return <CheckCircle className="h-5 w-5 text-green-500" />;
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
        <h1 className="text-2xl font-bold">Capacity-Constrained MPS Check</h1>
        <p className="text-sm text-muted-foreground">
          Validate production plans against resource capacity using Rough-Cut Capacity Planning (RCCP)
        </p>
      </div>

      {/* Input Section */}
      <div className="grid grid-cols-1 lg:grid-cols-7 gap-6 mb-6">
        <Card className="lg:col-span-4">
          <CardContent className="pt-4">
            <h2 className="text-lg font-semibold mb-4">Production Plan</h2>
            <Textarea
              value={productionPlan}
              onChange={(e) => setProductionPlan(e.target.value)}
              placeholder="Enter weekly production quantities (comma-separated)"
              rows={3}
              className="mb-2"
            />
            <p className="text-xs text-muted-foreground mb-4">
              Enter production quantities separated by commas
            </p>
            <div className="flex items-center gap-4">
              <Button
                variant="outline"
                size="sm"
                onClick={loadSamplePlan}
              >
                Load Sample Plan
              </Button>
              <div className="flex items-center gap-2">
                <Label htmlFor="strategy" className="whitespace-nowrap">Leveling Strategy</Label>
                <Select value={strategy} onValueChange={setStrategy}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Select strategy" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="level">Level Production</SelectItem>
                    <SelectItem value="shift">Shift Earlier</SelectItem>
                    <SelectItem value="reduce">Reduce to Capacity</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardContent className="pt-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Resource Requirements</h2>
              <Button
                size="sm"
                variant="outline"
                onClick={addResource}
                leftIcon={<Plus className="h-4 w-4" />}
              >
                Add Resource
              </Button>
            </div>
            <div className="space-y-4">
              {resources.map((resource) => (
                <Card key={resource.id} className="border">
                  <CardContent className="pt-4">
                    <div className="grid grid-cols-1 gap-3">
                      <div>
                        <Label className="text-xs">Resource Name</Label>
                        <Input
                          value={resource.name}
                          onChange={(e) => updateResource(resource.id, 'name', e.target.value)}
                          className="h-8"
                        />
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <Label className="text-xs">Units/Product</Label>
                          <Input
                            type="number"
                            value={resource.unitsPerProduct}
                            onChange={(e) => updateResource(resource.id, 'unitsPerProduct', parseFloat(e.target.value))}
                            className="h-8"
                          />
                        </div>
                        <div>
                          <Label className="text-xs">Capacity</Label>
                          <Input
                            type="number"
                            value={resource.capacity}
                            onChange={(e) => updateResource(resource.id, 'capacity', parseFloat(e.target.value))}
                            className="h-8"
                          />
                        </div>
                        <div>
                          <Label className="text-xs">Target %</Label>
                          <Input
                            type="number"
                            value={resource.target}
                            onChange={(e) => updateResource(resource.id, 'target', parseFloat(e.target.value))}
                            className="h-8"
                          />
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Run Button */}
      <div className="flex justify-center gap-4 mb-6">
        <Button
          size="lg"
          variant="warning"
          onClick={handleRunCheck}
          disabled={loading}
          leftIcon={loading ? <Spinner size="sm" /> : <Play className="h-5 w-5" />}
        >
          {loading ? 'Checking...' : 'Check Capacity Constraints'}
        </Button>
        {result && (
          <Button
            variant="outline"
            size="lg"
            onClick={handleExportCSV}
            leftIcon={<Download className="h-5 w-5" />}
          >
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
      {result && (
        <>
          {/* Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card className={result.isFeasible ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Feasibility Status</h3>
                <div className="flex items-center gap-2">
                  {result.isFeasible ? (
                    <CheckCircle className="h-12 w-12 text-green-600" />
                  ) : (
                    <XCircle className="h-12 w-12 text-red-600" />
                  )}
                  <span className="text-lg font-medium">
                    {result.isFeasible ? 'Plan is Feasible' : 'Capacity Constrained'}
                  </span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Bottleneck Resources</h3>
                <p className="text-3xl font-bold">{result.bottleneckResources.length}</p>
                <p className="text-sm text-muted-foreground">
                  {result.bottleneckResources.join(', ') || 'None'}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Production Adjustment</h3>
                <p className="text-3xl font-bold">{result.totalShortage.toFixed(0)}</p>
                <p className="text-sm text-muted-foreground">
                  Units reduced to meet capacity
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Capacity Utilization Chart */}
          <Card className="mb-6">
            <CardContent className="pt-4">
              <h3 className="text-lg font-semibold mb-4">Resource Utilization by Period</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart
                  data={result.checks
                    .filter(c => c.resource === resources[0]?.name)
                    .map((c, idx) => ({
                      period: `Week ${c.period + 1}`,
                      utilization: c.utilization,
                      target: resources.find(r => r.name === c.resource)?.target || 85,
                    }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" />
                  <YAxis label={{ value: 'Utilization (%)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="utilization"
                    stroke="#8884d8"
                    strokeWidth={2}
                    name="Utilization"
                  />
                  <Line
                    type="monotone"
                    dataKey="target"
                    stroke="#82ca9d"
                    strokeDasharray="5 5"
                    name="Target"
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Recommendations */}
          <Card className="mb-6">
            <CardContent className="pt-4">
              <h3 className="text-lg font-semibold mb-4">Recommendations</h3>
              <ul className="space-y-2">
                {result.recommendations.map((rec, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    {rec.includes('Bottleneck') || rec.includes('reduced') ? (
                      <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
                    ) : (
                      <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                    )}
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {/* Production Plan Comparison */}
          <Card>
            <CardContent className="pt-4">
              <h3 className="text-lg font-semibold mb-4">Production Plan Comparison</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Period</TableHead>
                    <TableHead className="text-right">Original Plan</TableHead>
                    <TableHead className="text-right">Feasible Plan</TableHead>
                    <TableHead className="text-right">Adjustment</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.originalPlan.map((qty, idx) => {
                    const feasible = result.feasiblePlan[idx];
                    const adjustment = qty - feasible;

                    return (
                      <TableRow key={idx}>
                        <TableCell>Week {idx + 1}</TableCell>
                        <TableCell className="text-right">{qty.toFixed(0)}</TableCell>
                        <TableCell className="text-right">{feasible.toFixed(0)}</TableCell>
                        <TableCell className="text-right">
                          {adjustment > 0 ? (
                            <Badge variant="warning">-{adjustment.toFixed(0)}</Badge>
                          ) : (
                            <Badge variant="success">OK</Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};

export default CapacityCheck;
