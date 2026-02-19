/**
 * System Dashboard Component
 * Phase 6 Sprint 3: Monitoring & Observability
 *
 * Displays real-time system health status, metrics, and monitoring data.
 * Features:
 * - Health status indicators for all components
 * - Real-time metrics visualization
 * - Error rate tracking
 * - System resource monitoring
 * - Auto-refresh every 5 seconds
 *
 * Migrated to Autonomy UI Kit (Tailwind CSS + lucide-react)
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Alert,
  AlertDescription,
  Spinner,
  IconButton,
} from '../common';
import {
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Info,
} from 'lucide-react';
import { api } from '../../services/api';
import HealthStatusCard from './HealthStatusCard';
import MetricsChart from './MetricsChart';

const SystemDashboard = () => {
  // State
  const [healthData, setHealthData] = useState(null);
  const [metricsData, setMetricsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Fetch health data
  const fetchHealthData = async () => {
    try {
      const response = await api.get('/health');
      setHealthData(response.data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch health data:', err);
      setError('Failed to fetch health data');
    }
  };

  // Fetch metrics data
  const fetchMetricsData = async () => {
    try {
      const response = await api.get('/metrics/json');
      setMetricsData(response.data);
    } catch (err) {
      console.error('Failed to fetch metrics data:', err);
    }
  };

  // Fetch all data
  const fetchData = async () => {
    setLoading(true);
    await Promise.all([fetchHealthData(), fetchMetricsData()]);
    setLoading(false);
    setLastUpdate(new Date());
  };

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, []);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchData();
    }, 5000);

    return () => clearInterval(interval);
  }, [autoRefresh]);

  // Manual refresh
  const handleRefresh = () => {
    fetchData();
  };

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case 'degraded':
        return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'unhealthy':
        return <XCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Info className="w-5 h-5 text-blue-500" />;
    }
  };

  // Get badge variant
  const getBadgeVariant = (status) => {
    switch (status) {
      case 'healthy':
        return 'success';
      case 'degraded':
        return 'warning';
      case 'unhealthy':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  // Format uptime
  const formatUptime = (seconds) => {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours}h ${minutes}m ${secs}s`;
  };

  // Loading state
  if (loading && !healthData) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold mb-1">System Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Real-time monitoring and observability
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 text-primary rounded border-gray-300 focus:ring-primary"
            />
            <span className="text-sm">Auto-refresh</span>
          </label>
          <IconButton
            onClick={handleRefresh}
            variant="ghost"
            size="icon"
            title="Refresh now"
          >
            <RefreshCw className="h-5 w-5 text-primary" />
          </IconButton>
          {lastUpdate && (
            <span className="text-xs text-muted-foreground">
              Last update: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription className="flex justify-between items-center">
            {error}
            <button
              onClick={() => setError(null)}
              className="text-sm underline hover:no-underline"
            >
              Dismiss
            </button>
          </AlertDescription>
        </Alert>
      )}

      {/* Overall Status Card */}
      {healthData && (
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-center">
              <div className="flex items-center gap-3">
                {getStatusIcon(healthData.status)}
                <div>
                  <h2 className="text-lg font-semibold">System Status</h2>
                  <Badge variant={getBadgeVariant(healthData.status)} size="sm">
                    {healthData.status.toUpperCase()}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Version</p>
                <p className="text-base">{healthData.version || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Uptime</p>
                <p className="text-base">
                  {formatUptime(healthData.uptime_seconds)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Timestamp</p>
                <p className="text-base">
                  {healthData.timestamp
                    ? new Date(healthData.timestamp).toLocaleString()
                    : 'N/A'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Health Checks Grid */}
      {healthData && healthData.checks && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-4">Component Health</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {healthData.checks.map((check, index) => (
              <HealthStatusCard key={index} check={check} />
            ))}
          </div>
        </div>
      )}

      <hr className="my-8 border-border" />

      {/* Metrics Section */}
      {metricsData && (
        <div>
          <h2 className="text-xl font-semibold mb-4">Metrics</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* HTTP Requests */}
            {metricsData.counters && (
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">HTTP Requests</h3>
                  <MetricsChart
                    data={metricsData.counters}
                    type="counter"
                    title="Request Count"
                    filterPrefix="http_requests_total"
                  />
                </CardContent>
              </Card>
            )}

            {/* Request Duration */}
            {metricsData.histograms && (
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">Request Duration</h3>
                  <MetricsChart
                    data={metricsData.histograms}
                    type="histogram"
                    title="Duration (ms)"
                    filterPrefix="http_request_duration"
                  />
                </CardContent>
              </Card>
            )}

            {/* Active Resources */}
            {metricsData.gauges && (
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">Active Resources</h3>
                  <MetricsChart
                    data={metricsData.gauges}
                    type="gauge"
                    title="Count"
                    filterPrefix="active_"
                  />
                </CardContent>
              </Card>
            )}

            {/* Business Metrics */}
            {metricsData.counters && (
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">Business Metrics</h3>
                  <MetricsChart
                    data={metricsData.counters}
                    type="counter"
                    title="Total"
                    filterPrefix="game_"
                  />
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* No Data State */}
      {!healthData && !metricsData && !loading && (
        <Alert variant="info">
          <AlertDescription>
            No monitoring data available. Click refresh to retry.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
};

export default SystemDashboard;
