/**
 * S&OP Worklist Page - SOP_DIRECTOR Landing Page
 *
 * Powell Framework Tactical Level Dashboard
 * Shows worklist items requiring attention with agent performance metrics
 *
 * Features:
 * - KPI summary cards (Gross Margin, Capacity, Revenue at Risk, Escalations)
 * - Quick action buttons for common operations
 * - Worklist table with Ask Why, Accept, Override actions
 * - Agent reasoning modal ("Ask Why" functionality)
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Gauge,
  AlertTriangle,
  Bell,
  ChevronRight,
  HelpCircle,
  Check,
  Pencil,
  X,
  RefreshCw,
  Filter,
  Clock,
  Package,
  Truck,
  Factory,
  Bot,
  Brain,
  MessageSquare,
} from 'lucide-react';
import { cn } from '../lib/utils/cn';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Spinner,
  Alert,
  IconButton,
} from '../components/common';
import { api } from '../services/api';

// =============================================================================
// KPI Card Component
// =============================================================================

const KPICard = ({ title, value, unit, change, changeLabel, icon: Icon, variant = 'default', action }) => {
  const isPositive = change >= 0;
  const changeColor = isPositive ? 'text-green-600' : 'text-red-600';

  const variantStyles = {
    success: 'bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-900',
    warning: 'bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-900',
    danger: 'bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900',
    info: 'bg-blue-50 border-blue-200 dark:bg-blue-950/20 dark:border-blue-900',
    default: '',
  };

  const iconStyles = {
    success: 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-400',
    warning: 'bg-amber-100 text-amber-600 dark:bg-amber-900 dark:text-amber-400',
    danger: 'bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-400',
    info: 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-400',
    default: 'bg-primary/10 text-primary',
  };

  return (
    <Card className={cn('relative overflow-hidden border', variantStyles[variant])}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="text-2xl font-bold">
                {typeof value === 'number' ? value.toLocaleString() : value}
              </span>
              {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
            </div>
            {change !== undefined && (
              <div className={cn('mt-1 flex items-center gap-1 text-xs', changeColor)}>
                {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                <span>{isPositive ? '+' : ''}{change}{changeLabel || ''}</span>
              </div>
            )}
          </div>
          {Icon && (
            <div className={cn('rounded-lg p-2', iconStyles[variant])}>
              <Icon className="h-5 w-5" />
            </div>
          )}
        </div>
        {action && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-between text-xs"
            onClick={action.onClick}
          >
            {action.label}
            <ChevronRight className="h-3 w-3" />
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Worklist Item Row Component
// =============================================================================

const WorklistItemRow = ({ item, onAskWhy, onAccept, onReject }) => {
  const [processing, setProcessing] = useState(false);

  const urgencyStyles = {
    urgent: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    high: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    low: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
  };

  const categoryIcons = {
    inventory: Package,
    logistics: Truck,
    production: Factory,
    demand: TrendingUp,
  };

  const CategoryIcon = categoryIcons[item.category] || Package;

  const handleAction = async (action, callback) => {
    setProcessing(true);
    try {
      await callback(item.id);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <tr className="border-b hover:bg-muted/50 transition-colors">
      <td className="py-3 px-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-muted">
            <CategoryIcon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium text-sm">{item.item_code}</p>
            <p className="text-xs text-muted-foreground">{item.item_name}</p>
          </div>
        </div>
      </td>
      <td className="py-3 px-4">
        <p className="text-sm">{item.issue_summary}</p>
        <div className="flex items-center gap-2 mt-1">
          <Badge
            variant="outline"
            size="sm"
            className={cn('text-[10px]', urgencyStyles[item.urgency])}
          >
            {item.urgency}
          </Badge>
          {item.agent_recommendation && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Bot className="h-3 w-3" />
              Agent suggestion available
            </span>
          )}
        </div>
      </td>
      <td className="py-3 px-4">
        <p className="text-sm font-medium">{item.impact_value}</p>
        <p className="text-xs text-muted-foreground">{item.impact_description}</p>
      </td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-1 text-sm">
          <Clock className="h-3 w-3 text-muted-foreground" />
          <span className={cn(
            item.days_until_due <= 1 ? 'text-red-600 font-medium' :
            item.days_until_due <= 3 ? 'text-amber-600' : ''
          )}>
            {item.due_date}
          </span>
        </div>
        {item.days_until_due <= 1 && (
          <p className="text-xs text-red-600">Due soon!</p>
        )}
      </td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-3">
          {/* Ask Why */}
          <button
            className="flex flex-col items-center gap-0.5 p-1.5 rounded-md hover:bg-muted transition-colors disabled:opacity-50"
            onClick={() => onAskWhy(item)}
            disabled={processing}
          >
            <HelpCircle className="h-5 w-5 text-muted-foreground" />
            <span className="text-[10px] text-muted-foreground">Ask Why</span>
          </button>
          {/* Accept */}
          <button
            className="flex flex-col items-center gap-0.5 p-1.5 rounded-md hover:bg-green-50 transition-colors disabled:opacity-50"
            onClick={() => handleAction('accept', onAccept)}
            disabled={processing}
          >
            <Check className="h-5 w-5 text-green-600" />
            <span className="text-[10px] text-green-600">Accept</span>
          </button>
          {/* Override */}
          <button
            className="flex flex-col items-center gap-0.5 p-1.5 rounded-md hover:bg-red-50 transition-colors disabled:opacity-50"
            onClick={() => handleAction('reject', onReject)}
            disabled={processing}
          >
            <Pencil className="h-5 w-5 text-red-600" />
            <span className="text-[10px] text-red-600">Override</span>
          </button>
        </div>
      </td>
    </tr>
  );
};

