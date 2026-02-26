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
  ToggleGroup,
  ToggleGroupItem,
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
import { Shield, TrendingUp, DollarSign, Star, Download } from 'lucide-react';
import AnalyticsSummaryCard from './AnalyticsSummaryCard';
import simulationApi from '../../services/api';

const PolicyEffectiveness = ({ configId, tenantId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    fetchMetrics();
  }, [configId, tenantId]);

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);

    const result = await simulationApi.getPolicyEffectiveness(configId, tenantId);

    if (result.success) {
      setMetrics(result.data);
    } else {
      setError(result.error);
    }

    setLoading(false);
  };

  const handleFilterChange = (newFilter) => {
    if (newFilter) {
      setFilterType(newFilter);
    }
  };

  const getFilteredPolicies = () => {
    if (!metrics || !metrics.policies) return [];
    if (filterType === 'all') return metrics.policies;
    return metrics.policies.filter(p => p.type === filterType);
  };

  const getAggregationPolicies = () => {
    if (!metrics || !metrics.policies) return [];
    return metrics.policies.filter(p => p.type === 'aggregation');
  };

  const getMostUsedPolicy = () => {
    const aggPolicies = getAggregationPolicies();
    if (aggPolicies.length === 0) return null;
    return aggPolicies.reduce((max, p) => p.usage_count > max.usage_count ? p : max);
  };

  const getHighestSavingsPolicy = () => {
    const aggPolicies = getAggregationPolicies();
    if (aggPolicies.length === 0) return null;
    return aggPolicies.reduce((max, p) => p.total_savings > max.total_savings ? p : max);
  };

  const getAvgEffectivenessScore = () => {
    const aggPolicies = getAggregationPolicies();
    if (aggPolicies.length === 0) return 0;
    const sum = aggPolicies.reduce((acc, p) => acc + p.effectiveness_score, 0);
    return (sum / aggPolicies.length).toFixed(1);
  };

  const prepareChartData = () => {
    const aggPolicies = getAggregationPolicies();
    return aggPolicies.map(p => ({
      name: `${p.from_site} → ${p.to_site}`,
      'Usage Count': p.usage_count,
      'Total Savings': p.total_savings
    }));
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

  if (!metrics || !metrics.policies || metrics.policies.length === 0) {
    return (
      <div className="p-6">
        <Alert>
          <AlertDescription>No policy data available for this configuration.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const mostUsedPolicy = getMostUsedPolicy();
  const highestSavingsPolicy = getHighestSavingsPolicy();
  const chartData = prepareChartData();

  const handleExportCSV = () => {
    simulationApi.exportPoliciesCSV(configId, tenantId);
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
          title="Total Policies"
          value={metrics.policies.length}
          subtitle={`${getAggregationPolicies().length} aggregation, ${metrics.policies.length - getAggregationPolicies().length} capacity`}
          icon={Shield}
          color="primary"
        />
        <AnalyticsSummaryCard
          title="Most Used"
          value={mostUsedPolicy ? `${mostUsedPolicy.usage_count}x` : 'N/A'}
          subtitle={mostUsedPolicy ? `${mostUsedPolicy.from_site} → ${mostUsedPolicy.to_site}` : 'No data'}
          icon={TrendingUp}
          color="info"
        />
        <AnalyticsSummaryCard
          title="Highest Savings"
          value={highestSavingsPolicy ? `$${highestSavingsPolicy.total_savings.toFixed(2)}` : 'N/A'}
          subtitle={highestSavingsPolicy ? `${highestSavingsPolicy.from_site} → ${highestSavingsPolicy.to_site}` : 'No data'}
          icon={DollarSign}
          color="success"
        />
        <AnalyticsSummaryCard
          title="Avg Effectiveness"
          value={getAvgEffectivenessScore()}
          subtitle="Effectiveness score"
          icon={Star}
          color="warning"
        />
      </div>

      {/* Charts Row */}
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Policy Usage Chart */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Policy Usage Count</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                  <YAxis label={{ value: 'Usage Count', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Usage Count" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Cost Savings by Policy */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Cost Savings by Policy</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                  <YAxis label={{ value: 'Total Savings ($)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip formatter={(value) => `$${value.toFixed(2)}`} />
                  <Legend />
                  <Bar dataKey="Total Savings" fill="#22c55e" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Policy Effectiveness Table */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">Policy Effectiveness Details</h3>
            <ToggleGroup
              type="single"
              value={filterType}
              onValueChange={handleFilterChange}
              size="sm"
            >
              <ToggleGroupItem value="all">All</ToggleGroupItem>
              <ToggleGroupItem value="aggregation">Aggregation</ToggleGroupItem>
              <ToggleGroupItem value="capacity">Capacity</ToggleGroupItem>
            </ToggleGroup>
          </div>

          <div className="border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Policy ID</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Route/Site</TableHead>
                  <TableHead className="text-right">Usage Count</TableHead>
                  <TableHead className="text-right">Total Savings</TableHead>
                  <TableHead className="text-right">Avg Savings/Use</TableHead>
                  <TableHead className="text-right">Effectiveness Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {getFilteredPolicies().map((policy) => (
                  <TableRow key={policy.policy_id}>
                    <TableCell>{policy.policy_id}</TableCell>
                    <TableCell>
                      <Badge variant={policy.type === 'aggregation' ? 'default' : 'secondary'}>
                        {policy.type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {policy.type === 'aggregation' ? (
                        `${policy.from_site} → ${policy.to_site}`
                      ) : (
                        policy.site
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.type === 'aggregation' ? policy.usage_count : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.type === 'aggregation' ? `$${policy.total_savings.toFixed(2)}` : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.type === 'aggregation' ? `$${policy.avg_savings_per_use.toFixed(2)}` : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.type === 'aggregation' ? (
                        <Badge
                          variant={
                            policy.effectiveness_score >= 50 ? 'success' :
                            policy.effectiveness_score >= 20 ? 'warning' :
                            'destructive'
                          }
                        >
                          {policy.effectiveness_score.toFixed(0)}
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          {policy.capacity ? `${policy.capacity.toFixed(0)} units` : '-'}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default PolicyEffectiveness;
