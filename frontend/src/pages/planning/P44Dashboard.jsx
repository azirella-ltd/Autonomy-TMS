import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  Wifi, WifiOff, RefreshCw, ShieldCheck, Clock, Truck, Ship,
  Plane, TrainFront, Activity, AlertTriangle, CheckCircle, XCircle, Send,
} from 'lucide-react';

const EVENT_TYPES = ['SHIPMENT_UPDATE', 'ETA_UPDATE', 'EXCEPTION', 'MILESTONE', 'TRACKING_LOST'];

const eventBadgeVariant = (type) => {
  switch (type) {
    case 'EXCEPTION': return 'destructive';
    case 'TRACKING_LOST': return 'destructive';
    case 'ETA_UPDATE': return 'secondary';
    case 'MILESTONE': return 'outline';
    default: return 'default';
  }
};

const statusBadge = (status) => {
  switch (status) {
    case 'Connected':
      return <Badge variant="default" className="bg-green-600 text-white"><CheckCircle className="w-3 h-3 mr-1" />{status}</Badge>;
    case 'Disconnected':
      return <Badge variant="secondary"><WifiOff className="w-3 h-3 mr-1" />{status}</Badge>;
    case 'Error':
      return <Badge variant="destructive"><XCircle className="w-3 h-3 mr-1" />{status}</Badge>;
    default:
      return <Badge variant="outline">{status || '\u2014'}</Badge>;
  }
};

const webhookStatusBadge = (status) => {
  switch (status) {
    case 'Active': return <Badge variant="default" className="bg-green-600 text-white">{status}</Badge>;
    case 'Inactive': return <Badge variant="secondary">{status}</Badge>;
    case 'Error': return <Badge variant="destructive">{status}</Badge>;
    default: return <Badge variant="outline">{status || '\u2014'}</Badge>;
  }
};

function maskClientId(id) {
  if (!id) return '\u2014';
  return id.substring(0, 4) + '****';
}

function formatTimestamp(ts) {
  if (!ts) return '\u2014';
  return new Date(ts).toLocaleString();
}

