/**
 * Decision Card Component
 *
 * Compact actionable card for a pending TRM decision, displayed inline
 * in the Decision Stream. Supports Inspect, Modify, Cancel, and Navigate.
 *
 * Override flow:
 *   - Modify: User changes decision values (qty, date, supplier, etc.) + reason
 *   - Cancel: User rejects the action entirely (no execution) + reason
 *   Both require a reason code and explanation for the learning flywheel.
 */
import React, { useState } from 'react';
import Markdown from 'react-markdown';
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
  XCircle,
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

// Decision-type-specific editable fields (must match backend EDITABLE_FIELDS_MAP)
const EDITABLE_FIELDS = {
  atp: [
    { key: 'allocated_qty', label: 'Allocated Qty', type: 'number' },
  ],
  rebalancing: [
    { key: 'qty', label: 'Transfer Qty', type: 'number' },
  ],
  po_creation: [
    { key: 'qty', label: 'Order Qty', type: 'number' },
    { key: 'supplier_id', label: 'Supplier', type: 'text' },
    { key: 'due_date', label: 'Due Date', type: 'date' },
  ],
  order_tracking: [
    { key: 'recommended_action', label: 'Action', type: 'select',
      options: ['find_alternate', 'expedite', 'cancel', 'split', 'reroute', 'accept_delay'] },
  ],
  mo_execution: [
    { key: 'qty', label: 'Planned Qty', type: 'number' },
    { key: 'priority', label: 'Priority', type: 'number' },
  ],
  to_execution: [
    { key: 'qty', label: 'Planned Qty', type: 'number' },
  ],
  quality: [
    { key: 'disposition', label: 'Disposition', type: 'select',
      options: ['accept', 'reject', 'rework', 'scrap', 'use_as_is', 'return_to_vendor'] },
  ],
  maintenance: [
    { key: 'scheduled_date', label: 'Schedule Date', type: 'date' },
    { key: 'action', label: 'Action', type: 'select',
      options: ['schedule', 'defer', 'expedite', 'combine', 'outsource'] },
  ],
  subcontracting: [
    { key: 'routing', label: 'Routing', type: 'select',
      options: ['route_external', 'keep_internal', 'split', 'change_vendor'] },
    { key: 'qty', label: 'Planned Qty', type: 'number' },
  ],
  forecast_adjustment: [
    { key: 'direction', label: 'Direction', type: 'select',
      options: ['up', 'down', 'no_change'] },
    { key: 'magnitude_pct', label: 'Adjustment %', type: 'number' },
  ],
  inventory_buffer: [
    { key: 'buffer_qty', label: 'Buffer Qty', type: 'number' },
    { key: 'multiplier', label: 'Multiplier', type: 'number' },
  ],
};

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

const URGENCY_COLORS = {
  Critical: 'bg-red-100 text-red-700',
  High: 'bg-orange-100 text-orange-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low: 'bg-blue-100 text-blue-700',
  Routine: 'bg-green-100 text-green-700',
};

const LIKELIHOOD_COLORS = {
  'Almost Certain': 'bg-green-100 text-green-700',
  Likely: 'bg-blue-100 text-blue-700',
  Possible: 'bg-amber-100 text-amber-700',
  Unlikely: 'bg-orange-100 text-orange-700',
  Never: 'bg-red-100 text-red-700',
};

const UrgencyBar = ({ value }) => {
  if (value == null) return null;
  const bg = URGENCY_COLORS[value] || 'bg-gray-100 text-gray-700';
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground font-medium">Urgency</span>
      <span className={cn('text-xs font-semibold px-1.5 py-0.5 rounded', bg)}>{value}</span>
    </div>
  );
};

const ConfidenceChip = ({ value }) => {
  if (value == null) return null;
  const bg = LIKELIHOOD_COLORS[value] || 'bg-gray-100 text-gray-700';
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground font-medium">Likelihood</span>
      <span className={cn('text-xs font-semibold px-1.5 py-0.5 rounded', bg)}>{value}</span>
    </div>
  );
};

