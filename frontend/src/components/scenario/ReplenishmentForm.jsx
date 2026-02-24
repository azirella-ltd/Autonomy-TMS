/**
 * Replenishment Form Component
 *
 * Phase 1: Manual mode replenishment decision (upstream order placement)
 * Phase 2: Agent copilot mode with AI suggestions
 * Phase 3: Full CTP calculation and capacity display for manufacturers
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - currentInventory: Current on-hand inventory after fulfillment
 * - pipeline: Array of in-transit shipments [{quantity, origin, arrival_round}]
 * - backlog: Unfulfilled orders
 * - demandHistory: Recent demand history for recommendation
 * - currentRound: Current round number
 * - agentMode: 'manual', 'copilot', or 'autonomous'
 * - gameId: Game ID for fetching recommendations
 * - scenarioUserId: ScenarioUser ID for fetching recommendations
 * - nodeType: Node type ('manufacturer', 'inventory', etc.)
 * - itemId: Item ID (for CTP calculation on manufacturers)
 * - onSubmit: Callback with order_qty
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  AlertTitle,
  AlertDescription,
  Input,
  Label,
  Slider,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableContainer,
} from '../common';
import {
  ShoppingCart as OrderIcon,
  Truck as ShipmentIcon,
  AlertTriangle as WarningIcon,
  CheckCircle as CheckIcon,
  Info as InfoIcon,
  TrendingUp as TrendingUpIcon,
} from 'lucide-react';
import AgentRecommendationPanel from './AgentRecommendationPanel';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const ReplenishmentForm = ({
  currentInventory,
  pipeline = [],
  backlog = 0,
  demandHistory = [],
  currentRound = 1,
  agentMode = 'manual',
  gameId,
  scenarioUserId,
  nodeType = 'inventory',
  itemId = 1,
  onSubmit,
  disabled = false,
}) => {
  const [orderQty, setOrderQty] = useState(0);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [recommendation, setRecommendation] = useState(null);
  const [loadingRecommendation, setLoadingRecommendation] = useState(false);
  const [ctpData, setCtpData] = useState(null);
  const [loadingCTP, setLoadingCTP] = useState(false);

  // Calculate recommended order based on base stock policy
  const calculateRecommendedOrder = () => {
    if (demandHistory.length === 0) return 100; // Default initial order

    // Simple base stock policy: target = avg demand * (lead time + review period) + safety stock
    const avgDemand = demandHistory.reduce((sum, d) => sum + d, 0) / demandHistory.length;
    const leadTime = 2; // Assume 2-round lead time
    const reviewPeriod = 1;
    const safetyStockMultiplier = 1.5; // 50% safety buffer

    const baseStock = Math.ceil(avgDemand * (leadTime + reviewPeriod) * safetyStockMultiplier);
    const pipelineTotal = pipeline.reduce((sum, shipment) => sum + shipment.quantity, 0);
    const inventoryPosition = currentInventory + pipelineTotal - backlog;

    return Math.max(0, baseStock - inventoryPosition);
  };

  const recommendedOrder = calculateRecommendedOrder();

  // Fetch agent recommendation in copilot mode
  useEffect(() => {
    const fetchRecommendation = async () => {
      if (agentMode !== 'copilot' || !gameId || !scenarioUserId) {
        return;
      }

      setLoadingRecommendation(true);
      try {
        const response = await api.get(
          `/mixed-scenarios/${gameId}/recommendations/replenishment/${scenarioUserId}`
        );
        setRecommendation(response.data);

        // Auto-populate with agent recommendation
        if (response.data.quantity !== undefined) {
          setOrderQty(response.data.quantity);
        }
      } catch (err) {
        console.error('Failed to fetch agent recommendation:', err);
        setRecommendation(null);
      } finally {
        setLoadingRecommendation(false);
      }
    };

    fetchRecommendation();
  }, [agentMode, gameId, scenarioUserId]);

  // Initialize with recommended order (manual mode fallback)
  useEffect(() => {
    if (agentMode === 'manual' && orderQty === 0) {
      setOrderQty(recommendedOrder);
    }
  }, [recommendedOrder, agentMode]);

  // Phase 3: Fetch CTP data for manufacturer nodes
  useEffect(() => {
    const fetchCTP = async () => {
      if (nodeType !== 'manufacturer' || !gameId || !scenarioUserId || !itemId) {
        return;
      }

      setLoadingCTP(true);
      try {
        const response = await api.get(
          `/mixed-scenarios/${gameId}/ctp/${scenarioUserId}?item_id=${itemId}`
        );
        setCtpData(response.data);
      } catch (err) {
        console.error('Failed to fetch CTP:', err);
        setCtpData(null);
      } finally {
        setLoadingCTP(false);
      }
    };

    fetchCTP();
  }, [nodeType, gameId, scenarioUserId, itemId, currentRound]);

  const handleQuantityChange = (event) => {
    const value = parseInt(event.target.value, 10);
    if (isNaN(value) || value < 0) {
      setOrderQty(0);
      setError('');
      return;
    }

    setOrderQty(value);
    setError('');
  };

  const handleSliderChange = (value) => {
    const newValue = Array.isArray(value) ? value[0] : value;
    setOrderQty(newValue);
    setError('');
  };

  const handleSubmit = async () => {
    if (orderQty < 0) {
      setError('Order quantity must be non-negative');
      return;
    }

    setSubmitting(true);
    try {
      // Phase 2: Build submission with copilot metadata if available
      const submission = {
        order_qty: orderQty,
      };

      // Include AI recommendation metadata for RLHF if in copilot mode
      if (agentMode === 'copilot' && recommendation) {
        submission.ai_recommendation = recommendation.quantity;
        submission.ai_confidence = recommendation.confidence;
        submission.ai_agent_type = recommendation.agent_type;
        submission.ai_reasoning = recommendation.reasoning;
      }

      await onSubmit(submission);
      setError('');
    } catch (err) {
      setError(err.message || 'Failed to submit replenishment order');
    } finally {
      setSubmitting(false);
    }
  };

  const handleOrderRecommended = () => {
    setOrderQty(recommendedOrder);
    setError('');
  };

  const handleOrderZero = () => {
    setOrderQty(0);
    setError('');
  };

  const handleOrderDouble = () => {
    setOrderQty(recommendedOrder * 2);
    setError('');
  };

  // Handle agent recommendation accept
  const handleAcceptRecommendation = (quantity) => {
    setOrderQty(quantity);
    setError('');
  };

  // Handle agent recommendation modify
  const handleModifyRecommendation = (quantity) => {
    setOrderQty(quantity);
  };

  // Calculate projected inventory
  const pipelineTotal = pipeline.reduce((sum, shipment) => sum + shipment.quantity, 0);
  const inventoryPosition = currentInventory + pipelineTotal + orderQty - backlog;
  const avgDemand = demandHistory.length > 0
    ? demandHistory.reduce((sum, d) => sum + d, 0) / demandHistory.length
    : 0;
  const daysOfSupply = avgDemand > 0 ? inventoryPosition / avgDemand : 0;

  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center gap-3">
            <OrderIcon className="h-5 w-5 text-primary" />
            <h3 className="text-lg font-semibold">Replenishment Decision</h3>
            {agentMode === 'autonomous' && (
              <Badge variant="info" size="sm">AI Controlled</Badge>
            )}
            {agentMode === 'copilot' && (
              <Badge variant="warning" size="sm">AI Assisted</Badge>
            )}
          </div>

          {/* Agent Recommendation Panel (Copilot Mode) */}
          {agentMode === 'copilot' && (
            <AgentRecommendationPanel
              recommendation={recommendation}
              onAccept={handleAcceptRecommendation}
              onModify={handleModifyRecommendation}
              currentValue={orderQty}
              disabled={disabled || submitting}
              loading={loadingRecommendation}
            />
          )}

          <hr className="border-border" />

          {/* Current State */}
          <div>
            <p className="text-sm text-muted-foreground mb-2">Current State</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">On-Hand Inventory</p>
                <p className="text-lg font-semibold">{currentInventory} units</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">In-Transit (Pipeline)</p>
                <p className="text-lg font-semibold text-blue-600">{pipelineTotal} units</p>
              </div>
              {backlog > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Backlog</p>
                  <p className="text-lg font-semibold text-red-600">{backlog} units</p>
                </div>
              )}
              {avgDemand > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Avg Demand (Recent)</p>
                  <p className="text-lg font-semibold">{avgDemand.toFixed(1)} units/round</p>
                </div>
              )}
            </div>
          </div>

          <hr className="border-border" />

          {/* Pipeline Visibility */}
          {pipeline.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <ShipmentIcon className="h-4 w-4 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">In-Transit Shipments</p>
              </div>
              <TableContainer>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Quantity</TableHead>
                      <TableHead>Origin</TableHead>
                      <TableHead>Arrival Round</TableHead>
                      <TableHead>Rounds Until Arrival</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pipeline.map((shipment, idx) => (
                      <TableRow key={idx}>
                        <TableCell>
                          <span className="font-semibold">{shipment.quantity}</span> units
                        </TableCell>
                        <TableCell>{shipment.origin || 'Upstream'}</TableCell>
                        <TableCell>{shipment.arrival_round || 'N/A'}</TableCell>
                        <TableCell>
                          {shipment.arrival_round
                            ? Math.max(0, shipment.arrival_round - currentRound)
                            : 'N/A'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </div>
          )}

          {pipeline.length === 0 && (
            <Alert variant="warning">
              <InfoIcon className="h-4 w-4" />
              <AlertDescription>
                No shipments currently in transit. Consider placing an order to replenish inventory.
              </AlertDescription>
            </Alert>
          )}

          <hr className="border-border" />

          {/* Phase 3: CTP Display (Manufacturers Only) */}
          {nodeType === 'manufacturer' && ctpData && !loadingCTP && (
            <div className="p-4 bg-blue-50 dark:bg-blue-950/30 rounded-lg">
              <p className="text-sm font-semibold mb-3">
                Capable to Promise (CTP) - Production Capacity
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Production Capacity</p>
                  <p className="text-sm font-semibold">{ctpData.production_capacity} units/round</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Current Commitments</p>
                  <p className="text-sm">{ctpData.current_commitments} units</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Yield Rate</p>
                  <p className="text-sm">{(ctpData.yield_rate * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Available CTP</p>
                  <p className="text-sm font-semibold text-primary">
                    {ctpData.ctp} units
                  </p>
                  <p className="text-xs text-muted-foreground">
                    ({((ctpData.ctp / ctpData.production_capacity) * 100).toFixed(0)}% capacity)
                  </p>
                </div>
              </div>

              {/* Component Constraints Warning */}
              {ctpData.component_constraints && ctpData.component_constraints.length > 0 &&
               ctpData.component_constraints.some(c => c.shortfall > 0) && (
                <Alert variant="warning" className="mt-3">
                  <WarningIcon className="h-4 w-4" />
                  <div>
                    <AlertTitle className="text-xs font-bold">Component Constraints</AlertTitle>
                    <AlertDescription className="text-xs">
                      Production limited by component availability:
                    </AlertDescription>
                    <ul className="mt-1 pl-4 list-disc text-xs">
                      {ctpData.component_constraints
                        .filter(c => c.shortfall > 0)
                        .map((constraint, idx) => (
                          <li key={idx}>
                            <strong>{constraint.item_name}</strong>: {constraint.shortfall} units short
                            (need {constraint.required_per_unit} per unit, have {constraint.available_atp} ATP)
                          </li>
                        ))}
                    </ul>
                  </div>
                </Alert>
              )}

              {/* Capacity Utilization Indicator */}
              {ctpData.constrained_by && (
                <Badge variant="warning" className="mt-2">
                  Constrained by: {ctpData.constrained_by.replace('_', ' ')}
                </Badge>
              )}
            </div>
          )}

          {nodeType === 'manufacturer' && loadingCTP && (
            <div className="p-4 text-center">
              <p className="text-xs text-muted-foreground">
                Loading production capacity data...
              </p>
            </div>
          )}

          <hr className="border-border" />

          {/* Autonomous Mode (Read-only) */}
          {agentMode === 'autonomous' ? (
            <Alert variant="success">
              <CheckIcon className="h-4 w-4" />
              <AlertDescription>
                AI Agent will automatically place replenishment orders based on demand forecasts and inventory position.
                You can observe the decision after submission.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {/* Replenishment Input (Manual & Copilot) */}
              <div className="space-y-3">
                <Label htmlFor="orderQty">Order Quantity (from upstream)</Label>
                <div className="relative">
                  <Input
                    id="orderQty"
                    type="number"
                    value={orderQty}
                    onChange={handleQuantityChange}
                    disabled={disabled || submitting}
                    min={0}
                    max={9999}
                    className="pr-16"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    units
                  </span>
                </div>

                {/* Slider with marks */}
                <div className="pt-2">
                  <Slider
                    value={[orderQty]}
                    onValueChange={handleSliderChange}
                    min={0}
                    max={Math.max(recommendedOrder * 2, 500)}
                    step={1}
                    disabled={disabled || submitting}
                  />
                  <div className="flex justify-between text-xs text-muted-foreground mt-1">
                    <span>0</span>
                    <span>Rec ({recommendedOrder})</span>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleOrderZero}
                  disabled={disabled || submitting}
                >
                  Order 0
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleOrderRecommended}
                  disabled={disabled || submitting}
                  className="gap-1"
                >
                  <TrendingUpIcon className="h-3 w-3" />
                  Order Recommended ({recommendedOrder})
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleOrderDouble}
                  disabled={disabled || submitting}
                >
                  Order Double ({recommendedOrder * 2})
                </Button>
              </div>
            </>
          )}

          {/* Validation Warning */}
          {error && (
            <Alert variant="warning">
              <WarningIcon className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Impact Preview */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <p className="text-sm font-medium mb-3">Impact Preview (After Order Arrives)</p>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Inventory Position</p>
                <p className="text-sm font-medium">{inventoryPosition} units</p>
                <p className="text-xs text-muted-foreground">
                  (On-hand + Pipeline + Order - Backlog)
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Days of Supply</p>
                <p
                  className={cn(
                    'text-sm font-medium',
                    daysOfSupply >= 4
                      ? 'text-emerald-600'
                      : daysOfSupply >= 2
                      ? 'text-amber-600'
                      : 'text-red-600'
                  )}
                >
                  {daysOfSupply > 0 ? daysOfSupply.toFixed(1) : 'N/A'} days
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">vs Recommended</p>
                <p
                  className={cn(
                    'text-sm font-medium',
                    orderQty >= recommendedOrder * 0.8 && orderQty <= recommendedOrder * 1.2
                      ? 'text-emerald-600'
                      : 'text-amber-600'
                  )}
                >
                  {orderQty > recommendedOrder
                    ? `+${orderQty - recommendedOrder}`
                    : orderQty < recommendedOrder
                    ? `${orderQty - recommendedOrder}`
                    : 'Exact'}
                </p>
              </div>
            </div>
          </div>

          {/* Submit Button */}
          <Button
            size="lg"
            onClick={handleSubmit}
            disabled={disabled || submitting || (agentMode === 'autonomous')}
            className="w-full gap-2"
          >
            <OrderIcon className="h-4 w-4" />
            {submitting ? 'Submitting...' : `Confirm Replenishment Order (${orderQty} units)`}
          </Button>

          {/* Info Note */}
          <Alert variant="info" className="mt-2">
            <InfoIcon className="h-4 w-4" />
            <AlertDescription className="text-xs">
              <strong>Inventory Position</strong> = On-hand + In-transit - Backlog. Order to maintain target service level
              based on demand forecasts and lead times.
            </AlertDescription>
          </Alert>
        </div>
      </CardContent>
    </Card>
  );
};

export default ReplenishmentForm;