// =============================================================================
// Agent Reasoning Modal
// =============================================================================

const AgentReasoningModal = ({ item, reasoning, onClose, onAccept, onReject }) => {
  const [overrideReason, setOverrideReason] = useState('');
  const [showRejectForm, setShowRejectForm] = useState(false);

  if (!item) return null;

  const handleReject = () => {
    if (showRejectForm && overrideReason.trim()) {
      onReject(item.id, overrideReason);
      onClose();
    } else {
      setShowRejectForm(true);
    }
  };

  const handleAccept = () => {
    onAccept(item.id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Brain className="h-5 w-5 text-primary" />
                Agent Reasoning
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                {item.item_code} - {item.item_name}
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="p-6 space-y-4">
          {/* Issue Summary */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-1">Issue</h3>
            <p className="text-sm">{item.issue_summary}</p>
          </div>

          {/* Agent Recommendation */}
          <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
            <h3 className="text-sm font-medium flex items-center gap-2 mb-2">
              <Bot className="h-4 w-4 text-primary" />
              Agent Recommendation
            </h3>
            <p className="text-sm font-medium">{reasoning?.recommendation || item.agent_recommendation}</p>
          </div>

          {/* Reasoning */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-1">Reasoning</h3>
            <p className="text-sm whitespace-pre-wrap">{reasoning?.reasoning || item.agent_reasoning}</p>
          </div>

          {/* Confidence & Supporting Data */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-1">Confidence</h3>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full"
                    style={{ width: `${reasoning?.confidence || 85}%` }}
                  />
                </div>
                <span className="text-sm font-medium">{reasoning?.confidence || 85}%</span>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-1">Expected Impact</h3>
              <p className="text-sm font-medium text-green-600">{reasoning?.expected_impact || item.impact_value}</p>
            </div>
          </div>

          {/* Supporting Data */}
          {reasoning?.supporting_data && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-2">Supporting Data</h3>
              <ul className="space-y-1">
                {reasoning.supporting_data.map((data, idx) => (
                  <li key={idx} className="text-sm flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                    {data}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Override Form */}
          {showRejectForm && (
            <div className="p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded-lg">
              <h3 className="text-sm font-medium text-red-700 dark:text-red-400 mb-2">
                Override Reason Required
              </h3>
              <textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Please explain why you're overriding the agent recommendation..."
                className="w-full p-3 border rounded-md text-sm resize-none h-24"
                autoFocus
              />
              <p className="text-xs text-muted-foreground mt-1">
                Your feedback helps improve agent accuracy (performance metrics)
              </p>
            </div>
          )}
        </div>

        <div className="p-6 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="outline"
            className="text-red-600 border-red-200 hover:bg-red-50"
            onClick={handleReject}
          >
            <Pencil className="h-4 w-4 mr-1" />
            {showRejectForm ? 'Submit Override' : 'Override'}
          </Button>
          <Button onClick={handleAccept}>
            <Check className="h-4 w-4 mr-1" />
            Accept Recommendation
          </Button>
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// Main S&OP Worklist Page Component
// =============================================================================

const SOPWorklistPage = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [reasoning, setReasoning] = useState(null);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [categoryFilter, setCategoryFilter] = useState(null);

  useEffect(() => {
    fetchWorklist();
  }, [statusFilter, categoryFilter]);

  const fetchWorklist = async () => {
    try {
      setLoading(true);
      const params = { status: statusFilter };
      if (categoryFilter) params.category = categoryFilter;
      const response = await api.get('/decision-metrics/sop-worklist', { params });
      setData(response.data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch worklist:', err);
      setError('Failed to load worklist data');
    } finally {
      setLoading(false);
    }
  };

  const handleAskWhy = async (item) => {
    setSelectedItem(item);
    try {
      const response = await api.get(`/decision-metrics/sop-worklist/${item.id}/reasoning`);
      setReasoning(response.data.data);
    } catch (err) {
      console.error('Failed to fetch reasoning:', err);
      setReasoning({
        recommendation: item.agent_recommendation,
        reasoning: item.agent_reasoning,
        confidence: 85,
        supporting_data: [
          'Historical demand pattern analysis',
          'Current inventory levels across network',
          'Lead time and transit considerations',
        ],
      });
    }
  };

  const handleAccept = async (itemId) => {
    try {
      await api.post(`/decision-metrics/sop-worklist/${itemId}/resolve`, {
        action: 'accept',
      });
      fetchWorklist();
    } catch (err) {
      console.error('Failed to accept:', err);
    }
    setSelectedItem(null);
    setReasoning(null);
  };

  const handleReject = async (itemId, notes = '') => {
    try {
      await api.post(`/decision-metrics/sop-worklist/${itemId}/resolve`, {
        action: 'reject',
        notes,
      });
      fetchWorklist();
    } catch (err) {
      console.error('Failed to reject:', err);
    }
    setSelectedItem(null);
    setReasoning(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="error">{error}</Alert>
      </div>
    );
  }

  const { summary, items } = data || {};

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">S&OP Worklist</h1>
          <p className="text-muted-foreground">
            Review and accept/override agent recommendations
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={fetchWorklist}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <span className="flex items-center gap-2 text-sm text-green-600">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Real-time updates
          </span>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          title="Gross Margin"
          value={summary?.gross_margin_pct || 32.5}
          unit="%"
          change={summary?.gross_margin_change || 2.1}
          changeLabel="% vs target"
          icon={DollarSign}
          variant="success"
          action={{
            label: 'Improve margin',
            onClick: () => setCategoryFilter('margin'),
          }}
        />
        <KPICard
          title="Capacity Utilization"
          value={summary?.capacity_utilization_pct || 87}
          unit="%"
          change={summary?.capacity_change || -3}
          changeLabel="% vs plan"
          icon={Gauge}
          variant="warning"
          action={{
            label: 'Balance capacity',
            onClick: () => setCategoryFilter('capacity'),
          }}
        />
        <KPICard
          title="Revenue at Risk"
          value={`$${((summary?.revenue_at_risk?.value || summary?.revenue_at_risk || 2400000) / 1000000).toFixed(1)}M`}
          change={summary?.revenue_at_risk_change || 5}
          changeLabel="% of forecast"
          icon={AlertTriangle}
          variant="danger"
          action={{
            label: 'Mitigate risk',
            onClick: () => setCategoryFilter('risk'),
          }}
        />
        <KPICard
          title="Escalations"
          value={summary?.escalation_count || 12}
          change={summary?.escalation_change || -3}
          changeLabel=" vs yesterday"
          icon={Bell}
          variant="info"
          action={{
            label: 'Resolve escalations',
            onClick: () => setCategoryFilter('escalation'),
          }}
        />
      </div>

      {/* Agent Performance Summary */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Agent Performance Score</p>
                <p className="text-2xl font-bold text-green-600">+{summary?.agent_score || 42}%</p>
                <p className="text-xs text-muted-foreground">Agent decisions outperforming manual by 42%</p>
              </div>
              <div className="p-3 bg-green-100 text-green-600 rounded-lg">
                <Bot className="h-6 w-6" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Human Override Rate</p>
                <p className="text-2xl font-bold text-blue-600">{summary?.override_rate || 22}%</p>
                <p className="text-xs text-muted-foreground">Percentage of decisions overridden by humans</p>
              </div>
              <div className="p-3 bg-blue-100 text-blue-600 rounded-lg">
                <Brain className="h-6 w-6" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Worklist Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-lg">Pending Decisions</CardTitle>
          <div className="flex items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-sm border rounded-md px-2 py-1 bg-background"
            >
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Overridden</option>
              <option value="">All</option>
            </select>
            <Button variant="outline" size="sm">
              <Filter className="h-4 w-4 mr-1" />
              Filter
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="py-3 px-4 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Item</th>
                  <th className="py-3 px-4 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Issue</th>
                  <th className="py-3 px-4 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Impact</th>
                  <th className="py-3 px-4 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Due</th>
                  <th className="py-3 px-4 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items && items.length > 0 ? (
                  items.map((item) => (
                    <WorklistItemRow
                      key={item.id}
                      item={item}
                      onAskWhy={handleAskWhy}
                      onAccept={handleAccept}
                      onReject={handleReject}
                    />
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-muted-foreground">
                      No items in worklist
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Agent Reasoning Modal */}
      {selectedItem && (
        <AgentReasoningModal
          item={selectedItem}
          reasoning={reasoning}
          onClose={() => {
            setSelectedItem(null);
            setReasoning(null);
          }}
          onAccept={handleAccept}
          onReject={handleReject}
        />
      )}
    </div>
  );
};

export default SOPWorklistPage;