/** Render a single editable field */
const EditableField = ({ field, value, onChange }) => {
  const inputClass = 'w-full text-sm border rounded px-2 py-1.5 bg-background';

  if (field.type === 'select') {
    return (
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">{field.label}</label>
        <select className={inputClass} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
          {(field.options || []).map((opt) => (
            <option key={opt} value={opt}>
              {opt.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (field.type === 'date') {
    return (
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">{field.label}</label>
        <input type="date" className={inputClass} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
      </div>
    );
  }
  // number or text
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground mb-1 block">{field.label}</label>
      <input
        type={field.type === 'number' ? 'number' : 'text'}
        className={inputClass}
        value={value ?? ''}
        onChange={(e) => onChange(field.type === 'number' ? e.target.value : e.target.value)}
        step={field.type === 'number' ? 'any' : undefined}
      />
    </div>
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
  // overrideMode: null | 'choose' | 'modify' | 'cancel'
  const [overrideMode, setOverrideMode] = useState(null);
  const [reasonCode, setReasonCode] = useState('');
  const [reasonText, setReasonText] = useState('');
  const [modifiedValues, setModifiedValues] = useState({});
  const [acting, setActing] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const [reasoning, setReasoning] = useState(null);
  const [reasoningLoading, setReasoningLoading] = useState(false);

  const Icon = TYPE_ICONS[decision.decision_type] || Package;
  const typeLabel = TYPE_LABELS[decision.decision_type] || decision.decision_type;
  const editableFields = EDITABLE_FIELDS[decision.decision_type] || [];

  // Initialize modifiedValues from decision.editable_values when opening Modify
  const openModify = () => {
    const initial = {};
    for (const f of editableFields) {
      initial[f.key] = decision.editable_values?.[f.key] ?? '';
    }
    setModifiedValues(initial);
    setOverrideMode('modify');
  };

  const openCancel = () => {
    setOverrideMode('cancel');
  };

  const closeOverride = () => {
    setOverrideMode(null);
    setReasonCode('');
    setReasonText('');
    setModifiedValues({});
  };

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
      await onOverride?.(
        decision,
        reasonCode,
        reasonText,
        overrideMode,
        overrideMode === 'modify' ? modifiedValues : null,
      );
      closeOverride();
    } finally {
      setActing(false);
    }
  };

  const handleNavigate = () => {
    if (decision.deep_link) {
      navigate(decision.deep_link);
    }
  };

  const showButtons = overrideMode === null;

  return (
    <Card className="border-l-4 border-l-primary/60 hover:shadow-md transition-shadow">
      <CardContent className={cn('pt-4', compact ? 'pb-3' : 'pb-4')}>
        {/* Header row: type + product/site + urgency + likelihood */}
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
            <ConfidenceChip value={decision.likelihood} />
          </div>
        </div>

        {/* Suggested action */}
        {decision.suggested_action && (
          <p className="text-sm mb-3">
            <span className="text-muted-foreground">Decided: </span>
            <span className="font-medium">{decision.suggested_action}</span>
          </p>
        )}

        {/* Action buttons — Inspect, Override */}
        {showButtons && (
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
                if (decision.decision_reasoning) {
                  setReasoning(decision.decision_reasoning);
                  setShowReasoning(true);
                } else if (reasoning) {
                  setShowReasoning(true);
                } else {
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
              className="h-7 text-xs border-orange-500 text-orange-600 hover:bg-orange-50"
              onClick={() => setOverrideMode('choose')}
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
        )}

        {/* Ask Why reasoning panel (collapsible) */}
        {showReasoning && (
          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-900 animate-in slide-in-from-top-1 duration-200">
            {reasoningLoading ? (
              <div className="flex items-center gap-2 text-blue-600">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Loading reasoning...</span>
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <HelpCircle className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <div className="leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-strong:text-blue-800">
                  <Markdown>{reasoning || decision.decision_reasoning}</Markdown>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Override chooser — Modify or Cancel */}
        {overrideMode === 'choose' && (
          <div className="space-y-2 p-3 bg-orange-50 border border-orange-200 rounded-md mt-2 animate-in slide-in-from-top-1 duration-200">
            <div className="text-xs font-semibold text-orange-800 uppercase tracking-wide">
              How would you like to override?
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs border-amber-500 text-amber-700 hover:bg-amber-100"
                onClick={openModify}
              >
                <Edit3 className="h-3 w-3 mr-1" />
                Modify Values
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs border-red-500 text-red-700 hover:bg-red-100"
                onClick={openCancel}
              >
                <XCircle className="h-3 w-3 mr-1" />
                Cancel Action
              </Button>
              <div className="flex-1" />
              <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={closeOverride}>
                Back
              </Button>
            </div>
          </div>
        )}

        {/* Modify form — editable fields + reason */}
        {overrideMode === 'modify' && (
          <div className="space-y-3 p-3 bg-amber-50 border border-amber-200 rounded-md mt-2">
            <div className="text-xs font-semibold text-amber-800 uppercase tracking-wide">
              Modify Decision Values
            </div>
            {/* Decision-type-specific editable fields */}
            <div className="grid grid-cols-2 gap-2">
              {editableFields.map((field) => (
                <EditableField
                  key={field.key}
                  field={field}
                  value={modifiedValues[field.key]}
                  onChange={(val) =>
                    setModifiedValues((prev) => ({ ...prev, [field.key]: val }))
                  }
                />
              ))}
            </div>
            {/* Reason code + text (required) */}
            <select
              className="w-full text-sm border rounded px-2 py-1 bg-background"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
            >
              <option value="">Select reason for modification...</option>
              {REASON_CODES.map((rc) => (
                <option key={rc.value} value={rc.value}>{rc.label}</option>
              ))}
            </select>
            <textarea
              className="w-full text-sm border rounded px-2 py-1 bg-background resize-none"
              rows={2}
              placeholder="Explain your modification (required)..."
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
                {acting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
                Submit Modification
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={closeOverride}>
                Back
              </Button>
            </div>
          </div>
        )}

        {/* Cancel form — reason only */}
        {overrideMode === 'cancel' && (
          <div className="space-y-2 p-3 bg-red-50 border border-red-200 rounded-md mt-2">
            <div className="text-xs font-semibold text-red-800 uppercase tracking-wide">
              Cancel This Action
            </div>
            <p className="text-xs text-red-700">
              This will reject the agent's recommendation entirely. No action will be taken.
            </p>
            <select
              className="w-full text-sm border rounded px-2 py-1 bg-background"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
            >
              <option value="">Select reason for cancellation...</option>
              {REASON_CODES.map((rc) => (
                <option key={rc.value} value={rc.value}>{rc.label}</option>
              ))}
            </select>
            <textarea
              className="w-full text-sm border rounded px-2 py-1 bg-background resize-none"
              rows={2}
              placeholder="Explain why this action should not be taken (required)..."
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs bg-red-500 hover:bg-red-600 text-white"
                onClick={handleOverrideSubmit}
                disabled={!reasonCode || !reasonText.trim() || acting}
              >
                {acting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
                Confirm Cancellation
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={closeOverride}>
                Back
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default DecisionCard;
