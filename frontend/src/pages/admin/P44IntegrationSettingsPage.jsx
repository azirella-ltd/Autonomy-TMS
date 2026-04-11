/**
 * project44 Integration Settings — Connection, Webhooks, Tracking Coverage
 *
 * Data-driven configuration page for the p44 integration. All data fetched
 * from backend APIs; no hardcoded fallback values.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  useToast,
} from '../../components/common';
import {
  Globe, Wifi, WifiOff, Webhook, BarChart3, RefreshCw,
  AlertTriangle, CheckCircle, Shield, Clock,
} from 'lucide-react';

function maskClientId(id) {
  if (!id || id.length < 8) return id ?? '\u2014';
  return `${id.slice(0, 4)}${'*'.repeat(id.length - 8)}${id.slice(-4)}`;
}

const P44IntegrationSettingsPage = () => {
  const { toast } = useToast();
  const [config, setConfig] = useState(null);
  const [webhooks, setWebhooks] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const errors = [];

    try {
      const configRes = await api.get('/p44/config');
      setConfig(configRes.data);
    } catch (err) {
      if (err.response?.status === 404) {
        errors.push('project44 integration not configured for this tenant.');
      } else {
        errors.push(`Config: ${err.message}`);
      }
      setConfig(null);
    }

    try {
      const whRes = await api.get('/p44/webhooks');
      setWebhooks(Array.isArray(whRes.data) ? whRes.data : whRes.data?.items ?? []);
    } catch (err) {
      if (err.response?.status !== 404) errors.push(`Webhooks: ${err.message}`);
      setWebhooks([]);
    }

    try {
      const statsRes = await api.get('/p44/stats');
      setStats(statsRes.data);
    } catch (err) {
      if (err.response?.status !== 404) errors.push(`Stats: ${err.message}`);
      setStats(null);
    }

    if (errors.length > 0) setError(errors.join(' '));
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleTestConnection = async () => {
    setTestingConnection(true);
    try {
      const res = await api.post('/p44/test-connection');
      toast({ title: 'Connection test passed', description: res.data?.message ?? 'Successfully connected to project44.', variant: 'default' });
    } catch (err) {
      toast({ title: 'Connection test failed', description: err.response?.data?.detail ?? err.message, variant: 'destructive' });
    } finally {
      setTestingConnection(false);
    }
  };

  const cell = (val) => (val != null ? val : '\u2014');

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <h1 className="text-2xl font-bold">project44 Integration Settings</h1>
        <div className="flex justify-center py-12"><Spinner /></div>
      </div>
    );
  }

  const notConfigured = !config && !stats && webhooks.length === 0;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Globe className="h-6 w-6 text-blue-600" />
            project44 Integration Settings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Connection configuration, webhook status, and tracking coverage</p>
        </div>
        <Button variant="outline" onClick={fetchAll}>
          <RefreshCw className="h-4 w-4 mr-1" />Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {notConfigured && !error && (
        <Alert>
          <AlertDescription>
            project44 integration not configured for this tenant. Contact your administrator to set up the p44 connection credentials.
          </AlertDescription>
        </Alert>
      )}

      {/* Section 1: Connection Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-5 w-5" />
            Connection Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {config ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge className={config.connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                    {config.connected ? (
                      <><Wifi className="h-3 w-3 mr-1" />Connected</>
                    ) : (
                      <><WifiOff className="h-3 w-3 mr-1" />Disconnected</>
                    )}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Client ID</p>
                  <p className="text-sm font-mono">{maskClientId(config.client_id)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Last Authenticated</p>
                  <p className="text-sm">{cell(config.last_auth)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Token Expires</p>
                  <p className="text-sm">{cell(config.token_expires)}</p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testingConnection}
              >
                {testingConnection ? <Spinner className="h-4 w-4 mr-1" /> : <CheckCircle className="h-4 w-4 mr-1" />}
                Test Connection
              </Button>
            </div>
          ) : (
            <Alert>
              <AlertDescription>No connection configuration available. Set up project44 credentials to enable real-time visibility.</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Section 2: Webhook Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Webhook className="h-5 w-5" />
            Webhook Configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          {webhooks.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Event Type</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Received</TableHead>
                  <TableHead className="text-right">Error Count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {webhooks.map((wh, i) => (
                  <TableRow key={wh.id ?? i}>
                    <TableCell className="font-medium">{cell(wh.event_type)}</TableCell>
                    <TableCell className="font-mono text-xs max-w-[300px] truncate">{cell(wh.url)}</TableCell>
                    <TableCell>
                      <Badge className={wh.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}>
                        {cell(wh.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>{cell(wh.last_received)}</TableCell>
                    <TableCell className="text-right">{cell(wh.error_count)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Alert>
              <AlertDescription>No webhooks configured. Webhooks enable real-time shipment status updates from project44.</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Section 3: Tracking Coverage */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-5 w-5" />
            Tracking Coverage
          </CardTitle>
        </CardHeader>
        <CardContent>
          {stats ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground">Total Tracked Shipments</p>
                <p className="text-3xl font-bold mt-1">{cell(stats.total_tracked)}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground">Coverage</p>
                <p className="text-3xl font-bold mt-1">
                  {stats.coverage_pct != null ? `${stats.coverage_pct}%` : '\u2014'}
                </p>
              </div>
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground">Avg Update Frequency</p>
                <p className="text-3xl font-bold mt-1">{cell(stats.avg_update_frequency)}</p>
              </div>
            </div>
          ) : (
            <Alert>
              <AlertDescription>No tracking coverage data available. Tracking statistics will appear once shipments are being tracked via project44.</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default P44IntegrationSettingsPage;
