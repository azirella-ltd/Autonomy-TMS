import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Progress,
  Modal,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Textarea,
} from '../../components/common';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import { Avatar, AvatarFallback } from '../../components/ui/avatar';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Check,
  X,
  Play,
  User,
  Settings,
  Plus,
  ArrowUp,
} from 'lucide-react';
import { api } from '../../services/api';

/**
 * ForecastExceptions Page
 *
 * Manages forecast exception alerts, variance tracking, and exception workflows.
 */
const ForecastExceptions = () => {
  // State
  const [activeTab, setActiveTab] = useState('exceptions');
  const [exceptions, setExceptions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [total, setTotal] = useState(0);

  // Filters
  const [filters, setFilters] = useState({
    status: '',
    severity: '',
    exception_type: '',
  });

  // Dialogs
  const [selectedException, setSelectedException] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [resolveDialogOpen, setResolveDialogOpen] = useState(false);
  const [escalateDialogOpen, setEscalateDialogOpen] = useState(false);
  const [createRuleDialogOpen, setCreateRuleDialogOpen] = useState(false);

  // Resolution form
  const [resolution, setResolution] = useState({
    resolution_action: '',
    resolution_notes: '',
    root_cause_category: '',
    root_cause_description: '',
    forecast_adjustment: '',
  });

  // Escalation form
  const [escalation, setEscalation] = useState({
    escalate_to_id: '',
    reason: '',
  });

  // New rule form
  const [newRule, setNewRule] = useState({
    name: '',
    description: '',
    rule_type: 'VARIANCE_THRESHOLD',
    variance_threshold_percent: 20,
    consecutive_periods: 1,
  });

  // Comments
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');

  useEffect(() => {
    loadData();
  }, [activeTab, page, rowsPerPage, filters]);

  const loadData = async () => {
    if (activeTab === 'exceptions') {
      await Promise.all([loadExceptions(), loadSummary()]);
    } else if (activeTab === 'rules') {
      await loadRules();
    }
  };

  const loadExceptions = async () => {
    setLoading(true);
    try {
      const params = {
        skip: page * rowsPerPage,
        limit: rowsPerPage,
        ...filters,
      };
      const response = await api.get('/forecast-exceptions', { params });
      setExceptions(response.data.items);
      setTotal(response.data.total);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load exceptions');
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    try {
      const response = await api.get('/forecast-exceptions/summary');
      setSummary(response.data);
    } catch (err) {
      console.error('Failed to load summary:', err);
    }
  };

  const loadRules = async () => {
    setLoading(true);
    try {
      const response = await api.get('/forecast-exceptions/rules/');
      setRules(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  };

  const loadComments = async (exceptionId) => {
    try {
      const response = await api.get(`/forecast-exceptions/${exceptionId}/comments`);
      setComments(response.data);
    } catch (err) {
      console.error('Failed to load comments:', err);
    }
  };

  const handleAcknowledge = async (exception) => {
    try {
      await api.post(`/forecast-exceptions/${exception.id}/acknowledge`, {});
      setSuccess('Exception acknowledged');
      loadExceptions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to acknowledge');
    }
  };

  const handleInvestigate = async (exception) => {
    try {
      await api.post(`/forecast-exceptions/${exception.id}/investigate`);
      setSuccess('Investigation started');
      loadExceptions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start investigation');
    }
  };

  const handleResolve = async () => {
    if (!selectedException) return;
    try {
      await api.post(`/forecast-exceptions/${selectedException.id}/resolve`, {
        ...resolution,
        forecast_adjustment: resolution.forecast_adjustment ? parseFloat(resolution.forecast_adjustment) : null,
      });
      setSuccess('Exception resolved');
      setResolveDialogOpen(false);
      setResolution({
        resolution_action: '',
        resolution_notes: '',
        root_cause_category: '',
        root_cause_description: '',
        forecast_adjustment: '',
      });
      loadExceptions();
      loadSummary();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to resolve');
    }
  };

  const handleEscalate = async () => {
    if (!selectedException) return;
    try {
      await api.post(`/forecast-exceptions/${selectedException.id}/escalate`, escalation);
      setSuccess('Exception escalated');
      setEscalateDialogOpen(false);
      setEscalation({ escalate_to_id: '', reason: '' });
      loadExceptions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to escalate');
    }
  };

  const handleDismiss = async (exception) => {
    const reason = window.prompt('Enter reason for dismissing:');
    if (!reason) return;
    try {
      await api.post(`/forecast-exceptions/${exception.id}/dismiss`, null, {
        params: { reason },
      });
      setSuccess('Exception dismissed');
      loadExceptions();
      loadSummary();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to dismiss');
    }
  };

  const handleAddComment = async () => {
    if (!selectedException || !newComment.trim()) return;
    try {
      await api.post(`/forecast-exceptions/${selectedException.id}/comments`, {
        content: newComment,
      });
      setNewComment('');
      loadComments(selectedException.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add comment');
    }
  };

  const handleCreateRule = async () => {
    try {
      await api.post('/forecast-exceptions/rules/', newRule);
      setSuccess('Rule created');
      setCreateRuleDialogOpen(false);
      setNewRule({
        name: '',
        description: '',
        rule_type: 'VARIANCE_THRESHOLD',
        variance_threshold_percent: 20,
        consecutive_periods: 1,
      });
      loadRules();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create rule');
    }
  };

  const handleToggleRule = async (rule) => {
    try {
      await api.post(`/forecast-exceptions/rules/${rule.id}/toggle`);
      loadRules();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to toggle rule');
    }
  };

  const getSeverityVariant = (severity) => {
    const variants = {
      LOW: 'info',
      MEDIUM: 'warning',
      HIGH: 'destructive',
      CRITICAL: 'destructive',
    };
    return variants[severity] || 'secondary';
  };

  const getStatusVariant = (status) => {
    const variants = {
      NEW: 'destructive',
      ACKNOWLEDGED: 'warning',
      INVESTIGATING: 'info',
      RESOLVED: 'success',
      ESCALATED: 'warning',
      DISMISSED: 'secondary',
    };
    return variants[status] || 'secondary';
  };

  const getSeverityIcon = (severity) => {
    if (severity === 'CRITICAL' || severity === 'HIGH') {
      return <AlertCircle className="h-4 w-4 text-red-600" />;
    }
    if (severity === 'MEDIUM') {
      return <AlertTriangle className="h-4 w-4 text-amber-600" />;
    }
    return <Info className="h-4 w-4 text-blue-600" />;
  };

  const openDetailDialog = (exception) => {
    setSelectedException(exception);
    setDetailDialogOpen(true);
    loadComments(exception.id);
  };

  const totalPages = Math.ceil(total / rowsPerPage);

  const renderSummaryCards = () => (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Open Exceptions</p>
              <p className="text-3xl font-bold">{summary?.total_open || 0}</p>
            </div>
            <div className="relative">
              <AlertTriangle className="h-10 w-10 text-amber-600" />
              {summary?.high_priority > 0 && (
                <Badge variant="destructive" className="absolute -top-2 -right-2 h-5 w-5 p-0 flex items-center justify-center text-xs">
                  {summary.high_priority}
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground mb-2">By Severity</p>
          <div className="flex gap-1 flex-wrap">
            {summary?.by_severity && Object.entries(summary.by_severity).map(([sev, count]) => (
              <Badge key={sev} variant={getSeverityVariant(sev)}>
                {sev}: {count}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground mb-2">By Status</p>
          <div className="flex gap-1 flex-wrap">
            {summary?.by_status && Object.entries(summary.by_status).map(([status, count]) => (
              <Badge key={status} variant={getStatusVariant(status)}>
                {status}: {count}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">Avg Resolution Time</p>
          <p className="text-3xl font-bold">
            {summary?.avg_resolution_hours
              ? `${summary.avg_resolution_hours.toFixed(1)}h`
              : 'N/A'}
          </p>
        </CardContent>
      </Card>
    </div>
  );

  const renderExceptionsTable = () => (
    <Card>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Severity</TableHead>
            <TableHead>Exception #</TableHead>
            <TableHead>Product</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Variance</TableHead>
            <TableHead>Forecast Source</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Detected</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {exceptions.map((exception) => (
            <TableRow
              key={exception.id}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => openDetailDialog(exception)}
            >
              <TableCell>
                <div className="flex items-center gap-2">
                  {getSeverityIcon(exception.severity)}
                  <Badge variant={getSeverityVariant(exception.severity)}>
                    {exception.severity}
                  </Badge>
                </div>
              </TableCell>
              <TableCell>{exception.exception_number}</TableCell>
              <TableCell>{exception.product_id}</TableCell>
              <TableCell>{exception.exception_type}</TableCell>
              <TableCell>
                <div className="flex items-center gap-1">
                  {exception.direction === 'OVER' ? (
                    <TrendingUp className="h-4 w-4 text-red-600" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-amber-600" />
                  )}
                  {exception.variance_percent?.toFixed(1)}%
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <Badge variant="outline">{exception.forecast_source || 'unknown'}</Badge>
                  {exception.forecast_run_id && (
                    <span className="text-xs text-muted-foreground">run {exception.forecast_run_id}</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant={getStatusVariant(exception.status)}>
                  {exception.status}
                </Badge>
              </TableCell>
              <TableCell>
                {new Date(exception.detected_at).toLocaleDateString()}
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  {exception.status === 'NEW' && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAcknowledge(exception);
                            }}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Acknowledge</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                  {['NEW', 'ACKNOWLEDGED'].includes(exception.status) && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleInvestigate(exception);
                            }}
                          >
                            <Play className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Start Investigation</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                  {!['RESOLVED', 'DISMISSED'].includes(exception.status) && (
                    <>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedException(exception);
                                setResolveDialogOpen(true);
                              }}
                            >
                              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Resolve</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDismiss(exception);
                              }}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Dismiss</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Pagination */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-border">
        <p className="text-sm text-muted-foreground">
          Showing {page * rowsPerPage + 1} to {Math.min((page + 1) * rowsPerPage, total)} of {total}
        </p>
        <div className="flex items-center gap-2">
          <Select value={String(rowsPerPage)} onValueChange={(v) => {
            setRowsPerPage(Number(v));
            setPage(0);
          }}>
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="10">10</SelectItem>
              <SelectItem value="25">25</SelectItem>
              <SelectItem value="50">50</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );

  const renderRulesTab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Detection Rules</h3>
        <Button onClick={() => setCreateRuleDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          Create Rule
        </Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Threshold</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rules.map((rule) => (
              <TableRow key={rule.id}>
                <TableCell>{rule.rule_id}</TableCell>
                <TableCell>
                  <div>
                    <p className="font-medium">{rule.name}</p>
                    {rule.description && (
                      <p className="text-sm text-muted-foreground">{rule.description}</p>
                    )}
                  </div>
                </TableCell>
                <TableCell>{rule.rule_type}</TableCell>
                <TableCell>{rule.variance_threshold_percent}%</TableCell>
                <TableCell>
                  <Badge variant={rule.is_active ? 'success' : 'secondary'}>
                    {rule.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleRule(rule)}
                  >
                    {rule.is_active ? 'Disable' : 'Enable'}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Forecast Exception Alerts</h1>
        <Button variant="outline" onClick={loadData} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {loading && <Progress className="mb-4" />}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="exceptions" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Exceptions
          </TabsTrigger>
          <TabsTrigger value="rules" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Detection Rules
          </TabsTrigger>
        </TabsList>

        <TabsContent value="exceptions">
          {renderSummaryCards()}

          {/* Filters */}
          <Card className="mb-4">
            <CardContent className="pt-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label>Status</Label>
                  <Select
                    value={filters.status}
                    onValueChange={(value) => setFilters({ ...filters, status: value })}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All</SelectItem>
                      <SelectItem value="NEW">New</SelectItem>
                      <SelectItem value="ACKNOWLEDGED">Acknowledged</SelectItem>
                      <SelectItem value="INVESTIGATING">Investigating</SelectItem>
                      <SelectItem value="RESOLVED">Resolved</SelectItem>
                      <SelectItem value="ESCALATED">Escalated</SelectItem>
                      <SelectItem value="DISMISSED">Dismissed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Severity</Label>
                  <Select
                    value={filters.severity}
                    onValueChange={(value) => setFilters({ ...filters, severity: value })}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All</SelectItem>
                      <SelectItem value="LOW">Low</SelectItem>
                      <SelectItem value="MEDIUM">Medium</SelectItem>
                      <SelectItem value="HIGH">High</SelectItem>
                      <SelectItem value="CRITICAL">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Type</Label>
                  <Select
                    value={filters.exception_type}
                    onValueChange={(value) => setFilters({ ...filters, exception_type: value })}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All</SelectItem>
                      <SelectItem value="VARIANCE">Variance</SelectItem>
                      <SelectItem value="TREND_BREAK">Trend Break</SelectItem>
                      <SelectItem value="OUTLIER">Outlier</SelectItem>
                      <SelectItem value="BIAS">Bias</SelectItem>
                      <SelectItem value="MANUAL">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {renderExceptionsTable()}
        </TabsContent>

        <TabsContent value="rules">
          {renderRulesTab()}
        </TabsContent>
      </Tabs>

      {/* Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title={`Exception Details: ${selectedException?.exception_number}`}
        size="lg"
      >
        {selectedException && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Product</p>
                <p className="font-medium">{selectedException.product_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Period</p>
                <p className="font-medium">
                  {selectedException.period_start} - {selectedException.period_end || 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Forecast Qty</p>
                <p className="font-medium">{selectedException.forecast_quantity}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Actual Qty</p>
                <p className="font-medium">{selectedException.actual_quantity || 'Pending'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Variance</p>
                <p className="font-medium">
                  {selectedException.variance_quantity} ({selectedException.variance_percent?.toFixed(1)}%)
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Threshold</p>
                <p className="font-medium">{selectedException.threshold_percent}%</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Forecast Source</p>
                <p className="font-medium">
                  {selectedException.forecast_source || 'unknown'}
                  {selectedException.forecast_run_id ? ` (run ${selectedException.forecast_run_id})` : ''}
                </p>
              </div>
            </div>

            {selectedException.ai_recommendation && (
              <Alert variant="info">
                <strong>AI Recommendation:</strong> {selectedException.ai_recommendation}
              </Alert>
            )}

            {selectedException.root_cause_category && (
              <div>
                <p className="text-sm text-muted-foreground">Root Cause</p>
                <p className="font-medium">
                  {selectedException.root_cause_category}: {selectedException.root_cause_description}
                </p>
              </div>
            )}

            <div className="border-t border-border pt-4">
              <h4 className="font-medium mb-3">Comments</h4>
              <div className="space-y-2 mb-4">
                {comments.map((comment) => (
                  <div key={comment.id} className="flex items-start gap-3">
                    <Avatar className="h-8 w-8">
                      <AvatarFallback>
                        <User className="h-4 w-4" />
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="text-sm">{comment.content}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(comment.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="Add a comment..."
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  className="flex-1"
                />
                <Button variant="outline" onClick={handleAddComment}>Add</Button>
              </div>
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          {selectedException && !['RESOLVED', 'DISMISSED'].includes(selectedException.status) && (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setDetailDialogOpen(false);
                  setEscalateDialogOpen(true);
                }}
                leftIcon={<ArrowUp className="h-4 w-4" />}
              >
                Escalate
              </Button>
              <Button
                onClick={() => {
                  setDetailDialogOpen(false);
                  setResolveDialogOpen(true);
                }}
                leftIcon={<CheckCircle2 className="h-4 w-4" />}
              >
                Resolve
              </Button>
            </>
          )}
          <Button variant="outline" onClick={() => setDetailDialogOpen(false)}>Close</Button>
        </div>
      </Modal>

      {/* Resolve Dialog */}
      <Modal
        open={resolveDialogOpen}
        onClose={() => setResolveDialogOpen(false)}
        title="Resolve Exception"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <Label>Resolution Action *</Label>
            <Select
              value={resolution.resolution_action}
              onValueChange={(value) => setResolution({ ...resolution, resolution_action: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Select action..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ADJUST_FORECAST">Adjust Forecast</SelectItem>
                <SelectItem value="ADJUST_SAFETY_STOCK">Adjust Safety Stock</SelectItem>
                <SelectItem value="EXPEDITE_SUPPLY">Expedite Supply</SelectItem>
                <SelectItem value="NO_ACTION">No Action Required</SelectItem>
                <SelectItem value="OTHER">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Root Cause Category</Label>
            <Select
              value={resolution.root_cause_category}
              onValueChange={(value) => setResolution({ ...resolution, root_cause_category: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Select category..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PROMOTION">Promotion/Event</SelectItem>
                <SelectItem value="SEASONALITY">Seasonality</SelectItem>
                <SelectItem value="MARKET_CHANGE">Market Change</SelectItem>
                <SelectItem value="DATA_ERROR">Data Error</SelectItem>
                <SelectItem value="SUPPLY_ISSUE">Supply Issue</SelectItem>
                <SelectItem value="EXTERNAL_EVENT">External Event</SelectItem>
                <SelectItem value="UNKNOWN">Unknown</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Root Cause Description</Label>
            <Textarea
              value={resolution.root_cause_description}
              onChange={(e) => setResolution({ ...resolution, root_cause_description: e.target.value })}
              rows={2}
              className="mt-1"
            />
          </div>
          {resolution.resolution_action === 'ADJUST_FORECAST' && (
            <div>
              <Label>Adjusted Forecast Value</Label>
              <Input
                type="number"
                value={resolution.forecast_adjustment}
                onChange={(e) => setResolution({ ...resolution, forecast_adjustment: e.target.value })}
                className="mt-1"
              />
            </div>
          )}
          <div>
            <Label>Resolution Notes</Label>
            <Textarea
              value={resolution.resolution_notes}
              onChange={(e) => setResolution({ ...resolution, resolution_notes: e.target.value })}
              rows={3}
              className="mt-1"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setResolveDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleResolve}
            disabled={!resolution.resolution_action}
          >
            Resolve
          </Button>
        </div>
      </Modal>

      {/* Escalate Dialog */}
      <Modal
        open={escalateDialogOpen}
        onClose={() => setEscalateDialogOpen(false)}
        title="Escalate Exception"
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <Label>Escalate to User ID *</Label>
            <Input
              type="number"
              value={escalation.escalate_to_id}
              onChange={(e) => setEscalation({ ...escalation, escalate_to_id: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label>Reason for Escalation *</Label>
            <Textarea
              value={escalation.reason}
              onChange={(e) => setEscalation({ ...escalation, reason: e.target.value })}
              rows={3}
              className="mt-1"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setEscalateDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleEscalate}
            disabled={!escalation.escalate_to_id || !escalation.reason}
          >
            Escalate
          </Button>
        </div>
      </Modal>

      {/* Create Rule Dialog */}
      <Modal
        open={createRuleDialogOpen}
        onClose={() => setCreateRuleDialogOpen(false)}
        title="Create Detection Rule"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <Label>Rule Name *</Label>
            <Input
              value={newRule.name}
              onChange={(e) => setNewRule({ ...newRule, name: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              value={newRule.description}
              onChange={(e) => setNewRule({ ...newRule, description: e.target.value })}
              rows={2}
              className="mt-1"
            />
          </div>
          <div>
            <Label>Rule Type</Label>
            <Select
              value={newRule.rule_type}
              onValueChange={(value) => setNewRule({ ...newRule, rule_type: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="VARIANCE_THRESHOLD">Variance Threshold</SelectItem>
                <SelectItem value="TREND_DETECTION">Trend Detection</SelectItem>
                <SelectItem value="OUTLIER_DETECTION">Outlier Detection</SelectItem>
                <SelectItem value="BIAS_DETECTION">Bias Detection</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Variance Threshold (%)</Label>
              <Input
                type="number"
                value={newRule.variance_threshold_percent}
                onChange={(e) => setNewRule({ ...newRule, variance_threshold_percent: parseFloat(e.target.value) })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Consecutive Periods</Label>
              <Input
                type="number"
                value={newRule.consecutive_periods}
                onChange={(e) => setNewRule({ ...newRule, consecutive_periods: parseInt(e.target.value) })}
                className="mt-1"
              />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCreateRuleDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleCreateRule}
            disabled={!newRule.name}
          >
            Create
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default ForecastExceptions;
