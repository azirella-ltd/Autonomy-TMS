import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Modal,
  Progress,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/common';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  RefreshCw,
  Plus,
  Trash2,
  Eye,
  Bell,
  Mail,
  MessageSquare,
  Settings,
  Edit2,
} from 'lucide-react';
import { format } from 'date-fns';
import { api } from '../../services/api';

const RiskAnalysis = () => {
  // State management
  const [alerts, setAlerts] = useState([]);
  const [watchlists, setWatchlists] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('INFORMED');

  // Dialog states
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [alertDetailOpen, setAlertDetailOpen] = useState(false);
  const [watchlistDialogOpen, setWatchlistDialogOpen] = useState(false);
  const [watchlistForm, setWatchlistForm] = useState({
    name: '',
    description: '',
    stockout_threshold: 60,
    overstock_threshold_days: 90,
    enable_notifications: true,
    notification_frequency: 'DAILY'
  });

  // Tab state
  const [tabValue, setTabValue] = useState('alerts');

  // Alert rules state
  const [alertRules, setAlertRules] = useState([
    { id: 1, name: 'Critical Stockout Alert', type: 'STOCKOUT', severity: 'CRITICAL', threshold: 80, condition: 'above', metric: 'stockout_probability', enabled: true, channels: ['email', 'in_app'], escalateAfterHours: 4 },
    { id: 2, name: 'High Overstock Warning', type: 'OVERSTOCK', severity: 'HIGH', threshold: 120, condition: 'above', metric: 'days_of_supply', enabled: true, channels: ['in_app'], escalateAfterHours: 24 },
    { id: 3, name: 'Vendor Lead Time Drift', type: 'VENDOR_LEADTIME', severity: 'MEDIUM', threshold: 15, condition: 'above', metric: 'lead_time_variance_pct', enabled: true, channels: ['email', 'slack'], escalateAfterHours: 48 },
    { id: 4, name: 'Low Inventory Coverage', type: 'STOCKOUT', severity: 'HIGH', threshold: 7, condition: 'below', metric: 'days_of_coverage', enabled: false, channels: ['email'], escalateAfterHours: 12 },
  ]);
  const [ruleDialogOpen, setRuleDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [ruleForm, setRuleForm] = useState({
    name: '', type: 'STOCKOUT', severity: 'HIGH', threshold: 0, condition: 'above', metric: 'stockout_probability', enabled: true, channels: ['in_app'], escalateAfterHours: 24,
  });

  // Notification channels state
  const [notifChannels, setNotifChannels] = useState([
    { id: 'email', name: 'Email', type: 'email', config: { address: 'alerts@company.com' }, enabled: true },
    { id: 'in_app', name: 'In-App', type: 'in_app', config: {}, enabled: true },
    { id: 'slack', name: 'Slack', type: 'slack', config: { webhook: 'https://hooks.slack.com/services/...' }, enabled: false },
  ]);

  // Fetch risk alerts
  const fetchAlerts = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (severityFilter !== 'ALL') params.severity = severityFilter;
      if (typeFilter !== 'ALL') params.alert_type = typeFilter;

      if (statusFilter === 'COMPLETED') {
        // Fetch INSPECTED + OVERRIDDEN separately and merge
        const [inspected, overridden] = await Promise.all([
          api.get('/risk-analysis/alerts', { params: { ...params, status: 'INSPECTED' } }),
          api.get('/risk-analysis/alerts', { params: { ...params, status: 'OVERRIDDEN' } }),
        ]);
        setAlerts([...(inspected.data || []), ...(overridden.data || [])]);
      } else if (statusFilter !== 'ALL') {
        params.status = statusFilter;
        const response = await api.get('/risk-analysis/alerts', { params });
        setAlerts(response.data);
      } else {
        const response = await api.get('/risk-analysis/alerts', { params });
        setAlerts(response.data);
      }
    } catch (err) {
      console.error('Failed to fetch risk alerts:', err);
      setError('Failed to load risk alerts. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Fetch watchlists
  const fetchWatchlists = async () => {
    try {
      const response = await api.get('/risk-analysis/watchlists');
      setWatchlists(response.data);
    } catch (err) {
      console.error('Failed to fetch watchlists:', err);
    }
  };

  // Generate alerts
  const generateAlerts = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.post('/risk-analysis/generate-alerts');
      const r = response.data;
      const parts = [`${r.new_alerts} new alerts`];
      if (r.updated_alerts) parts.push(`${r.updated_alerts} updated`);
      if (r.auto_resolved) parts.push(`${r.auto_resolved} auto-resolved`);
      setSuccess(parts.join(', ') + '.');
      await fetchAlerts();
    } catch (err) {
      console.error('Failed to generate alerts:', err);
      setError('Failed to generate alerts. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Acknowledge alert
  const acknowledgeAlert = async (alertId) => {
    try {
      await api.post(`/risk-analysis/alerts/${alertId}/acknowledge`, {});
      setSuccess('Alert acknowledged successfully');
      await fetchAlerts();
      setAlertDetailOpen(false);
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
      setError('Failed to acknowledge alert');
    }
  };

  // Resolve alert
  const resolveAlert = async (alertId, notes) => {
    try {
      await api.post(`/risk-analysis/alerts/${alertId}/resolve`, {
        resolution_notes: notes
      });
      setSuccess('Alert resolved successfully');
      await fetchAlerts();
      setAlertDetailOpen(false);
    } catch (err) {
      console.error('Failed to resolve alert:', err);
      setError('Failed to resolve alert');
    }
  };

  // Create watchlist
  const createWatchlist = async () => {
    try {
      await api.post('/risk-analysis/watchlists', watchlistForm);
      setSuccess('Watchlist created successfully');
      setWatchlistDialogOpen(false);
      setWatchlistForm({
        name: '',
        description: '',
        stockout_threshold: 60,
        overstock_threshold_days: 90,
        enable_notifications: true,
        notification_frequency: 'DAILY'
      });
      await fetchWatchlists();
    } catch (err) {
      console.error('Failed to create watchlist:', err);
      setError('Failed to create watchlist');
    }
  };

  // Delete watchlist
  const deleteWatchlist = async (id) => {
    if (!window.confirm('Are you sure you want to delete this watchlist?')) return;

    try {
      await api.delete(`/risk-analysis/watchlists/${id}`);
      setSuccess('Watchlist deleted successfully');
      await fetchWatchlists();
    } catch (err) {
      console.error('Failed to delete watchlist:', err);
      setError('Failed to delete watchlist');
    }
  };

  // Load data on mount
  useEffect(() => {
    fetchAlerts();
    fetchWatchlists();
  }, [severityFilter, typeFilter, statusFilter]);

  // Helper functions
  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'CRITICAL':
        return <XCircle className="h-5 w-5 text-red-500" />;
      case 'HIGH':
        return <AlertTriangle className="h-5 w-5 text-amber-500" />;
      case 'MEDIUM':
        return <Info className="h-5 w-5 text-blue-500" />;
      case 'LOW':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      default:
        return null;
    }
  };

  const getSeverityVariant = (severity) => {
    switch (severity) {
      case 'CRITICAL':
        return 'destructive';
      case 'HIGH':
        return 'warning';
      case 'MEDIUM':
        return 'info';
      case 'LOW':
        return 'success';
      default:
        return 'secondary';
    }
  };

  const getTypeLabel = (type) => {
    switch (type) {
      case 'STOCKOUT':
        return 'Stock-out Risk';
      case 'OVERSTOCK':
        return 'Overstock Risk';
      case 'VENDOR_LEADTIME':
        return 'Vendor Lead Time';
      default:
        return type;
    }
  };

  // Alert detail dialog
  const AlertDetailDialog = () => {
    if (!selectedAlert) return null;

    return (
      <Modal
        isOpen={alertDetailOpen}
        onClose={() => setAlertDetailOpen(false)}
        title={
          <div className="flex items-center gap-2">
            {getSeverityIcon(selectedAlert.severity)}
            <span>Risk Alert Details</span>
          </div>
        }
        maxWidth="lg"
      >
        <div className="space-y-4">
          <Alert variant={getSeverityVariant(selectedAlert.severity)}>
            <AlertDescription>{selectedAlert.message}</AlertDescription>
          </Alert>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Product ID</p>
              <p className="font-medium">{selectedAlert.product_id}</p>
            </div>

            <div>
              <p className="text-sm text-muted-foreground">Site ID</p>
              <p className="font-medium">{selectedAlert.site_id}</p>
            </div>

            <div>
              <p className="text-sm text-muted-foreground">Alert Type</p>
              <Badge variant="secondary">{getTypeLabel(selectedAlert.type)}</Badge>
            </div>

            <div>
              <p className="text-sm text-muted-foreground">Severity</p>
              <Badge variant={getSeverityVariant(selectedAlert.severity)}>
                {selectedAlert.severity}
              </Badge>
            </div>

            {selectedAlert.probability && (
              <div>
                <p className="text-sm text-muted-foreground">Probability</p>
                <p className="font-medium">{selectedAlert.probability.toFixed(1)}%</p>
              </div>
            )}

            {selectedAlert.days_until_stockout !== null && (
              <div>
                <p className="text-sm text-muted-foreground">Days Until Stock-out</p>
                <p className="font-medium">{selectedAlert.days_until_stockout} days</p>
              </div>
            )}

            {selectedAlert.days_of_supply && (
              <div>
                <p className="text-sm text-muted-foreground">Days of Supply</p>
                <p className="font-medium">{selectedAlert.days_of_supply.toFixed(1)} days</p>
              </div>
            )}

            {selectedAlert.excess_quantity && (
              <div>
                <p className="text-sm text-muted-foreground">Excess Quantity</p>
                <p className="font-medium">{selectedAlert.excess_quantity.toFixed(2)} units</p>
              </div>
            )}
          </div>

          <div>
            <p className="text-sm text-muted-foreground mb-1">Recommended Action</p>
            <p>{selectedAlert.recommended_action}</p>
          </div>

          {selectedAlert.factors && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Risk Factors</p>
              <div className="bg-muted/50 p-4 rounded-md">
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(selectedAlert.factors).map(([key, value]) => (
                    <div key={key}>
                      <p className="text-xs text-muted-foreground uppercase">
                        {key.replace(/_/g, ' ')}
                      </p>
                      <p className="text-sm font-medium">
                        {typeof value === 'number' ? value.toFixed(2) : value}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {selectedAlert.resolution_condition && (
            <div>
              <p className="text-sm text-muted-foreground mb-1">Auto-Resolution Condition</p>
              <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 p-3 rounded-md">
                <p className="text-sm">{selectedAlert.resolution_condition.description}</p>
              </div>
            </div>
          )}

          {selectedAlert.resolution_notes && (
            <div>
              <p className="text-sm text-muted-foreground mb-1">Resolution Notes</p>
              <p className="text-sm">{selectedAlert.resolution_notes}</p>
            </div>
          )}

          <div>
            <p className="text-sm text-muted-foreground">Created</p>
            <p className="text-sm">{format(new Date(selectedAlert.created_at), 'PPpp')}</p>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          {selectedAlert.status === 'INFORMED' && (
            <>
              <Button
                variant="outline"
                onClick={() => acknowledgeAlert(selectedAlert.alert_id)}
              >
                Inspect (No Action Needed)
              </Button>
              <Button
                variant="default"
                onClick={() => {
                  const notes = window.prompt('Enter override reason:');
                  if (notes) resolveAlert(selectedAlert.alert_id, notes);
                }}
              >
                Override (Take Action)
              </Button>
            </>
          )}
          <Button variant="ghost" onClick={() => setAlertDetailOpen(false)}>
            Close
          </Button>
        </div>
      </Modal>
    );
  };

  // Watchlist dialog
  const WatchlistDialog = () => (
    <Modal
      isOpen={watchlistDialogOpen}
      onClose={() => setWatchlistDialogOpen(false)}
      title="Create Watchlist"
      maxWidth="md"
    >
      <div className="space-y-4">
        <div>
          <Label htmlFor="watchlist-name">Name</Label>
          <Input
            id="watchlist-name"
            value={watchlistForm.name}
            onChange={(e) => setWatchlistForm({ ...watchlistForm, name: e.target.value })}
            required
          />
        </div>

        <div>
          <Label htmlFor="watchlist-description">Description</Label>
          <Textarea
            id="watchlist-description"
            rows={2}
            value={watchlistForm.description}
            onChange={(e) => setWatchlistForm({ ...watchlistForm, description: e.target.value })}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="stockout-threshold">Stock-out Threshold (%)</Label>
            <Input
              id="stockout-threshold"
              type="number"
              min={0}
              max={100}
              value={watchlistForm.stockout_threshold}
              onChange={(e) => setWatchlistForm({ ...watchlistForm, stockout_threshold: parseFloat(e.target.value) })}
            />
          </div>

          <div>
            <Label htmlFor="overstock-threshold">Overstock Threshold (days)</Label>
            <Input
              id="overstock-threshold"
              type="number"
              min={1}
              value={watchlistForm.overstock_threshold_days}
              onChange={(e) => setWatchlistForm({ ...watchlistForm, overstock_threshold_days: parseFloat(e.target.value) })}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="notification-frequency">Notification Frequency</Label>
          <Select
            value={watchlistForm.notification_frequency}
            onValueChange={(value) => setWatchlistForm({ ...watchlistForm, notification_frequency: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="REALTIME">Real-time</SelectItem>
              <SelectItem value="HOURLY">Hourly</SelectItem>
              <SelectItem value="DAILY">Daily</SelectItem>
              <SelectItem value="WEEKLY">Weekly</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex justify-end gap-2 mt-6">
        <Button variant="ghost" onClick={() => setWatchlistDialogOpen(false)}>
          Cancel
        </Button>
        <Button
          onClick={createWatchlist}
          disabled={!watchlistForm.name}
        >
          Create
        </Button>
      </div>
    </Modal>
  );

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Risk Analysis & Insights</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={fetchAlerts}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={generateAlerts}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Generate Alerts
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription className="flex justify-between items-center">
            {error}
            <Button variant="ghost" size="sm" onClick={() => setError(null)}>×</Button>
          </AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4">
          <AlertDescription className="flex justify-between items-center">
            {success}
            <Button variant="ghost" size="sm" onClick={() => setSuccess(null)}>×</Button>
          </AlertDescription>
        </Alert>
      )}

      {loading && <Progress className="mb-4" />}

      <Tabs value={tabValue} onValueChange={setTabValue} className="mb-6">
        <TabsList>
          <TabsTrigger value="alerts">Risk Alerts</TabsTrigger>
          <TabsTrigger value="watchlists">Watchlists</TabsTrigger>
          <TabsTrigger value="rules">Alert Rules & Channels</TabsTrigger>
        </TabsList>
      </Tabs>

      {tabValue === 'alerts' && (
        <>
          {/* Filters */}
          <Card className="mb-6">
            <CardContent className="pt-6">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <Label htmlFor="severity-filter">Severity</Label>
                  <Select value={severityFilter} onValueChange={setSeverityFilter}>
                    <SelectTrigger id="severity-filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ALL">All Severities</SelectItem>
                      <SelectItem value="CRITICAL">Critical</SelectItem>
                      <SelectItem value="HIGH">High</SelectItem>
                      <SelectItem value="MEDIUM">Medium</SelectItem>
                      <SelectItem value="LOW">Low</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="type-filter">Type</Label>
                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger id="type-filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ALL">All Types</SelectItem>
                      <SelectItem value="STOCKOUT">Stock-out</SelectItem>
                      <SelectItem value="OVERSTOCK">Overstock</SelectItem>
                      <SelectItem value="VENDOR_LEADTIME">Vendor Lead Time</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="status-filter">Status</Label>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger id="status-filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="INFORMED">Needs Attention</SelectItem>
                      <SelectItem value="COMPLETED">Completed</SelectItem>
                      <SelectItem value="ACTIONED">Auto-Resolved</SelectItem>
                      <SelectItem value="ALL">All</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Alerts table */}
          <Card>
            <CardContent className="pt-6">
              <h2 className="text-lg font-semibold mb-4">
                Risk Alerts ({alerts.length})
              </h2>
              <div className="border rounded-md">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Severity</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead>Site</TableHead>
                      <TableHead>Message</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {alerts.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-center text-muted-foreground">
                          No alerts found
                        </TableCell>
                      </TableRow>
                    ) : (
                      alerts.map((alert) => (
                        <TableRow key={alert.id}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              {getSeverityIcon(alert.severity)}
                              <Badge variant={getSeverityVariant(alert.severity)}>
                                {alert.severity}
                              </Badge>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{getTypeLabel(alert.type)}</Badge>
                          </TableCell>
                          <TableCell>{alert.product_id}</TableCell>
                          <TableCell>{alert.site_id}</TableCell>
                          <TableCell>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <p className="max-w-[250px] truncate text-sm">
                                    {alert.message}
                                  </p>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="max-w-xs">{alert.recommended_action}</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={
                              alert.status === 'INFORMED' ? 'border-blue-500 text-blue-700 bg-blue-50' :
                              alert.status === 'ACTIONED' ? 'border-green-500 text-green-700 bg-green-50' :
                              alert.status === 'INSPECTED' ? 'border-gray-500 text-gray-700 bg-gray-50' :
                              alert.status === 'OVERRIDDEN' ? 'border-amber-500 text-amber-700 bg-amber-50' : ''
                            }>
                              {alert.status === 'INFORMED' ? 'Needs Attention' :
                               alert.status === 'ACTIONED' ? 'Auto-Resolved' :
                               alert.status === 'INSPECTED' ? 'Inspected' :
                               alert.status === 'OVERRIDDEN' ? 'Overridden' : alert.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {format(new Date(alert.created_at), 'PP')}
                          </TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => {
                                setSelectedAlert(alert);
                                setAlertDetailOpen(true);
                              }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {tabValue === 'watchlists' && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Watchlists</h2>
              <Button
                onClick={() => setWatchlistDialogOpen(true)}
                leftIcon={<Plus className="h-4 w-4" />}
              >
                Create Watchlist
              </Button>
            </div>

            <div className="divide-y">
              {watchlists.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="font-medium">No watchlists found</p>
                  <p className="text-sm text-muted-foreground">
                    Create a watchlist to monitor specific products and sites
                  </p>
                </div>
              ) : (
                watchlists.map((watchlist) => (
                  <div key={watchlist.id} className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">{watchlist.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {watchlist.description || 'No description'}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Notifications: {watchlist.notification_frequency} |
                        Created: {format(new Date(watchlist.created_at), 'PP')}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteWatchlist(watchlist.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {tabValue === 'rules' && (
        <div className="space-y-6">
          {/* Alert Rules */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  Alert Rules
                </h2>
                <Button
                  onClick={() => {
                    setEditingRule(null);
                    setRuleForm({ name: '', type: 'STOCKOUT', severity: 'HIGH', threshold: 0, condition: 'above', metric: 'stockout_probability', enabled: true, channels: ['in_app'], escalateAfterHours: 24 });
                    setRuleDialogOpen(true);
                  }}
                  leftIcon={<Plus className="h-4 w-4" />}
                >
                  Create Rule
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Condition</TableHead>
                    <TableHead>Channels</TableHead>
                    <TableHead>Escalation</TableHead>
                    <TableHead>Enabled</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alertRules.map((rule) => (
                    <TableRow key={rule.id}>
                      <TableCell className="font-medium">{rule.name}</TableCell>
                      <TableCell><Badge variant="secondary">{getTypeLabel(rule.type)}</Badge></TableCell>
                      <TableCell><Badge variant={getSeverityVariant(rule.severity)}>{rule.severity}</Badge></TableCell>
                      <TableCell className="text-sm">{rule.metric.replace(/_/g, ' ')} {rule.condition} {rule.threshold}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {rule.channels.map((ch) => (
                            <Badge key={ch} variant="outline" className="text-xs">{ch}</Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">{rule.escalateAfterHours}h</TableCell>
                      <TableCell>
                        <Switch
                          checked={rule.enabled}
                          onCheckedChange={(checked) => {
                            setAlertRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, enabled: checked } : r));
                          }}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              setEditingRule(rule);
                              setRuleForm({ ...rule });
                              setRuleDialogOpen(true);
                            }}
                          >
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              if (window.confirm('Delete this alert rule?')) {
                                setAlertRules((prev) => prev.filter((r) => r.id !== rule.id));
                              }
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Notification Channels */}
          <Card>
            <CardContent className="pt-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Notification Channels
              </h2>
              <div className="space-y-4">
                {notifChannels.map((ch) => (
                  <div key={ch.id} className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
                    <div className="flex items-center gap-3">
                      {ch.type === 'email' && <Mail className="h-5 w-5 text-blue-500" />}
                      {ch.type === 'in_app' && <Bell className="h-5 w-5 text-green-500" />}
                      {ch.type === 'slack' && <MessageSquare className="h-5 w-5 text-purple-500" />}
                      <div>
                        <p className="font-medium">{ch.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {ch.type === 'email' && ch.config.address}
                          {ch.type === 'slack' && ch.config.webhook?.slice(0, 40) + '...'}
                          {ch.type === 'in_app' && 'Browser push + in-app notifications'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={ch.enabled ? 'success' : 'secondary'}>
                        {ch.enabled ? 'Active' : 'Disabled'}
                      </Badge>
                      <Switch
                        checked={ch.enabled}
                        onCheckedChange={(checked) => {
                          setNotifChannels((prev) => prev.map((c) => c.id === ch.id ? { ...c, enabled: checked } : c));
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <AlertDetailDialog />
      <WatchlistDialog />

      {/* Alert Rule Dialog */}
      <Modal
        isOpen={ruleDialogOpen}
        onClose={() => setRuleDialogOpen(false)}
        title={editingRule ? 'Edit Alert Rule' : 'Create Alert Rule'}
        maxWidth="md"
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="rule-name">Rule Name</Label>
            <Input
              id="rule-name"
              value={ruleForm.name}
              onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Alert Type</Label>
              <Select value={ruleForm.type} onValueChange={(v) => setRuleForm({ ...ruleForm, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="STOCKOUT">Stock-out</SelectItem>
                  <SelectItem value="OVERSTOCK">Overstock</SelectItem>
                  <SelectItem value="VENDOR_LEADTIME">Vendor Lead Time</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Severity</Label>
              <Select value={ruleForm.severity} onValueChange={(v) => setRuleForm({ ...ruleForm, severity: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="CRITICAL">Critical</SelectItem>
                  <SelectItem value="HIGH">High</SelectItem>
                  <SelectItem value="MEDIUM">Medium</SelectItem>
                  <SelectItem value="LOW">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Metric</Label>
              <Select value={ruleForm.metric} onValueChange={(v) => setRuleForm({ ...ruleForm, metric: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="stockout_probability">Stockout Probability</SelectItem>
                  <SelectItem value="days_of_supply">Days of Supply</SelectItem>
                  <SelectItem value="days_of_coverage">Days of Coverage</SelectItem>
                  <SelectItem value="lead_time_variance_pct">Lead Time Variance %</SelectItem>
                  <SelectItem value="inventory_turns">Inventory Turns</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Condition</Label>
              <Select value={ruleForm.condition} onValueChange={(v) => setRuleForm({ ...ruleForm, condition: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="above">Above</SelectItem>
                  <SelectItem value="below">Below</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Threshold</Label>
              <Input
                type="number"
                value={ruleForm.threshold}
                onChange={(e) => setRuleForm({ ...ruleForm, threshold: parseFloat(e.target.value) })}
              />
            </div>
          </div>
          <div>
            <Label>Escalate After (hours)</Label>
            <Input
              type="number"
              value={ruleForm.escalateAfterHours}
              onChange={(e) => setRuleForm({ ...ruleForm, escalateAfterHours: parseInt(e.target.value) })}
            />
          </div>
          <div>
            <Label className="mb-2 block">Notification Channels</Label>
            <div className="flex gap-4">
              {notifChannels.map((ch) => (
                <label key={ch.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={ruleForm.channels.includes(ch.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setRuleForm({ ...ruleForm, channels: [...ruleForm.channels, ch.id] });
                      } else {
                        setRuleForm({ ...ruleForm, channels: ruleForm.channels.filter((c) => c !== ch.id) });
                      }
                    }}
                    className="rounded border-input"
                  />
                  {ch.name}
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" onClick={() => setRuleDialogOpen(false)}>Cancel</Button>
          <Button
            disabled={!ruleForm.name}
            onClick={() => {
              if (editingRule) {
                setAlertRules((prev) => prev.map((r) => r.id === editingRule.id ? { ...ruleForm, id: editingRule.id } : r));
              } else {
                setAlertRules((prev) => [...prev, { ...ruleForm, id: Date.now() }]);
              }
              setRuleDialogOpen(false);
            }}
          >
            {editingRule ? 'Update' : 'Create'}
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default RiskAnalysis;
