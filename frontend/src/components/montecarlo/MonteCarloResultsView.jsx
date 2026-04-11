import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import {
  LineChart,
  Line,
  Area,
  AreaChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
} from 'recharts';
import { Card, CardContent } from '../common/Card';
import { Button, IconButton } from '../common/Button';
import { Alert, AlertTitle } from '../common/Alert';
import { Badge } from '../common/Badge';
import { Tabs, TabsList, Tab, TabPanel } from '../common/Tabs';
import { Spinner } from '../common/Loading';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableContainer,
} from '../common/Table';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { api } from '../../services/api';

const MonteCarloResultsView = ({ run, onBack }) => {
  const [currentTab, setCurrentTab] = useState('summary');
  const [timeSeriesData, setTimeSeriesData] = useState([]);
  const [riskAlerts, setRiskAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadResultsData();
  }, [run.id]);

  const loadResultsData = async () => {
    try {
      setLoading(true);

      // Load time-series data
      const tsResponse = await api.get(`/monte-carlo/runs/${run.id}/time-series`);
      setTimeSeriesData(tsResponse.data);

      // Load risk alerts
      const alertsResponse = await api.get(`/monte-carlo/runs/${run.id}/risk-alerts`);
      setRiskAlerts(alertsResponse.data);
    } catch (error) {
      console.error('Error loading results:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAcknowledgeAlert = async (alertId) => {
    try {
      await api.post(`/monte-carlo/runs/${run.id}/risk-alerts/${alertId}/acknowledge`);
      loadResultsData();
    } catch (error) {
      console.error('Error acknowledging alert:', error);
    }
  };

  // Render Summary Statistics
  const renderSummaryStats = () => {
    if (!run.summary_statistics) return null;

    const stats = run.summary_statistics;

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Cost */}
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-1">Total Cost</p>
            <p className="text-2xl font-bold mb-2">
              ${stats.total_cost?.mean?.toFixed(0) || 0}
            </p>
            <div className="flex justify-between mt-2">
              <span className="text-xs text-muted-foreground">
                P5: ${stats.total_cost?.p5?.toFixed(0) || 0}
              </span>
              <span className="text-xs text-muted-foreground">
                P95: ${stats.total_cost?.p95?.toFixed(0) || 0}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Std Dev: ${stats.total_cost?.std?.toFixed(0) || 0}
            </p>
          </CardContent>
        </Card>

        {/* Service Level */}
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-1">Service Level</p>
            <p className="text-2xl font-bold mb-2">
              {stats.service_level?.mean?.toFixed(1) || 0}%
            </p>
            <div className="flex justify-between mt-2">
              <span className="text-xs text-muted-foreground">
                P5: {stats.service_level?.p5?.toFixed(1) || 0}%
              </span>
              <span className="text-xs text-muted-foreground">
                P95: {stats.service_level?.p95?.toFixed(1) || 0}%
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Final Inventory */}
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-1">Final Inventory</p>
            <p className="text-2xl font-bold mb-2">
              {stats.final_inventory?.mean?.toFixed(0) || 0}
            </p>
            <div className="flex justify-between mt-2">
              <span className="text-xs text-muted-foreground">
                P5: {stats.final_inventory?.p5?.toFixed(0) || 0}
              </span>
              <span className="text-xs text-muted-foreground">
                P95: {stats.final_inventory?.p95?.toFixed(0) || 0}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Final Backlog */}
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-1">Final Backlog</p>
            <p className="text-2xl font-bold mb-2">
              {stats.final_backlog?.mean?.toFixed(0) || 0}
            </p>
            <div className="flex justify-between mt-2">
              <span className="text-xs text-muted-foreground">
                P5: {stats.final_backlog?.p5?.toFixed(0) || 0}
              </span>
              <span className="text-xs text-muted-foreground">
                P95: {stats.final_backlog?.p95?.toFixed(0) || 0}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  };

  // Render Risk Metrics
  const renderRiskMetrics = () => {
    if (!run.risk_metrics) return null;

    const risks = run.risk_metrics;

    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
        <Card className={cn(risks.stockout_probability > 0.1 && 'bg-orange-50 dark:bg-orange-950/20')}>
          <CardContent>
            <div className="flex items-center mb-2">
              {risks.stockout_probability > 0.1 ? (
                <AlertTriangle className="h-5 w-5 text-orange-500 mr-2" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-emerald-500 mr-2" />
              )}
              <span className="text-sm font-semibold">Stockout Risk</span>
            </div>
            <p className="text-3xl font-bold">
              {(risks.stockout_probability * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground">
              Probability of stockout occurring
            </p>
          </CardContent>
        </Card>

        <Card className={cn(risks.overstock_probability > 0.2 && 'bg-orange-50 dark:bg-orange-950/20')}>
          <CardContent>
            <div className="flex items-center mb-2">
              {risks.overstock_probability > 0.2 ? (
                <AlertTriangle className="h-5 w-5 text-orange-500 mr-2" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-emerald-500 mr-2" />
              )}
              <span className="text-sm font-semibold">Overstock Risk</span>
            </div>
            <p className="text-3xl font-bold">
              {(risks.overstock_probability * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground">
              Probability of excess inventory
            </p>
          </CardContent>
        </Card>

        <Card
          className={cn(
            risks.capacity_violation_probability > 0.05 && 'bg-orange-50 dark:bg-orange-950/20'
          )}
        >
          <CardContent>
            <div className="flex items-center mb-2">
              {risks.capacity_violation_probability > 0.05 ? (
                <AlertTriangle className="h-5 w-5 text-orange-500 mr-2" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-emerald-500 mr-2" />
              )}
              <span className="text-sm font-semibold">Capacity Risk</span>
            </div>
            <p className="text-3xl font-bold">
              {(risks.capacity_violation_probability * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground">
              Probability of capacity violations
            </p>
          </CardContent>
        </Card>
      </div>
    );
  };

  // Render Time Series Chart with Confidence Bands
  const renderTimeSeriesChart = (metricData) => {
    if (!metricData || metricData.data_points.length === 0) return null;

    const data = metricData.data_points.map((point) => ({
      week: point.week,
      mean: point.mean,
      p5: point.p5,
      p25: point.p25,
      p75: point.p75,
      p95: point.p95,
      min: point.min,
      max: point.max,
    }));

    return (
      <Card className="mb-6">
        <CardContent className="p-6">
          <h3 className="text-lg font-semibold mb-4">
            {metricData.metric_name.replace(/_/g, ' ').toUpperCase()}
          </h3>
          <ResponsiveContainer width="100%" height={400}>
            <ComposedChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="week" label={{ value: 'Week', position: 'insideBottom', offset: -5 }} />
              <YAxis label={{ value: 'Quantity', angle: -90, position: 'insideLeft' }} />
              <RechartsTooltip />
              <Legend />

              {/* P5-P95 confidence band (lightest) */}
              <Area
                type="monotone"
                dataKey="p95"
                fill="#2196f3"
                fillOpacity={0.1}
                stroke="none"
                name="P5-P95 Band"
              />
              <Area
                type="monotone"
                dataKey="p5"
                fill="#ffffff"
                fillOpacity={1}
                stroke="none"
              />

              {/* P25-P75 confidence band (darker) */}
              <Area
                type="monotone"
                dataKey="p75"
                fill="#2196f3"
                fillOpacity={0.2}
                stroke="none"
                name="P25-P75 Band"
              />
              <Area
                type="monotone"
                dataKey="p25"
                fill="#ffffff"
                fillOpacity={1}
                stroke="none"
              />

              {/* Mean line */}
              <Line
                type="monotone"
                dataKey="mean"
                stroke="#1976d2"
                strokeWidth={2}
                dot={false}
                name="Mean"
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-6 mt-4">
            <div className="flex items-center">
              <div className="w-5 h-2.5 bg-blue-500/10 mr-2" />
              <span className="text-xs text-muted-foreground">P5-P95 Range</span>
            </div>
            <div className="flex items-center">
              <div className="w-5 h-2.5 bg-blue-500/30 mr-2" />
              <span className="text-xs text-muted-foreground">P25-P75 Range</span>
            </div>
            <div className="flex items-center">
              <div className="w-5 h-0.5 bg-blue-600 mr-2" />
              <span className="text-xs text-muted-foreground">Mean Value</span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  // Render Risk Alerts
  const renderRiskAlerts = () => {
    const unacknowledgedAlerts = riskAlerts.filter((a) => !a.acknowledged);
    const acknowledgedAlerts = riskAlerts.filter((a) => a.acknowledged);

    const getSeverityVariant = (severity) => {
      switch (severity) {
        case 'critical':
          return 'destructive';
        case 'high':
          return 'warning';
        case 'medium':
          return 'info';
        case 'low':
          return 'secondary';
        default:
          return 'secondary';
      }
    };

    const getAlertVariant = (severity) => {
      switch (severity) {
        case 'critical':
          return 'error';
        case 'high':
          return 'warning';
        case 'medium':
          return 'info';
        case 'low':
          return 'default';
        default:
          return 'default';
      }
    };

    return (
      <div>
        {unacknowledgedAlerts.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-4">
              Active Alerts ({unacknowledgedAlerts.length})
            </h3>
            {unacknowledgedAlerts.map((alert) => (
              <Alert
                key={alert.id}
                variant={getAlertVariant(alert.severity)}
                className="mb-4"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <AlertTitle className="flex items-center gap-2">
                      {alert.title}
                      <Badge variant={getSeverityVariant(alert.severity)} size="sm">
                        {alert.severity.toUpperCase()}
                      </Badge>
                    </AlertTitle>
                    <p className="text-sm mt-2">{alert.description}</p>
                    {alert.recommendation && (
                      <p className="text-sm font-semibold mt-2">
                        Recommendation: {alert.recommendation}
                      </p>
                    )}
                    {alert.probability && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Probability: {(alert.probability * 100).toFixed(1)}%
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleAcknowledgeAlert(alert.id)}
                  >
                    Acknowledge
                  </Button>
                </div>
              </Alert>
            ))}
          </div>
        )}

        {acknowledgedAlerts.length > 0 && (
          <div>
            <h3 className="text-lg font-semibold mb-4 text-muted-foreground">
              Acknowledged Alerts ({acknowledgedAlerts.length})
            </h3>
            <TableContainer>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Severity</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Probability</TableHead>
                    <TableHead>Acknowledged</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {acknowledgedAlerts.map((alert) => (
                    <TableRow key={alert.id}>
                      <TableCell>
                        <Badge variant={getSeverityVariant(alert.severity)} size="sm">
                          {alert.severity}
                        </Badge>
                      </TableCell>
                      <TableCell>{alert.title}</TableCell>
                      <TableCell>
                        {alert.probability ? `${(alert.probability * 100).toFixed(1)}%` : '-'}
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-muted-foreground">
                          {new Date(alert.acknowledged_at).toLocaleString()}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </div>
        )}

        {riskAlerts.length === 0 && (
          <Alert variant="success">
            <AlertTitle>No Risk Alerts</AlertTitle>
            All metrics are within acceptable ranges. No action required.
          </Alert>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center mb-6">
        <IconButton onClick={onBack} className="mr-4">
          <ArrowLeft className="h-5 w-5" />
        </IconButton>
        <div>
          <h2 className="text-xl font-bold">{run.name}</h2>
          <p className="text-sm text-muted-foreground">
            {run.num_scenarios} scenarios - {run.planning_horizon_weeks} weeks - Completed{' '}
            {new Date(run.completed_at).toLocaleString()}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Card className="mb-6" padding="none">
        <Tabs value={currentTab} onChange={(e, newValue) => setCurrentTab(newValue)}>
          <TabsList className="border-b border-border">
            <Tab value="summary" label="Summary" />
            <Tab value="timeseries" label="Time Series" />
            <Tab value="alerts" label="Risk Alerts" />
          </TabsList>
        </Tabs>
      </Card>

      {/* Tab Content */}
      {currentTab === 'summary' && (
        <div>
          {renderSummaryStats()}
          {renderRiskMetrics()}
        </div>
      )}

      {currentTab === 'timeseries' && (
        <div>
          {timeSeriesData.length === 0 ? (
            <Alert variant="info">No time-series data available for this simulation.</Alert>
          ) : (
            timeSeriesData.map((metricData) => (
              <div key={`${metricData.metric_name}_${metricData.product_id}_${metricData.site_id}`}>
                {renderTimeSeriesChart(metricData)}
              </div>
            ))
          )}
        </div>
      )}

      {currentTab === 'alerts' && <div>{renderRiskAlerts()}</div>}
    </div>
  );
};

export default MonteCarloResultsView;