function timeSince(ts) {
  if (!ts) return '\u2014';
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.round(diff / 3600000)}h ago`;
  return `${Math.round(diff / 86400000)}d ago`;
}

const P44Dashboard = () => {
  const [status, setStatus] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [webhooks, setWebhooks] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [refreshingToken, setRefreshingToken] = useState(false);
  const [testingWebhook, setTestingWebhook] = useState(null);
  const eventsTimerRef = useRef(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const results = await Promise.allSettled([
      api.get('/p44/status'),
      api.get('/p44/coverage'),
      api.get('/p44/webhooks'),
      api.get('/p44/events/recent'),
    ]);

    const [statusRes, coverageRes, webhooksRes, eventsRes] = results;

    // If all fail with 404, p44 is not configured
    const all404 = results.every(
      (r) => r.status === 'rejected' && r.reason?.response?.status === 404
    );
    if (all404) {
      setError('project44 integration not configured. Contact your administrator to set up the connection.');
      setLoading(false);
      return;
    }

    if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data);
    if (coverageRes.status === 'fulfilled') setCoverage(coverageRes.value.data);
    if (webhooksRes.status === 'fulfilled') setWebhooks(webhooksRes.value.data || []);
    if (eventsRes.status === 'fulfilled') setEvents(eventsRes.value.data || []);

    // Show first non-404 error if any
    const firstError = results.find(
      (r) => r.status === 'rejected' && r.reason?.response?.status !== 404
    );
    if (firstError) {
      const err = firstError.reason;
      setError(err.response?.data?.detail || err.message || 'Failed to load p44 data');
    }

    setLoading(false);
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await api.get('/p44/events/recent');
      setEvents(res.data || []);
    } catch {
      // silent — events refresh is best-effort
    }
  }, []);

  useEffect(() => {
    fetchAll();
    eventsTimerRef.current = setInterval(fetchEvents, 30000);
    return () => clearInterval(eventsTimerRef.current);
  }, [fetchAll, fetchEvents]);

  const testConnection = async () => {
    setTestingConnection(true);
    try {
      const res = await api.post('/p44/test-connection');
      setStatus((prev) => ({ ...prev, ...res.data }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Connection test failed');
    } finally {
      setTestingConnection(false);
    }
  };

  const refreshToken = async () => {
    setRefreshingToken(true);
    try {
      const res = await api.post('/p44/refresh-token');
      setStatus((prev) => ({ ...prev, ...res.data }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Token refresh failed');
    } finally {
      setRefreshingToken(false);
    }
  };

  const testWebhook = async (eventType) => {
    setTestingWebhook(eventType);
    try {
      await api.post('/p44/webhooks/test', { event_type: eventType });
    } catch (err) {
      setError(err.response?.data?.detail || `Webhook test failed for ${eventType}`);
    } finally {
      setTestingWebhook(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  const connectionStatus = status?.status || 'Disconnected';

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">project44 Integration</h1>
          {statusBadge(connectionStatus)}
        </div>
        <Button variant="ghost" size="sm" onClick={fetchAll}>
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh All
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* 2-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Section 1: Connection Health */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wifi className="w-4 h-4" /> Connection Health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {connectionStatus === 'Disconnected' && !status && (
              <Alert>
                <AlertDescription>
                  project44 is not connected. Configure your Client ID and Secret in the
                  TMS Data Management settings, then test the connection.
                </AlertDescription>
              </Alert>
            )}
            <div className="grid grid-cols-2 gap-2">
              <span className="text-muted-foreground">Status</span>
              <span>{statusBadge(connectionStatus)}</span>
              <span className="text-muted-foreground">Client ID</span>
              <span className="font-mono text-xs">{maskClientId(status?.client_id)}</span>
              <span className="text-muted-foreground">Last Auth</span>
              <span>{formatTimestamp(status?.last_auth)}</span>
              <span className="text-muted-foreground">Token Expiry</span>
              <span>
                {status?.token_expiry
                  ? timeSince(status.token_expiry).includes('ago')
                    ? <Badge variant="destructive">Expired</Badge>
                    : formatTimestamp(status.token_expiry)
                  : '\u2014'}
              </span>
            </div>
            <div className="flex gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={testConnection}
                disabled={testingConnection}
              >
                {testingConnection ? <Spinner className="w-3 h-3 mr-1" /> : <ShieldCheck className="w-3 h-3 mr-1" />}
                Test Connection
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshToken}
                disabled={refreshingToken}
              >
                {refreshingToken ? <Spinner className="w-3 h-3 mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
                Refresh Token
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Tracking Coverage */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="w-4 h-4" /> Tracking Coverage
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <span className="text-muted-foreground">Tracked Shipments</span>
              <span className="font-semibold">{coverage?.total_tracked != null ? coverage.total_tracked : '\u2014'}</span>
              <span className="text-muted-foreground">Coverage Rate</span>
              <span className="font-semibold">
                {coverage?.coverage_rate != null ? `${(coverage.coverage_rate * 100).toFixed(1)}%` : '\u2014'}
              </span>
              <span className="text-muted-foreground">Avg Update Freq</span>
              <span>
                {coverage?.avg_update_frequency_min != null
                  ? `${coverage.avg_update_frequency_min.toFixed(0)} min`
                  : '\u2014'}
              </span>
              <span className="text-muted-foreground">Data Freshness</span>
              <span>{coverage?.last_tracking_update ? timeSince(coverage.last_tracking_update) : '\u2014'}</span>
            </div>

            {/* Mode breakdown bars */}
            <div className="space-y-2 pt-2">
              <span className="text-xs font-medium text-muted-foreground">Coverage by Mode</span>
              {[
                { key: 'road_pct', label: 'Road', icon: Truck },
                { key: 'ocean_pct', label: 'Ocean', icon: Ship },
                { key: 'rail_pct', label: 'Rail', icon: TrainFront },
                { key: 'air_pct', label: 'Air', icon: Plane },
              ].map(({ key, label, icon: Icon }) => {
                const val = coverage?.[key];
                return (
                  <div key={key} className="flex items-center gap-2 text-xs">
                    <Icon className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                    <span className="w-12">{label}</span>
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      {val != null && (
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${Math.min(val * 100, 100)}%` }}
                        />
                      )}
                    </div>
                    <span className="w-10 text-right">{val != null ? `${(val * 100).toFixed(0)}%` : '\u2014'}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Section 3: Webhook Status — full width */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Send className="w-4 h-4" /> Webhook Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            {webhooks.length === 0 ? (
              <Alert>
                <AlertDescription>
                  No webhooks configured. Set up webhook endpoints in project44 to receive
                  real-time shipment updates, ETA changes, and exception alerts.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event Type</TableHead>
                      <TableHead>Endpoint URL</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Last Received</TableHead>
                      <TableHead>Success Rate</TableHead>
                      <TableHead>Errors</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {webhooks.map((wh, i) => (
                      <TableRow key={wh.event_type || i}>
                        <TableCell className="font-mono text-xs">{wh.event_type || '\u2014'}</TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate">{wh.endpoint_url || '\u2014'}</TableCell>
                        <TableCell>{webhookStatusBadge(wh.status)}</TableCell>
                        <TableCell className="text-xs">{formatTimestamp(wh.last_received)}</TableCell>
                        <TableCell className="text-xs">
                          {wh.success_rate != null ? `${(wh.success_rate * 100).toFixed(1)}%` : '\u2014'}
                        </TableCell>
                        <TableCell className="text-xs">{wh.error_count != null ? wh.error_count : '\u2014'}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => testWebhook(wh.event_type)}
                            disabled={testingWebhook === wh.event_type}
                          >
                            {testingWebhook === wh.event_type
                              ? <Spinner className="w-3 h-3" />
                              : 'Test'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Section 4: Recent Events Feed — takes second column on last row but full if webhooks spans */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="w-4 h-4" /> Recent Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <Alert>
                <AlertDescription>
                  No recent events. Verify that webhook endpoints are configured and that
                  project44 is actively sending tracking updates.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="max-h-[300px] overflow-y-auto space-y-1">
                {events.map((evt, i) => (
                  <div
                    key={evt.id || i}
                    className="flex items-start gap-2 p-2 border rounded text-xs hover:bg-muted/50"
                  >
                    <span className="text-muted-foreground whitespace-nowrap flex-shrink-0">
                      {formatTimestamp(evt.timestamp)}
                    </span>
                    <Badge variant={eventBadgeVariant(evt.event_type)} className="flex-shrink-0">
                      {evt.event_type || '\u2014'}
                    </Badge>
                    <span className="font-mono flex-shrink-0">{evt.shipment_ref || '\u2014'}</span>
                    <span className="text-muted-foreground truncate">{evt.description || ''}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default P44Dashboard;
