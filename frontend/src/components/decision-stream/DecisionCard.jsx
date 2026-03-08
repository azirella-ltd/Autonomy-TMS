/**
 * Decision Card Component
 *
 * Compact actionable card for a pending TRM decision, displayed inline
 * in the Decision Stream. Supports Accept, Override, Ask Why, and Navigate.
 *
 * Reuses patterns from:
 *   - FeedbackSignalCards (card layout, deviation indicators)
 *   - TRMDecisionWorklist (confidence chips, override reason codes)
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle,
  Edit3,
  HelpCircle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Package,
  Truck,
  ShoppingCart,
  AlertTriangle,
  Factory,
  Wrench,
  BarChart3,
  Shield,
  RefreshCw,
  TrendingUp,
  Box,
  Loader2,
} from 'lucide-react';
import { Badge, Button, Card, CardContent } from '../common';
import { cn } from '../../lib/utils/cn';

// Override reason codes (aligned with TRMDecisionWorklist)
const REASON_CODES = [
  { value: 'MARKET_INTELLIGENCE', label: 'Market Intelligence' },
  { value: 'CUSTOMER_COMMITMENT', label: 'Customer Commitment' },
  { value: 'CAPACITY_CONSTRAINT', label: 'Capacity Constraint' },
  { value: 'SUPPLIER_ISSUE', label: 'Supplier Issue' },
  { value: 'QUALITY_CONCERN', label: 'Quality Concern' },
  { value: 'COST_OPTIMIZATION', label: 'Cost Optimization' },
  { value: 'SERVICE_LEVEL', label: 'Service Level Priority' },
  { value: 'INVENTORY_BUFFER', label: 'Inventory Buffer Adjustment' },
  { value: 'DEMAND_CHANGE', label: 'Demand Change' },
  { value: 'EXPEDITE_REQUIRED', label: 'Expedite Required' },
  { value: 'RISK_MITIGATION', label: 'Risk Mitigation' },
  { value: 'OTHER', label: 'Other' },
];

// Decision type icons
const TYPE_ICONS = {
  atp: ShoppingCart,
  rebalancing: RefreshCw,
  po_creation: Package,
  order_tracking: AlertTriangle,
  mo_execution: Factory,
  to_execution: Truck,
  quality: Shield,
  maintenance: Wrench,
  subcontracting: Box,
  forecast_adjustment: TrendingUp,
  inventory_buffer: BarChart3,
};

// Decision type display labels
const TYPE_LABELS = {
  atp: 'ATP',
  rebalancing: 'Rebalancing',
  po_creation: 'PO Creation',
  order_tracking: 'Order Exception',
  mo_execution: 'MO Execution',
  to_execution: 'TO Execution',
  quality: 'Quality',
  maintenance: 'Maintenance',
  subcontracting: 'Subcontracting',
  forecast_adjustment: 'Forecast Adj.',
  inventory_buffer: 'Inv. Buffer',
};

const UrgencyBar = ({ value }) => {
  if (value == null) return null;
  const pct = (value * 100).toFixed(1);
  const color =
    value >= 0.8
      ? 'bg-red-500'
      : value >= 0.5
        ? 'bg-amber-500'
        : 'bg-green-500';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{pct}%</span>
    </div>
  );
};

const ConfidenceChip = ({ value }) => {
  if (value == null)
    return (
      <Badge variant="outline" className="text-xs">
        --
      </Badge>
    );
  const pct = (value * 100).toFixed(1);
  const variant =
    value >= 0.9
      ? 'default'
      : value >= 0.7
        ? 'secondary'
        : 'destructive';
  return (
    <Badge variant={variant} className="text-xs">
      {pct}%
    </Badge>
  );
};

const DecisionCard = ({
  decision,
  onAccept,
  onOverride,
  onAskWhy,
  compact = false,
}) => {
  const navigate = useNavigate();
  const [showOverride, setShowOverride] = useState(false);
  const [reasonCode, setReasonCode] = useState('');
  const [reasonText, setReasonText] = useState('');
  const [acting, setActing] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const [reasoning, setReasoning] = useState(null);
  const [reasoningLoading, setReasoningLoading] = useState(false);

  const Icon = TYPE_ICONS[decision.decision_type] || Package;
  const typeLabel = TYPE_LABELS[decision.decision_type] || decision.decision_type;

  const handleAccept = async () => {
    setActing(true);
    try {
      await onAccept?.(decision);
    } finally {
      setActing(false);
    }
  };

  const handleOverrideSubmit = async () => {
    if (!reasonCode || !reasonText.trim()) return;
    setActing(true);
    try {
      await onOverride?.(decision, reasonCode, reasonText);
      setShowOverride(false);
      setReasonCode('');
      setReasonText('');
    } finally {
      setActing(false);
    }
  };

  const handleNavigate = () => {
    if (decision.deep_link) {
      navigate(decision.deep_link);
    }
  };

  return (
    <Card className="border-l-4 border-l-primary/60 hover:shadow-md transition-shadow">
      <CardContent className={cn('pt-4', compact ? 'pb-3' : 'pb-4')}>
        {/* Header row: type + product/site + urgency + confidence */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <Icon className="h-4 w-4 text-primary flex-shrink-0" />
            <Badge variant="outline" className="text-xs flex-shrink-0">
              {typeLabel}
            </Badge>
            {decision.product_id && (
              <span className="text-xs text-muted-foreground truncate">
                {decision.product_name || decision.product_id}
              </span>
            )}
            {decision.site_id && (
              <span className="text-xs text-muted-foreground truncate">
                @ {decision.site_name || decision.site_id}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <UrgencyBar value={decision.urgency} />
            <ConfidenceChip value={decision.confidence} />
          </div>
        </div>

        {/* Suggested action */}
        {decision.suggested_action && (
          <p className="text-sm mb-3">
            <span className="text-muted-foreground">Decided: </span>
            <span className="font-medium">{decision.suggested_action}</span>
          </p>
        )}

        {/* Action buttons — AIIO: Inspect (expand reasoning) and Override */}
        {!showOverride ? (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="default"
              className="h-7 text-xs bg-blue-600 hover:bg-blue-700"
              onClick={async () => {
                if (showReasoning) {
                  setShowReasoning(false);
                  return;
                }
                // Use pre-computed reasoning if available
                if (decision.decision_reasoning) {
                  setReasoning(decision.decision_reasoning);
                  setShowReasoning(true);
                } else if (reasoning) {
                  setShowReasoning(true);
                } else {
                  // Fetch from ask-why endpoint
                  setReasoningLoading(true);
                  setShowReasoning(true);
                  try {
                    const { decisionStreamApi } = await import('../../services/decisionStreamApi');
                    const result = await decisionStreamApi.askWhy(decision.id, decision.decision_type);
                    setReasoning(result.reasoning || 'No reasoning available.');
                  } catch {
                    setReasoning('Unable to retrieve reasoning for this decision.');
                  } finally {
                    setReasoningLoading(false);
                  }
                }
              }}
              disabled={acting}
            >
              <HelpCircle className="h-3 w-3 mr-1" />
              Inspect
              {showReasoning ? (
                <ChevronUp className="h-3 w-3 ml-0.5" />
              ) : (
                <ChevronDown className="h-3 w-3 ml-0.5" />
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs border-amber-500 text-amber-600 hover:bg-amber-50"
              onClick={() => setShowOverride(true)}
              disabled={acting}
            >
              <Edit3 className="h-3 w-3 mr-1" />
              Override
            </Button>
            <div className="flex-1" />
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={handleNavigate}
              title="Open in Console"
            >
              <ArrowRight className="h-3 w-3" />
            </Button>
          </div>
        ) : null}

        {/* Ask Why reasoning panel (collapsible) */}
        {showReasoning && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-900 animate-in slide-in-from-top-1 duration-200">
            {reasoningLoading ? (
              <div className="flex items-center gap-2 text-blue-600">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Loading reasoning...</span>
              </div>
            ) : (
              <>
                <div className="flex items-start gap-2">
                  <HelpCircle className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
                  <p className="leading-relaxed">{reasoning || decision.decision_reasoning}</p>
                </div>
              </>
            )}
          </div>
        )}

        {showOverride ? (
          /* Override form (inline) */
          <div className="space-y-2 p-3 bg-amber-50 border border-amber-200 rounded-md">
            <select
              className="w-full text-sm border rounded px-2 py-1 bg-background"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
            >
              <option value="">Select override reason...</option>
              {REASON_CODES.map((rc) => (
                <option key={rc.value} value={rc.value}>
                  {rc.label}
                </option>
              ))}
            </select>
            <textarea
              className="w-full text-sm border rounded px-2 py-1 bg-background resize-none"
              rows={2}
              placeholder="Explain your override (required)..."
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs bg-amber-500 hover:bg-amber-600"
                onClick={handleOverrideSubmit}
                disabled={!reasonCode || !reasonText.trim() || acting}
              >
                Submit Override
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowOverride(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

export default DecisionCard;
