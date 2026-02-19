/**
 * Agent Recommendation Panel Component
 *
 * Phase 2: Agent Copilot Mode
 * Displays agent recommendation with reasoning, confidence, alternatives, and impact preview.
 * Supports quick actions: Accept / Modify / Override
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - recommendation: RecommendationResult from API
 * - onAccept: Callback when user accepts recommendation
 * - onModify: Callback when user modifies recommendation
 * - currentValue: Current input value (for comparison)
 * - disabled: Whether panel is disabled
 * - loading: Whether recommendation is loading
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Button,
  Alert,
  AlertTitle,
  AlertDescription,
  Progress,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableContainer,
} from '../common';
import {
  ThumbsUp as AcceptIcon,
  Pencil as ModifyIcon,
  AlertTriangle as OverrideIcon,
  ChevronDown as ExpandMoreIcon,
  ChevronUp as ExpandLessIcon,
  Brain as AgentIcon,
  TrendingUp as ImpactIcon,
  History as HistoryIcon,
  Lightbulb as AlternativeIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const AgentRecommendationPanel = ({
  recommendation,
  onAccept,
  onModify,
  currentValue = null,
  disabled = false,
  loading = false,
}) => {
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [showImpactDetails, setShowImpactDetails] = useState(false);
  const [showHistoricalPerf, setShowHistoricalPerf] = useState(false);

  if (loading) {
    return (
      <Card className="mb-4 border-l-4 border-l-primary">
        <CardContent className="pt-4">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <AgentIcon className="h-5 w-5 text-primary animate-pulse" />
              <h3 className="text-lg font-semibold">Getting AI Recommendation...</h3>
            </div>
            <Progress value={undefined} className="animate-pulse" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!recommendation) {
    return null;
  }

  // Determine if user has modified the recommendation
  const isModified = currentValue !== null && currentValue !== recommendation.quantity;
  const isOverride = isModified && Math.abs(currentValue - recommendation.quantity) > recommendation.quantity * 0.1;

  // Get confidence color
  const getConfidenceVariant = (confidence) => {
    if (confidence >= 0.9) return 'success';
    if (confidence >= 0.75) return 'info';
    if (confidence >= 0.6) return 'warning';
    return 'error';
  };

  // Get agent type variant
  const getAgentTypeVariant = (agentType) => {
    const variants = {
      LLM: 'info',
      GNN: 'secondary',
      TRM: 'default',
      HEURISTIC: 'secondary',
    };
    return variants[agentType] || 'secondary';
  };

  // Format percentage
  const formatPct = (value) => `${(value * 100).toFixed(1)}%`;

  return (
    <Card
      className={cn(
        'mb-4 border-l-4',
        isOverride ? 'border-l-amber-500 bg-amber-50/50 dark:bg-amber-950/20' : 'border-l-primary',
        disabled && 'opacity-60'
      )}
    >
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex justify-between items-start">
            <div className="flex items-start gap-3">
              <AgentIcon className="h-6 w-6 text-primary mt-1" />
              <div>
                <h3 className="text-lg font-semibold mb-1">AI Recommendation</h3>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={getAgentTypeVariant(recommendation.agent_type)} size="sm">
                    {recommendation.agent_type}
                  </Badge>
                  <Badge variant={getConfidenceVariant(recommendation.confidence)} size="sm">
                    Confidence: {formatPct(recommendation.confidence)}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Recommended Quantity (Large) */}
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Recommended</p>
              <p className="text-3xl font-bold text-primary">{recommendation.quantity}</p>
              <p className="text-xs text-muted-foreground">units</p>
            </div>
          </div>

          {/* Reasoning */}
          <Alert variant="info">
            <AlternativeIcon className="h-4 w-4" />
            <AlertTitle>Agent Reasoning</AlertTitle>
            <AlertDescription>{recommendation.reasoning}</AlertDescription>
          </Alert>

          {/* Modification Warning */}
          {isModified && (
            <Alert variant={isOverride ? 'warning' : 'info'}>
              <OverrideIcon className="h-4 w-4" />
              <AlertTitle>
                {isOverride ? 'Override Detected' : 'Modified Recommendation'}
              </AlertTitle>
              <AlertDescription>
                You've {isOverride ? 'significantly overridden' : 'modified'} the agent's
                recommendation ({recommendation.quantity} → {currentValue} units).
                {isOverride && ' This may require manager approval.'}
              </AlertDescription>
            </Alert>
          )}

          {/* Quick Actions */}
          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={() => onAccept(recommendation.quantity)}
              disabled={disabled}
              className="gap-2"
            >
              <AcceptIcon className="h-4 w-4" />
              Accept ({recommendation.quantity} units)
            </Button>
            <Button
              variant="outline"
              onClick={() => onModify(recommendation.quantity)}
              disabled={disabled}
              className="gap-2"
            >
              <ModifyIcon className="h-4 w-4" />
              Modify
            </Button>
          </div>

          <hr className="border-border" />

          {/* Impact Preview (Collapsible) */}
          <div>
            <button
              className="flex justify-between items-center w-full py-2 hover:bg-muted/50 rounded-md px-2 transition-colors"
              onClick={() => setShowImpactDetails(!showImpactDetails)}
            >
              <div className="flex items-center gap-2">
                <ImpactIcon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Impact Preview</span>
              </div>
              {showImpactDetails ? (
                <ExpandLessIcon className="h-4 w-4" />
              ) : (
                <ExpandMoreIcon className="h-4 w-4" />
              )}
            </button>

            {showImpactDetails && recommendation.impact_preview_if_accept && (
              <div className="mt-3">
                <TableContainer>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50">
                        <TableHead>Metric</TableHead>
                        <TableHead className="text-right">If Accept</TableHead>
                        {isModified && recommendation.impact_preview_if_override && (
                          <TableHead className="text-right">If Override</TableHead>
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell>Inventory After</TableCell>
                        <TableCell className="text-right">
                          {recommendation.impact_preview_if_accept.inventory_after}
                        </TableCell>
                        {isModified && recommendation.impact_preview_if_override && (
                          <TableCell className="text-right">
                            {recommendation.impact_preview_if_override.inventory_after}
                          </TableCell>
                        )}
                      </TableRow>
                      <TableRow>
                        <TableCell>Fill Rate</TableCell>
                        <TableCell className="text-right">
                          {formatPct(recommendation.impact_preview_if_accept.fill_rate)}
                        </TableCell>
                        {isModified && recommendation.impact_preview_if_override && (
                          <TableCell className="text-right">
                            {formatPct(recommendation.impact_preview_if_override.fill_rate)}
                          </TableCell>
                        )}
                      </TableRow>
                      <TableRow>
                        <TableCell>Backlog After</TableCell>
                        <TableCell className="text-right">
                          {recommendation.impact_preview_if_accept.backlog_after}
                        </TableCell>
                        {isModified && recommendation.impact_preview_if_override && (
                          <TableCell className="text-right">
                            {recommendation.impact_preview_if_override.backlog_after}
                          </TableCell>
                        )}
                      </TableRow>
                      <TableRow>
                        <TableCell>Cost Impact</TableCell>
                        <TableCell className="text-right">
                          ${recommendation.impact_preview_if_accept.cost_impact?.toFixed(2) || '0.00'}
                        </TableCell>
                        {isModified && recommendation.impact_preview_if_override && (
                          <TableCell className="text-right">
                            ${recommendation.impact_preview_if_override.cost_impact?.toFixed(2) || '0.00'}
                          </TableCell>
                        )}
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </div>
            )}
          </div>

          {/* Alternative Scenarios (Collapsible) */}
          {recommendation.alternative_scenarios && recommendation.alternative_scenarios.length > 0 && (
            <div>
              <button
                className="flex justify-between items-center w-full py-2 hover:bg-muted/50 rounded-md px-2 transition-colors"
                onClick={() => setShowAlternatives(!showAlternatives)}
              >
                <div className="flex items-center gap-2">
                  <AlternativeIcon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">
                    Alternative Scenarios ({recommendation.alternative_scenarios.length})
                  </span>
                </div>
                {showAlternatives ? (
                  <ExpandLessIcon className="h-4 w-4" />
                ) : (
                  <ExpandMoreIcon className="h-4 w-4" />
                )}
              </button>

              {showAlternatives && (
                <div className="mt-3 space-y-2">
                  {recommendation.alternative_scenarios.map((alt, idx) => (
                    <div
                      key={idx}
                      className="p-3 border rounded-lg bg-card flex justify-between items-center"
                    >
                      <div>
                        <p className="font-semibold">{alt.quantity} units</p>
                        <p className="text-sm text-muted-foreground">{alt.description}</p>
                        <p className="text-xs text-muted-foreground">Risk: {alt.risk}</p>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onModify(alt.quantity)}
                        disabled={disabled}
                      >
                        Use This
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Historical Performance (Collapsible) */}
          {recommendation.historical_performance && (
            <div>
              <button
                className="flex justify-between items-center w-full py-2 hover:bg-muted/50 rounded-md px-2 transition-colors"
                onClick={() => setShowHistoricalPerf(!showHistoricalPerf)}
              >
                <div className="flex items-center gap-2">
                  <HistoryIcon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Agent Performance History</span>
                </div>
                {showHistoricalPerf ? (
                  <ExpandLessIcon className="h-4 w-4" />
                ) : (
                  <ExpandMoreIcon className="h-4 w-4" />
                )}
              </button>

              {showHistoricalPerf && (
                <div className="mt-3 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Average Accuracy</span>
                    <span className="font-medium">
                      {formatPct(recommendation.historical_performance.avg_accuracy)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Recent Decisions</span>
                    <span className="font-medium">
                      {recommendation.historical_performance.recent_decisions}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Human Overrides</span>
                    <span className="font-medium">
                      {recommendation.historical_performance.overrides}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Override Regret Rate</span>
                    <span
                      className={cn(
                        'font-medium',
                        recommendation.historical_performance.override_regret_rate > 0.3 && 'text-amber-600'
                      )}
                      title="Percentage of times human override performed worse than agent"
                    >
                      {formatPct(recommendation.historical_performance.override_regret_rate)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Timestamp */}
          {recommendation.timestamp && (
            <p className="text-xs text-muted-foreground text-right">
              Generated: {new Date(recommendation.timestamp).toLocaleTimeString()}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default AgentRecommendationPanel;
