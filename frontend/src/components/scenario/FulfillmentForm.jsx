/**
 * Fulfillment Form Component
 *
 * Phase 1: Manual mode fulfillment decision (ATP-based shipment to downstream)
 * Phase 2: Agent copilot mode with AI suggestions
 * Phase 3: Full ATP/CTP integration with warnings and projection chart
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - atp: Available to Promise quantity
 * - demand: Downstream demand (customer orders + backlog)
 * - currentInventory: Current on-hand inventory
 * - agentMode: 'manual', 'copilot', or 'autonomous'
 * - gameId: Game ID for fetching recommendations
 * - playerId: Player ID for fetching recommendations
 * - currentRound: Current round number (for ATP projection)
 * - onSubmit: Callback with fulfill_qty
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  AlertDescription,
  Input,
  Label,
  Slider,
} from '../common';
import {
  Truck as ShipIcon,
  AlertTriangle as WarningIcon,
  CheckCircle as CheckIcon,
  Info as InfoIcon,
  ChevronDown as ExpandMoreIcon,
  ChevronUp as ExpandLessIcon,
  TrendingUp as TrendingUpIcon,
} from 'lucide-react';
import AgentRecommendationPanel from './AgentRecommendationPanel';
import ATPProjectionChart from './ATPProjectionChart';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const FulfillmentForm = ({
  atp,
  demand,
  currentInventory,
  backlog = 0,
  agentMode = 'manual',
  gameId,
  playerId,
  currentRound,
  onSubmit,
  disabled = false,
}) => {
  const [fulfillQty, setFulfillQty] = useState(0);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [recommendation, setRecommendation] = useState(null);
  const [loadingRecommendation, setLoadingRecommendation] = useState(false);
  const [showATPProjection, setShowATPProjection] = useState(false);
  const [atpWarning, setAtpWarning] = useState(null);

  // Fetch agent recommendation in copilot mode
  useEffect(() => {
    const fetchRecommendation = async () => {
      if (agentMode !== 'copilot' || !gameId || !playerId) {
        return;
      }

      setLoadingRecommendation(true);
      try {
        const response = await api.get(
          `/mixed-scenarios/${gameId}/recommendations/fulfillment/${playerId}`
        );
        setRecommendation(response.data);

        // Auto-populate with agent recommendation
        if (response.data.quantity !== undefined) {
          setFulfillQty(response.data.quantity);
        }
      } catch (err) {
        console.error('Failed to fetch agent recommendation:', err);
        setRecommendation(null);
      } finally {
        setLoadingRecommendation(false);
      }
    };

    fetchRecommendation();
  }, [agentMode, gameId, playerId]);

  // Initialize with full demand if ATP allows (manual mode fallback)
  useEffect(() => {
    if (agentMode === 'manual' && demand > 0 && fulfillQty === 0) {
      setFulfillQty(Math.min(demand, atp));
    }
  }, [demand, atp, agentMode]);

  const handleQuantityChange = (event) => {
    const value = parseInt(event.target.value, 10);
    if (isNaN(value) || value < 0) {
      setFulfillQty(0);
      setError('');
      setAtpWarning(null);
      return;
    }

    setFulfillQty(value);

    // Phase 3: Real-time ATP validation
    if (value > atp) {
      const exceeds = value - atp;
      setAtpWarning({
        severity: 'warning',
        message: `Exceeds ATP by ${exceeds} units. This may impact future customer commitments.`,
        exceeds: exceeds,
      });
      setError(`Warning: Exceeds ATP by ${exceeds} units. This will impact future commitments.`);
    } else {
      setAtpWarning(null);
      setError('');
    }
  };

  const handleSliderChange = (value) => {
    const newValue = Array.isArray(value) ? value[0] : value;
    setFulfillQty(newValue);
    if (newValue > atp) {
      setError(`Warning: Exceeds ATP by ${newValue - atp} units. This will impact future commitments.`);
    } else {
      setError('');
    }
  };

  const handleSubmit = async () => {
    if (fulfillQty < 0) {
      setError('Quantity must be non-negative');
      return;
    }

    setSubmitting(true);
    try {
      // Phase 2: Build submission with copilot metadata if available
      const submission = {
        fulfill_qty: fulfillQty,
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
      setError(err.message || 'Failed to submit fulfillment decision');
    } finally {
      setSubmitting(false);
    }
  };

  const handleShipATP = () => {
    setFulfillQty(atp);
    setError('');
    setAtpWarning(null);
  };

  const handleShipFull = () => {
    setFulfillQty(demand);
    if (demand > atp) {
      setError(`Warning: Exceeds ATP by ${demand - atp} units. This will impact future commitments.`);
    } else {
      setError('');
    }
  };

  const handleShipZero = () => {
    setFulfillQty(0);
    setError('');
    setAtpWarning(null);
  };

  // Handle agent recommendation accept
  const handleAcceptRecommendation = (quantity) => {
    setFulfillQty(quantity);
    if (quantity > atp) {
      setError(`Warning: Exceeds ATP by ${quantity - atp} units. This will impact future commitments.`);
    } else {
      setError('');
    }
  };

  // Handle agent recommendation modify
  const handleModifyRecommendation = (quantity) => {
    setFulfillQty(quantity);
  };

  // Calculate fulfillment metrics
  const backlogAfter = Math.max(0, demand - fulfillQty + backlog);
  const backlogChange = backlogAfter - backlog;
  const fillRate = demand > 0 ? (Math.min(fulfillQty, demand) / demand * 100) : 100;

  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center gap-3">
            <ShipIcon className="h-5 w-5 text-primary" />
            <h3 className="text-lg font-semibold">Fulfillment Decision</h3>
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
              currentValue={fulfillQty}
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
                <p className="text-xs text-muted-foreground">Available to Promise (ATP)</p>
                <p className="text-lg font-semibold text-primary">{atp} units</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Downstream Demand</p>
                <p className="text-lg font-semibold">{demand} units</p>
              </div>
              {backlog > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Backlog</p>
                  <p className="text-lg font-semibold text-red-600">{backlog} units</p>
                </div>
              )}
            </div>
          </div>

          <hr className="border-border" />

          {/* Autonomous Mode (Read-only) */}
          {agentMode === 'autonomous' ? (
            <Alert variant="success">
              <CheckIcon className="h-4 w-4" />
              <AlertDescription>
                AI Agent will automatically fulfill downstream orders based on ATP availability.
                You can observe the decision after submission.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {/* Fulfillment Input (Manual & Copilot) */}
              <div className="space-y-3">
                <Label htmlFor="fulfillQty">Ship Quantity</Label>
                <div className="relative">
                  <Input
                    id="fulfillQty"
                    type="number"
                    value={fulfillQty}
                    onChange={handleQuantityChange}
                    disabled={disabled || submitting}
                    min={0}
                    max={demand + 100}
                    className="pr-16"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    units
                  </span>
                </div>

                {/* Slider with marks */}
                <div className="pt-2">
                  <Slider
                    value={[fulfillQty]}
                    onValueChange={handleSliderChange}
                    min={0}
                    max={Math.max(demand, atp) + 50}
                    step={1}
                    disabled={disabled || submitting}
                  />
                  <div className="flex justify-between text-xs text-muted-foreground mt-1">
                    <span>0</span>
                    <span>ATP ({atp})</span>
                    <span>Demand ({demand})</span>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleShipZero}
                  disabled={disabled || submitting}
                >
                  Ship 0
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleShipATP}
                  disabled={disabled || submitting}
                >
                  Ship ATP ({atp})
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleShipFull}
                  disabled={disabled || submitting}
                >
                  Ship Full Demand ({demand})
                </Button>
              </div>
            </>
          )}

          {/* Phase 3: ATP Warning with Projection Link */}
          {atpWarning && (
            <Alert variant="warning">
              <WarningIcon className="h-4 w-4" />
              <div className="space-y-2">
                <AlertDescription>{atpWarning.message}</AlertDescription>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowATPProjection(!showATPProjection)}
                    className="gap-1"
                  >
                    <TrendingUpIcon className="h-4 w-4" />
                    {showATPProjection ? 'Hide' : 'View'} ATP Projection
                    {showATPProjection ? (
                      <ExpandLessIcon className="h-4 w-4" />
                    ) : (
                      <ExpandMoreIcon className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleShipATP}
                    disabled={disabled || submitting}
                  >
                    Ship ATP Only ({atp} units)
                  </Button>
                </div>
              </div>
            </Alert>
          )}

          {/* Phase 3: ATP Projection Chart (Collapsible) */}
          {gameId && playerId && currentRound && showATPProjection && (
            <div className="border rounded-lg p-4 bg-muted/30">
              <ATPProjectionChart
                gameId={gameId}
                playerId={playerId}
                currentRound={currentRound}
                periods={8}
              />
            </div>
          )}

          {/* Validation Warning (Legacy) */}
          {error && !atpWarning && (
            <Alert variant="warning">
              <WarningIcon className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Impact Preview */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <p className="text-sm font-medium mb-3">Impact Preview</p>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Inventory After Shipment</p>
                <p className="text-sm font-medium">{currentInventory - fulfillQty} units</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Fill Rate</p>
                <p
                  className={cn(
                    'text-sm font-medium',
                    fillRate >= 95
                      ? 'text-emerald-600'
                      : fillRate >= 80
                      ? 'text-amber-600'
                      : 'text-red-600'
                  )}
                >
                  {fillRate.toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Backlog After</p>
                <p
                  className={cn(
                    'text-sm font-medium',
                    backlogAfter > backlog ? 'text-red-600' : 'text-emerald-600'
                  )}
                >
                  {backlogAfter} units
                  {backlogChange !== 0 && (
                    <span
                      className={cn(
                        'ml-1 text-xs',
                        backlogChange > 0 ? 'text-red-600' : 'text-emerald-600'
                      )}
                    >
                      ({backlogChange > 0 ? '+' : ''}{backlogChange})
                    </span>
                  )}
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
            <ShipIcon className="h-4 w-4" />
            {submitting ? 'Submitting...' : `Confirm Fulfillment (${fulfillQty} units)`}
          </Button>

          {/* Info Note */}
          <Alert variant="info" className="mt-2">
            <InfoIcon className="h-4 w-4" />
            <AlertDescription className="text-xs">
              <strong>Available to Promise (ATP)</strong> = Current Inventory - Committed Orders.
              Shipping more than ATP may impact future customer commitments.
            </AlertDescription>
          </Alert>
        </div>
      </CardContent>
    </Card>
  );
};

export default FulfillmentForm;
