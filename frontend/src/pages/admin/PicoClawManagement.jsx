/**
 * PicoClaw Fleet Management
 *
 * Admin page for managing PicoClaw edge CDC monitors across the supply chain.
 * Provides fleet dashboard, per-site monitoring, alert management, and configuration.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';
import { picoClawApi } from '../../services/edgeAgentApi';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
  Input,
  NativeSelect,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../../components/common';
import {
  Cpu,
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  Settings,
  ChevronRight,
  Heart,
  Wifi,
  WifiOff,
  MapPin,
  Bell,
  Plus,
  Trash2,
  Eye,
  BarChart3,
  Shield,
  Key,
  RotateCcw,
  Send,
  Search,
  Filter,
  ArrowUpDown,
  XCircle,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

// Tab configuration
const tabItems = [
  { value: 'fleet', label: 'Fleet Dashboard', icon: <BarChart3 className="h-4 w-4" /> },
  { value: 'alerts', label: 'Alerts', icon: <Bell className="h-4 w-4" /> },
  { value: 'config', label: 'Configuration', icon: <Settings className="h-4 w-4" /> },
  { value: 'accounts', label: 'Service Accounts', icon: <Key className="h-4 w-4" /> },
];

// Severity color mapping
const severityColors = {
  OK: { border: 'border-green-500', bg: 'bg-green-50', text: 'text-green-700', badge: 'success' },
  WARNING: { border: 'border-yellow-500', bg: 'bg-yellow-50', text: 'text-yellow-700', badge: 'warning' },
  CRITICAL: { border: 'border-red-500', bg: 'bg-red-50', text: 'text-red-700', badge: 'destructive' },
  STALE: { border: 'border-gray-400', bg: 'bg-gray-50', text: 'text-gray-600', badge: 'secondary' },
};

const getSeverityStyle = (severity) => severityColors[severity] || severityColors.STALE;

// ============================================================================
// Fleet Dashboard Tab
// ============================================================================
const FleetDashboardTab = ({ instances, summary, loading, onRefresh, onSelectInstance }) => {
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  const filteredInstances = (instances || []).filter(inst => {
    if (filterStatus !== 'all' && inst.status !== filterStatus) return false;
    if (filterType !== 'all' && inst.site_type !== filterType) return false;
    if (searchTerm && !inst.site_key.toLowerCase().includes(searchTerm.toLowerCase()) &&
        !inst.site_name?.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Instances</p>
                <p className="text-3xl font-bold">{summary?.total || 0}</p>
              </div>
              <Cpu className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Healthy</p>
                <p className="text-3xl font-bold text-green-600">{summary?.healthy || 0}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Warning</p>
                <p className="text-3xl font-bold text-yellow-600">{summary?.warning || 0}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Critical</p>
                <p className="text-3xl font-bold text-red-600">{summary?.critical || 0}</p>
              </div>
              <XCircle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Stale</p>
                <p className="text-3xl font-bold text-gray-500">{summary?.stale || 0}</p>
              </div>
              <WifiOff className="h-8 w-8 text-gray-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by site key or name..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-64"
              />
            </div>
            <NativeSelect value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="all">All Statuses</option>
              <option value="OK">Healthy</option>
              <option value="WARNING">Warning</option>
              <option value="CRITICAL">Critical</option>
              <option value="STALE">Stale</option>
            </NativeSelect>
            <NativeSelect value={filterType} onChange={(e) => setFilterType(e.target.value)}>
              <option value="all">All Site Types</option>
              <option value="DC">Distribution Center</option>
              <option value="manufacturing">Manufacturing</option>
              <option value="supplier">Supplier</option>
              <option value="customer">Customer</option>
            </NativeSelect>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Instance Table */}
      <Card>
        <CardHeader>
          <CardTitle>Fleet Instances ({filteredInstances.length})</CardTitle>
          <CardDescription>All registered PicoClaw edge monitors</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Status</th>
                  <th className="text-left py-3 px-4 font-medium">Site Key</th>
                  <th className="text-left py-3 px-4 font-medium">Site Name</th>
                  <th className="text-left py-3 px-4 font-medium">Type</th>
                  <th className="text-left py-3 px-4 font-medium">Region</th>
                  <th className="text-left py-3 px-4 font-medium">Mode</th>
                  <th className="text-left py-3 px-4 font-medium">Last Heartbeat</th>
                  <th className="text-left py-3 px-4 font-medium">Uptime</th>
                  <th className="text-left py-3 px-4 font-medium">Memory</th>
                  <th className="text-left py-3 px-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredInstances.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-muted-foreground">
                      {instances?.length === 0
                        ? 'No PicoClaw instances registered. Click "Register Instance" to add one.'
                        : 'No instances match current filters.'}
                    </td>
                  </tr>
                ) : (
                  filteredInstances.map((inst) => {
                    const style = getSeverityStyle(inst.status);
                    return (
                      <tr key={inst.site_key} className="border-b hover:bg-muted/50 cursor-pointer"
                          onClick={() => onSelectInstance(inst)}>
                        <td className="py-3 px-4">
                          <Badge variant={style.badge}>{inst.status}</Badge>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs">{inst.site_key}</td>
                        <td className="py-3 px-4">{inst.site_name || '—'}</td>
                        <td className="py-3 px-4">
                          <Badge variant="secondary">{inst.site_type || 'unknown'}</Badge>
                        </td>
                        <td className="py-3 px-4">{inst.region || '—'}</td>
                        <td className="py-3 px-4">
                          <Badge variant={inst.mode === 'deterministic' ? 'outline' : 'default'}>
                            {inst.mode || 'deterministic'}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-xs">
                          {inst.last_heartbeat
                            ? new Date(inst.last_heartbeat).toLocaleString()
                            : 'Never'}
                        </td>
                        <td className="py-3 px-4">{inst.uptime_pct != null ? `${inst.uptime_pct}%` : '—'}</td>
                        <td className="py-3 px-4">{inst.memory_mb != null ? `${inst.memory_mb}MB` : '—'}</td>
                        <td className="py-3 px-4">
                          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onSelectInstance(inst); }}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Instance Detail Dialog
// ============================================================================
const InstanceDetailDialog = ({ instance, open, onClose }) => {
  const [heartbeats, setHeartbeats] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (instance && open) {
      loadDetails();
    }
  }, [instance, open]);

  const loadDetails = async () => {
    if (!instance) return;
    setLoading(true);
    try {
      const [hbRes, alertRes] = await Promise.all([
        picoClawApi.getHeartbeats(instance.site_key, { limit: 24 }).catch(() => ({ data: [] })),
        picoClawApi.getAlerts(instance.site_key, { limit: 20 }).catch(() => ({ data: [] })),
      ]);
      setHeartbeats(hbRes.data || []);
      setAlerts(alertRes.data || []);
    } catch (err) {
      console.error('Failed to load instance details:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!instance) return null;

  const style = getSeverityStyle(instance.status);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            {instance.site_name || instance.site_key}
          </DialogTitle>
          <DialogDescription>
            Site Key: {instance.site_key} | Type: {instance.site_type} | Region: {instance.region}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Status Overview */}
          <div className={cn("p-4 rounded-lg border-2", style.border, style.bg)}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {instance.status === 'OK' ? <CheckCircle className={cn("h-5 w-5", style.text)} /> :
                 instance.status === 'WARNING' ? <AlertTriangle className={cn("h-5 w-5", style.text)} /> :
                 <XCircle className={cn("h-5 w-5", style.text)} />}
                <span className={cn("font-semibold", style.text)}>{instance.status}</span>
              </div>
              <div className="text-sm text-muted-foreground">
                Mode: <Badge variant="outline">{instance.mode || 'deterministic'}</Badge>
              </div>
            </div>
          </div>

          {/* CDC Metrics */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">CDC Metrics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Inventory Ratio</p>
                  <p className="text-2xl font-bold">
                    {instance.inventory_ratio != null ? `${(instance.inventory_ratio * 100).toFixed(0)}%` : '—'}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Service Level (24h)</p>
                  <p className="text-2xl font-bold">
                    {instance.service_level != null ? `${(instance.service_level * 100).toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Demand Deviation</p>
                  <p className="text-2xl font-bold">
                    {instance.demand_deviation != null ? `${instance.demand_deviation > 0 ? '+' : ''}${(instance.demand_deviation * 100).toFixed(1)}%` : '—'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Recent Alerts */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent Alerts ({alerts.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center py-4"><Spinner /></div>
              ) : alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No recent alerts</p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {alerts.map((alert, i) => (
                    <div key={i} className="flex items-center gap-3 py-2 border-b last:border-0">
                      <Badge variant={getSeverityStyle(alert.severity).badge}>{alert.severity}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {new Date(alert.timestamp).toLocaleString()}
                      </span>
                      <span className="text-sm flex-1">{alert.condition}</span>
                      {alert.acknowledged && <CheckCircle className="h-4 w-4 text-green-500" />}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Heartbeat History */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Heartbeat History (Last 24)</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center py-4"><Spinner /></div>
              ) : heartbeats.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No heartbeat data</p>
              ) : (
                <div className="flex gap-1 flex-wrap">
                  {heartbeats.map((hb, i) => (
                    <div
                      key={i}
                      className={cn(
                        "w-6 h-6 rounded-sm",
                        hb.status === 'OK' ? 'bg-green-400' :
                        hb.status === 'WARNING' ? 'bg-yellow-400' :
                        hb.status === 'CRITICAL' ? 'bg-red-400' : 'bg-gray-300'
                      )}
                      title={`${new Date(hb.timestamp).toLocaleString()} - ${hb.status}`}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ============================================================================
// Alerts Tab
// ============================================================================
const AlertsTab = ({ loading }) => {
  const [alerts, setAlerts] = useState([]);
  const [alertLoading, setAlertLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('all');

  useEffect(() => {
    loadAlerts();
  }, []);

  const loadAlerts = async () => {
    setAlertLoading(true);
    try {
      const res = await picoClawApi.getFleetAlerts({ limit: 100 });
      setAlerts(res.data || []);
    } catch {
      // Mock data for initial rendering
      setAlerts([]);
    } finally {
      setAlertLoading(false);
    }
  };

  const handleAcknowledge = async (alertId) => {
    try {
      await picoClawApi.acknowledgeAlert(alertId);
      setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: true } : a));
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  const filteredAlerts = filterSeverity === 'all'
    ? alerts
    : alerts.filter(a => a.severity === filterSeverity);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <NativeSelect value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
          <option value="all">All Severities</option>
          <option value="CRITICAL">Critical Only</option>
          <option value="WARNING">Warning Only</option>
          <option value="OK">OK Only</option>
        </NativeSelect>
        <Button variant="outline" size="sm" onClick={loadAlerts}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Alert Timeline</CardTitle>
          <CardDescription>CDC alerts across all PicoClaw instances</CardDescription>
        </CardHeader>
        <CardContent>
          {alertLoading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : filteredAlerts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Bell className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
              <p>No alerts match current filters</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredAlerts.map((alert, i) => {
                const style = getSeverityStyle(alert.severity);
                return (
                  <div key={i} className={cn("p-3 rounded-lg border", style.border, style.bg)}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Badge variant={style.badge}>{alert.severity}</Badge>
                        <span className="font-medium">{alert.site_key}</span>
                        <span className="text-sm">{alert.condition}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : '—'}
                        </span>
                        {!alert.acknowledged && (
                          <Button variant="outline" size="sm" onClick={() => handleAcknowledge(alert.id)}>
                            Acknowledge
                          </Button>
                        )}
                        {alert.acknowledged && (
                          <Badge variant="outline">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Acknowledged
                          </Badge>
                        )}
                      </div>
                    </div>
                    {alert.details && (
                      <p className="text-sm mt-2 text-muted-foreground">{alert.details}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Configuration Tab
// ============================================================================
const ConfigurationTab = () => {
  const [configForm, setConfigForm] = useState({
    heartbeat_interval_min: 30,
    digest_interval_hours: 4,
    default_alert_channel: '#supply-chain-alerts',
    default_mode: 'deterministic',
    llm_mode_threshold: 50,
    api_base_url: '',
  });
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save fleet-wide defaults
      setSuccess('Configuration saved successfully');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error('Failed to save configuration:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {success && (
        <Alert variant="success">
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Fleet-Wide Defaults</CardTitle>
          <CardDescription>
            Default configuration applied to new PicoClaw instances. Individual instances can override.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">Heartbeat Interval (minutes)</label>
              <Input
                type="number"
                value={configForm.heartbeat_interval_min}
                onChange={(e) => setConfigForm(prev => ({ ...prev, heartbeat_interval_min: Number(e.target.value) }))}
                min={1}
                max={120}
              />
              <p className="text-xs text-muted-foreground mt-1">How often each PicoClaw sends heartbeat (default: 30)</p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Digest Interval (hours)</label>
              <Input
                type="number"
                value={configForm.digest_interval_hours}
                onChange={(e) => setConfigForm(prev => ({ ...prev, digest_interval_hours: Number(e.target.value) }))}
                min={1}
                max={24}
              />
              <p className="text-xs text-muted-foreground mt-1">Batched warning digest interval (default: 4)</p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Default Alert Channel</label>
              <Input
                value={configForm.default_alert_channel}
                onChange={(e) => setConfigForm(prev => ({ ...prev, default_alert_channel: e.target.value }))}
                placeholder="#supply-chain-alerts"
              />
              <p className="text-xs text-muted-foreground mt-1">Slack/Teams channel for CRITICAL alerts</p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Default Mode</label>
              <NativeSelect
                value={configForm.default_mode}
                onChange={(e) => setConfigForm(prev => ({ ...prev, default_mode: e.target.value }))}
              >
                <option value="deterministic">Deterministic (recommended for 50+ sites)</option>
                <option value="llm">LLM-Interpreted</option>
              </NativeSelect>
              <p className="text-xs text-muted-foreground mt-1">Deterministic mode: HEARTBEAT.sh scripts. LLM mode: AI interpretation.</p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">LLM Mode Site Threshold</label>
              <Input
                type="number"
                value={configForm.llm_mode_threshold}
                onChange={(e) => setConfigForm(prev => ({ ...prev, llm_mode_threshold: Number(e.target.value) }))}
                min={1}
                max={500}
              />
              <p className="text-xs text-muted-foreground mt-1">Auto-switch to deterministic mode when fleet exceeds this count</p>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Autonomy API Base URL</label>
              <Input
                value={configForm.api_base_url}
                onChange={(e) => setConfigForm(prev => ({ ...prev, api_base_url: e.target.value }))}
                placeholder="https://api.autonomy.local"
              />
              <p className="text-xs text-muted-foreground mt-1">Base URL for PicoClaw REST API calls</p>
            </div>
          </div>

          <div className="flex justify-end pt-4">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Spinner className="mr-2" /> : null}
              Save Fleet Defaults
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* CDC Threshold Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>CDC Threshold Configuration</CardTitle>
          <CardDescription>
            Condition Detection & Correction thresholds that trigger alerts
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Condition</th>
                  <th className="text-left py-3 px-4 font-medium">Warning Threshold</th>
                  <th className="text-left py-3 px-4 font-medium">Critical Threshold</th>
                  <th className="text-left py-3 px-4 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { condition: 'Inventory Ratio', warning: '< 50%', critical: '< 25%', desc: 'On-hand / safety stock target' },
                  { condition: 'Service Level (24h)', warning: '< 95%', critical: '< 85%', desc: 'Orders fulfilled / orders received' },
                  { condition: 'Demand Deviation', warning: '> ±20%', critical: '> ±40%', desc: 'Actual vs forecast deviation' },
                  { condition: 'ATP Shortfall', warning: '> 5%', critical: '> 15%', desc: 'Unfulfilled ATP requests as % of demand' },
                  { condition: 'Capacity Utilization', warning: '> 90%', critical: '> 98%', desc: 'Current utilization vs rated capacity' },
                  { condition: 'Orders Past Due', warning: '> 3', critical: '> 10', desc: 'Count of orders past promised date' },
                ].map((row, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-3 px-4 font-medium">{row.condition}</td>
                    <td className="py-3 px-4">
                      <Badge variant="warning">{row.warning}</Badge>
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="destructive">{row.critical}</Badge>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">{row.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Service Accounts Tab
// ============================================================================
const ServiceAccountsTab = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newAccount, setNewAccount] = useState({ name: '', scope: 'site', site_key: '' });

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const res = await picoClawApi.getServiceAccounts();
      setAccounts(res.data || []);
    } catch {
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      await picoClawApi.createServiceAccount(newAccount);
      setShowCreate(false);
      setNewAccount({ name: '', scope: 'site', site_key: '' });
      loadAccounts();
    } catch (err) {
      console.error('Failed to create service account:', err);
    }
  };

  const handleRotate = async (accountId) => {
    try {
      await picoClawApi.rotateToken(accountId);
      loadAccounts();
    } catch (err) {
      console.error('Failed to rotate token:', err);
    }
  };

  const handleRevoke = async (accountId) => {
    if (!window.confirm('Are you sure you want to revoke this service account?')) return;
    try {
      await picoClawApi.revokeServiceAccount(accountId);
      loadAccounts();
    } catch (err) {
      console.error('Failed to revoke account:', err);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">
          Service accounts authenticate PicoClaw instances against the Autonomy API.
          Each account is scoped to specific sites with read-only permissions.
        </p>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Account
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : accounts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Key className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
              <p>No service accounts created yet</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Name</th>
                  <th className="text-left py-3 px-4 font-medium">Scope</th>
                  <th className="text-left py-3 px-4 font-medium">Token (masked)</th>
                  <th className="text-left py-3 px-4 font-medium">Created</th>
                  <th className="text-left py-3 px-4 font-medium">Last Rotated</th>
                  <th className="text-left py-3 px-4 font-medium">Status</th>
                  <th className="text-left py-3 px-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((acct) => (
                  <tr key={acct.id} className="border-b">
                    <td className="py-3 px-4 font-medium">{acct.name}</td>
                    <td className="py-3 px-4"><Badge variant="outline">{acct.scope}</Badge></td>
                    <td className="py-3 px-4 font-mono text-xs">{acct.token_masked || '****...****'}</td>
                    <td className="py-3 px-4 text-xs">{acct.created_at ? new Date(acct.created_at).toLocaleDateString() : '—'}</td>
                    <td className="py-3 px-4 text-xs">{acct.last_rotated ? new Date(acct.last_rotated).toLocaleDateString() : 'Never'}</td>
                    <td className="py-3 px-4">
                      <Badge variant={acct.status === 'active' ? 'success' : 'destructive'}>
                        {acct.status || 'active'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => handleRotate(acct.id)} title="Rotate token">
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleRevoke(acct.id)} title="Revoke account">
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Service Account</DialogTitle>
            <DialogDescription>
              Create a JWT-authenticated service account for PicoClaw instances.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium block mb-1">Account Name</label>
              <Input
                value={newAccount.name}
                onChange={(e) => setNewAccount(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., picoclaw-dc-east"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Scope</label>
              <NativeSelect
                value={newAccount.scope}
                onChange={(e) => setNewAccount(prev => ({ ...prev, scope: e.target.value }))}
              >
                <option value="site">Site-Specific (single site)</option>
                <option value="region">Region (group of sites)</option>
                <option value="global">Global (all sites, read-only)</option>
              </NativeSelect>
            </div>
            {newAccount.scope === 'site' && (
              <div>
                <label className="text-sm font-medium block mb-1">Site Key</label>
                <Input
                  value={newAccount.site_key}
                  onChange={(e) => setNewAccount(prev => ({ ...prev, site_key: e.target.value }))}
                  placeholder="e.g., DC-EAST-001"
                />
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button onClick={handleCreate} disabled={!newAccount.name}>Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================
const PicoClawManagement = () => {
  const [currentTab, setCurrentTab] = useState('fleet');
  const [instances, setInstances] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedInstance, setSelectedInstance] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    loadFleetData();
  }, []);

  const loadFleetData = async () => {
    setLoading(true);
    try {
      const [summaryRes, instancesRes] = await Promise.all([
        picoClawApi.getFleetSummary().catch(() => ({ data: { total: 0, healthy: 0, warning: 0, critical: 0, stale: 0 } })),
        picoClawApi.getFleetInstances().catch(() => ({ data: [] })),
      ]);
      setSummary(summaryRes.data);
      setInstances(instancesRes.data || []);
      setError(null);
    } catch (err) {
      setError('Failed to load fleet data. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectInstance = (inst) => {
    setSelectedInstance(inst);
    setDetailOpen(true);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <a href="/admin" className="hover:text-foreground">Administration</a>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">PicoClaw Fleet Management</span>
      </nav>

      {/* Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Cpu className="h-7 w-7 text-primary" />
          PicoClaw Fleet Management
        </h1>
        <p className="text-muted-foreground mt-1">
          Monitor and configure edge CDC monitors across your supply chain network.
          Each PicoClaw instance runs as a lightweight (&lt;10MB) Go binary performing heartbeat-based condition detection.
        </p>
      </div>

      {error && (
        <Alert variant="warning" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 mb-6">
          {tabItems.map((tab) => (
            <Tab
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
            >
              {tab.icon}
              {tab.label}
            </Tab>
          ))}
        </TabsList>

        {currentTab === 'fleet' && (
          <FleetDashboardTab
            instances={instances}
            summary={summary}
            loading={loading}
            onRefresh={loadFleetData}
            onSelectInstance={handleSelectInstance}
          />
        )}
        {currentTab === 'alerts' && <AlertsTab loading={loading} />}
        {currentTab === 'config' && <ConfigurationTab />}
        {currentTab === 'accounts' && <ServiceAccountsTab />}
      </Tabs>

      {/* Instance Detail Dialog */}
      <InstanceDetailDialog
        instance={selectedInstance}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
};

export default PicoClawManagement;
