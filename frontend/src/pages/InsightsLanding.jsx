/**
 * Insights Landing Page - AIIO Framework
 *
 * The primary landing page for planners showing agent actions with
 * hierarchy drill-down by site, product, and time.
 *
 * AIIO Framework:
 * - AUTOMATE: Agent executed automatically (no notification)
 * - INFORM: Agent executed and notified user (acknowledgment workflow)
 * - INSPECT: User drills into action to see explanation/alternatives
 * - OVERRIDE: User changes decision with required reason
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Spinner,
  Alert,
  AlertDescription,
  AlertTitle,
} from '../components/common';
import {
  RefreshCw,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Eye,
  Check,
  Edit3,
  Package,
  TrendingUp,
  Truck,
  AlertTriangle,
  Clock,
  Bot,
  Filter,
  Layers,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import insightsApi, {
  getDashboard,
  getActions,
  getActionDetail,
  acknowledgeAction,
  overrideAction,
  drillDown,
  drillUp,
  ACTION_MODES,
  ACTION_CATEGORIES,
  HIERARCHY_LEVELS,
} from '../services/insightsApi';

// ============================================================================
// Summary Cards
// ============================================================================

const SummaryCards = ({ summary }) => {
  if (!summary) return null;

  const { by_mode, by_status, total_actions } = summary;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-muted-foreground">Total Actions</p>
              <p className="text-3xl font-bold">{total_actions}</p>
            </div>
            <Bot className="h-8 w-8 text-muted-foreground" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-muted-foreground">Automated</p>
              <p className="text-3xl font-bold text-blue-600">{by_mode?.automate || 0}</p>
            </div>
            <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
              <Check className="h-5 w-5 text-blue-600" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-muted-foreground">Pending Review</p>
              <p className="text-3xl font-bold text-amber-600">{by_status?.pending_acknowledgment || 0}</p>
            </div>
            <div className="h-8 w-8 rounded-full bg-amber-100 flex items-center justify-center">
              <Clock className="h-5 w-5 text-amber-600" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-muted-foreground">Overridden</p>
              <p className="text-3xl font-bold text-red-600">{by_status?.overridden || 0}</p>
            </div>
            <div className="h-8 w-8 rounded-full bg-red-100 flex items-center justify-center">
              <Edit3 className="h-5 w-5 text-red-600" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Hierarchy Breadcrumb
// ============================================================================

const HierarchyBreadcrumb = ({ breadcrumbs, dimension, onNavigate }) => {
  const items = breadcrumbs?.[dimension] || [];

  return (
    <div className="flex items-center gap-1 text-sm">
      <span className="text-muted-foreground capitalize">{dimension}:</span>
      {items.map((item, idx) => (
        <React.Fragment key={item.key}>
          {idx > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          <button
            onClick={() => !item.is_current && onNavigate(dimension, item.level, item.key)}
            className={`px-2 py-0.5 rounded ${
              item.is_current
                ? 'bg-primary text-primary-foreground font-medium'
                : 'hover:bg-muted'
            }`}
            disabled={item.is_current}
          >
            {item.label}
          </button>
        </React.Fragment>
      ))}
    </div>
  );
};

// ============================================================================
// Hierarchy Selector
// ============================================================================

const HierarchySelector = ({ context, onChange }) => {
  const renderLevelSelect = (dimension, currentValue, levels) => (
    <select
      value={currentValue || Object.keys(levels)[0]}
      onChange={(e) => onChange(dimension, e.target.value)}
      className="px-3 py-1.5 border rounded text-sm bg-background"
    >
      {Object.entries(levels).map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </select>
  );

  return (
    <div className="flex items-center gap-4 mb-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Site:</span>
        {renderLevelSelect('site', context.siteLevel, HIERARCHY_LEVELS.site)}
      </div>
      <span className="text-muted-foreground">×</span>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Product:</span>
        {renderLevelSelect('product', context.productLevel, HIERARCHY_LEVELS.product)}
      </div>
      <span className="text-muted-foreground">×</span>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Time:</span>
        {renderLevelSelect('time', context.timeBucket, HIERARCHY_LEVELS.time)}
      </div>
    </div>
  );
};

// ============================================================================
// Action Card
// ============================================================================

const ActionCard = ({ action, onAcknowledge, onInspect, onOverride }) => {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [overrideMode, setOverrideMode] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');

  const modeInfo = ACTION_MODES[action.action_mode] || ACTION_MODES.inform;
  const categoryInfo = ACTION_CATEGORIES[action.category] || ACTION_CATEGORIES.other;

  const handleInspect = async () => {
    if (expanded && detail) {
      setExpanded(false);
      return;
    }

    setLoadingDetail(true);
    try {
      const response = await getActionDetail(action.id);
      setDetail(response.data);
      setExpanded(true);
    } catch (err) {
      console.error('Failed to load action detail:', err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleOverrideSubmit = async () => {
    if (overrideReason.length < 10) {
      alert('Reason must be at least 10 characters');
      return;
    }

    try {
      await onOverride(action.id, overrideReason);
      setOverrideMode(false);
      setOverrideReason('');
    } catch (err) {
      console.error('Failed to override:', err);
    }
  };

  const metricChange = action.metric_after !== null && action.metric_before !== null
    ? action.metric_after - action.metric_before
    : null;

  return (
    <Card className={`mb-3 ${action.is_overridden ? 'border-l-4 border-l-red-500' : ''}`}>
      <CardContent className="py-4">
        {/* Header Row */}
        <div className="flex justify-between items-start gap-4 mb-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Badge className={modeInfo.color}>{modeInfo.label}</Badge>
              <Badge variant="outline">{categoryInfo.label}</Badge>
              {action.is_overridden && <Badge variant="destructive">Overridden</Badge>}
              {!action.is_acknowledged && action.action_mode === 'inform' && (
                <Badge variant="warning">Pending</Badge>
              )}
            </div>
            <h3 className="font-semibold">{action.title}</h3>
            <p className="text-sm text-muted-foreground mt-1">{action.explanation}</p>
          </div>

          {/* Metrics */}
          {action.metric_name && (
            <div className="text-right">
              <p className="text-xs text-muted-foreground">{action.metric_name}</p>
              <div className="flex items-center gap-2">
                <span className="text-sm">{action.metric_before?.toLocaleString()}</span>
                <ChevronRight className="h-4 w-4" />
                <span className="text-sm font-semibold">{action.metric_after?.toLocaleString()}</span>
                {metricChange !== null && (
                  <Badge variant={metricChange >= 0 ? 'success' : 'destructive'}>
                    {metricChange >= 0 ? '+' : ''}{metricChange.toLocaleString()}
                  </Badge>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Context */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground mb-3">
          <span>{action.site_key}</span>
          <span>•</span>
          <span>{action.product_key}</span>
          <span>•</span>
          <span>{action.time_key}</span>
          <span>•</span>
          <span>{action.agent_id}</span>
          <span>•</span>
          <span>{new Date(action.executed_at).toLocaleString()}</span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {action.action_mode === 'inform' && !action.is_acknowledged && (
            <Button size="sm" onClick={() => onAcknowledge(action.id)}>
              <Check className="h-4 w-4 mr-1" />
              Acknowledge
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={handleInspect} disabled={loadingDetail}>
            {loadingDetail ? (
              <Spinner size="sm" className="mr-1" />
            ) : (
              <Eye className="h-4 w-4 mr-1" />
            )}
            {expanded ? 'Hide Details' : 'Inspect'}
          </Button>
          {!action.is_overridden && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOverrideMode(!overrideMode)}
            >
              <Edit3 className="h-4 w-4 mr-1" />
              Override
            </Button>
          )}
        </div>

        {/* Expanded Detail (INSPECT) */}
        {expanded && detail && (
          <div className="mt-4 pt-4 border-t">
            <h4 className="font-semibold mb-2">Full Explanation</h4>
            <p className="text-sm whitespace-pre-wrap mb-4">{detail.explanation}</p>

            {detail.reasoning_chain && detail.reasoning_chain.length > 0 && (
              <div className="mb-4">
                <h4 className="font-semibold mb-2">Reasoning Chain</h4>
                <div className="space-y-2">
                  {detail.reasoning_chain.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm">
                      <span className="font-mono bg-muted px-1.5 py-0.5 rounded">{step.step}</span>
                      <span>{step.description}</span>
                      {step.confidence && (
                        <Badge variant="outline">{(step.confidence * 100).toFixed(0)}%</Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detail.alternatives_considered && detail.alternatives_considered.length > 0 && (
              <div>
                <h4 className="font-semibold mb-2">Alternatives Considered</h4>
                <div className="space-y-2">
                  {detail.alternatives_considered.map((alt, idx) => (
                    <div key={idx} className="text-sm p-2 bg-muted rounded">
                      <p className="font-medium">{alt.description}</p>
                      <p className="text-muted-foreground">Not chosen: {alt.why_not_chosen}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Override Form */}
        {overrideMode && (
          <div className="mt-4 pt-4 border-t">
            <h4 className="font-semibold mb-2">Override Action</h4>
            <p className="text-sm text-muted-foreground mb-2">
              Please provide a reason for overriding this action. This is required for audit trail and to improve agent decisions.
            </p>
            <textarea
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Enter reason for override (minimum 10 characters)..."
              className="w-full p-2 border rounded text-sm mb-2"
              rows={3}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleOverrideSubmit} disabled={overrideReason.length < 10}>
                Submit Override
              </Button>
              <Button size="sm" variant="outline" onClick={() => setOverrideMode(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ============================================================================
// Main Component
// ============================================================================

const InsightsLanding = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const [summary, setSummary] = useState(null);
  const [actions, setActions] = useState([]);
  const [totalActions, setTotalActions] = useState(0);

  // Hierarchy context
  const [context, setContext] = useState({
    siteLevel: 'company',
    siteKey: null,
    productLevel: 'category',
    productKey: null,
    timeBucket: 'month',
    timeKey: null,
  });

  // Filters
  const [filters, setFilters] = useState({
    mode: null,
    category: null,
    acknowledged: null,
    offset: 0,
    limit: 20,
  });

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setRefreshing(true);

      // Fetch dashboard summary
      const dashboardResponse = await getDashboard(context, 5);
      setSummary(dashboardResponse.data);

      // Fetch actions list
      const actionsResponse = await getActions(filters, context);
      setActions(actionsResponse.data);
      setTotalActions(actionsResponse.total);

      setError(null);
    } catch (err) {
      console.error('Failed to fetch insights data:', err);
      setError('Unable to load insights. Please try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [context, filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handlers
  const handleAcknowledge = async (actionId) => {
    try {
      await acknowledgeAction(actionId);
      fetchData();
    } catch (err) {
      console.error('Failed to acknowledge:', err);
    }
  };

  const handleOverride = async (actionId, reason) => {
    try {
      await overrideAction(actionId, reason);
      fetchData();
    } catch (err) {
      console.error('Failed to override:', err);
      throw err;
    }
  };

  const handleLevelChange = (dimension, level) => {
    const newContext = { ...context };
    if (dimension === 'site') {
      newContext.siteLevel = level;
      newContext.siteKey = null;
    } else if (dimension === 'product') {
      newContext.productLevel = level;
      newContext.productKey = null;
    } else if (dimension === 'time') {
      newContext.timeBucket = level;
      newContext.timeKey = null;
    }
    setContext(newContext);
    setFilters({ ...filters, offset: 0 });
  };

  const handleBreadcrumbNavigate = (dimension, level, key) => {
    const newContext = { ...context };
    if (dimension === 'site') {
      newContext.siteLevel = level;
      newContext.siteKey = key === `all_${level}` ? null : key;
    } else if (dimension === 'product') {
      newContext.productLevel = level;
      newContext.productKey = key === `all_${level}` ? null : key;
    } else if (dimension === 'time') {
      newContext.timeBucket = level;
      newContext.timeKey = key === `all_${level}` ? null : key;
    }
    setContext(newContext);
    setFilters({ ...filters, offset: 0 });
  };

  const handleFilterChange = (key, value) => {
    setFilters({ ...filters, [key]: value, offset: 0 });
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold">Insights & Actions</h1>
          <p className="text-muted-foreground">
            AI agent decisions with drill-down by site, product, and time
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!summary?.user_has_full_scope && (
            <Badge variant="outline">
              <Filter className="h-3 w-3 mr-1" />
              Filtered View
            </Badge>
          )}
          <Button variant="outline" size="icon" onClick={fetchData} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Summary Cards */}
      <SummaryCards summary={summary} />

      {/* Hierarchy Navigation */}
      <Card className="mb-6">
        <CardContent className="py-4">
          <div className="flex items-center gap-2 mb-4">
            <Layers className="h-5 w-5 text-muted-foreground" />
            <span className="font-semibold">Hierarchy</span>
          </div>

          <HierarchySelector context={context} onChange={handleLevelChange} />

          {summary?.breadcrumbs && (
            <div className="space-y-2 pt-4 border-t">
              <HierarchyBreadcrumb
                breadcrumbs={summary.breadcrumbs}
                dimension="site"
                onNavigate={handleBreadcrumbNavigate}
              />
              <HierarchyBreadcrumb
                breadcrumbs={summary.breadcrumbs}
                dimension="product"
                onNavigate={handleBreadcrumbNavigate}
              />
              <HierarchyBreadcrumb
                breadcrumbs={summary.breadcrumbs}
                dimension="time"
                onNavigate={handleBreadcrumbNavigate}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-4">
        <select
          value={filters.mode || ''}
          onChange={(e) => handleFilterChange('mode', e.target.value || null)}
          className="px-3 py-1.5 border rounded text-sm bg-background"
        >
          <option value="">All Modes</option>
          <option value="automate">Automated</option>
          <option value="inform">Informed</option>
        </select>

        <select
          value={filters.acknowledged === null ? '' : filters.acknowledged.toString()}
          onChange={(e) => handleFilterChange('acknowledged', e.target.value === '' ? null : e.target.value === 'true')}
          className="px-3 py-1.5 border rounded text-sm bg-background"
        >
          <option value="">All Status</option>
          <option value="false">Pending</option>
          <option value="true">Acknowledged</option>
        </select>

        <span className="text-sm text-muted-foreground">
          Showing {actions.length} of {totalActions} actions
        </span>
      </div>

      {/* Actions List */}
      <div>
        {actions.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Bot className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Actions Found</h3>
              <p className="text-muted-foreground">
                No agent actions match the current filters and hierarchy context.
              </p>
            </CardContent>
          </Card>
        ) : (
          actions.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              onAcknowledge={handleAcknowledge}
              onOverride={handleOverride}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {totalActions > filters.limit && (
        <div className="flex justify-center gap-2 mt-6">
          <Button
            variant="outline"
            disabled={filters.offset === 0}
            onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - filters.limit) })}
          >
            Previous
          </Button>
          <span className="px-4 py-2 text-sm">
            Page {Math.floor(filters.offset / filters.limit) + 1} of {Math.ceil(totalActions / filters.limit)}
          </span>
          <Button
            variant="outline"
            disabled={filters.offset + filters.limit >= totalActions}
            onClick={() => setFilters({ ...filters, offset: filters.offset + filters.limit })}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
};

export default InsightsLanding;
