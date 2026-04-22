/**
 * Recommended Actions Dashboard
 *
 * AWS Supply Chain-inspired dashboard showing:
 * - Inventory risk overview with projected inventory timelines
 * - Resolution recommendations ranked by score (risk resolved %, cost, impact)
 * - Before/After comparison for each recommendation
 * - Accept/override workflow
 *
 * Respects agent mode: Empty when fully manual, populated when copilot/autonomous
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  TrendingDown,
  TrendingUp,
  Truck,
  Package,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Brain,
  Info,
  Settings,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

// Inventory projection bar colors (matches AWS Supply Chain)
const getInventoryBarColor = (level, target, min) => {
  if (level <= min) return 'bg-red-500';
  if (level <= min * 1.5) return 'bg-orange-500';
  if (level <= target * 0.8) return 'bg-yellow-500';
  return 'bg-green-500';
};

// Score badge variant based on score value
const getScoreBadgeVariant = (score) => {
  if (score >= 90) return 'success';
  if (score >= 75) return 'default';
  if (score >= 60) return 'warning';
  return 'destructive';
};

/**
 * Inventory Timeline Bar - Shows projected inventory levels
 */
const InventoryTimelineBar = ({ projections, target, min, maxValue }) => {
  const barWidth = 100 / projections.length;

  return (
    <TooltipProvider>
      <div className="flex gap-0.5 h-8 items-end">
        {projections.map((level, idx) => {
          const height = Math.max((level / maxValue) * 100, 5);
          const colorClass = getInventoryBarColor(level, target, min);
          return (
            <Tooltip key={idx}>
              <TooltipTrigger asChild>
                <div
                  className={`${colorClass} rounded-sm min-h-1 transition-all hover:opacity-80 hover:scale-y-110`}
                  style={{ width: `${barWidth}%`, height: `${height}%` }}
                />
              </TooltipTrigger>
              <TooltipContent>Period {idx + 1}: {level} units</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
};

/**
 * Inventory Risk Summary Card - Shows a single site's risk status
 */
const InventoryRiskSummaryCard = ({ risk }) => {
  const statusVariants = {
    critical: 'destructive',
    warning: 'warning',
    healthy: 'success',
  };

  const statusColors = {
    critical: 'border-l-red-500',
    warning: 'border-l-amber-500',
    healthy: 'border-l-green-500',
  };

  return (
    <Card className={`border-l-4 ${statusColors[risk.status]}`}>
      <CardContent className="py-4">
        <div className="space-y-3">
          {/* Header */}
          <div className="flex justify-between items-start">
            <div>
              <p className="font-semibold">{risk.location_name}</p>
              <p className="text-sm text-muted-foreground">{risk.product_name}</p>
            </div>
            <Badge variant={statusVariants[risk.status]} className="capitalize">
              {risk.status}
            </Badge>
          </div>

          {/* Summary Message */}
          <Alert variant={risk.status === 'critical' ? 'destructive' : risk.status === 'warning' ? 'warning' : 'default'} className="py-2">
            <AlertDescription className="text-sm">{risk.summary_message}</AlertDescription>
          </Alert>

          {/* Key Metrics */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">On Hand</p>
              <p className="text-xl font-bold">{risk.current_inventory.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Min Qty</p>
              <p className="text-xl font-semibold">{risk.min_qty.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Days of Cover</p>
              <p className="text-xl font-semibold">{risk.days_of_supply}</p>
            </div>
          </div>

          {/* Projected Inventory Timeline */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Projected Inventory</p>
            <InventoryTimelineBar
              projections={risk.projected_inventory}
              target={risk.target_inventory}
              min={risk.min_qty}
              maxValue={Math.max(...risk.projected_inventory, risk.target_inventory)}
            />
            <div className="flex justify-between mt-1">
              <span className="text-xs text-muted-foreground">Today</span>
              <span className="text-xs text-muted-foreground">+{risk.projected_inventory.length} periods</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

/**
 * Resolution Recommendation Card - Shows a single recommendation with accept action
 */
const RecommendationCard = ({ recommendation, onAccept, isSelected }) => {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <Card className={`mb-4 border-l-4 ${isSelected ? 'border-l-primary bg-primary/5 opacity-90' : 'border-l-gray-300'}`}>
      <CardContent className="py-4">
        <div className="space-y-4">
          {/* Main Content Row */}
          <div className="flex justify-between items-start gap-4">
            {/* Left: Description */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Truck className="h-4 w-4 text-muted-foreground" />
                <p className="font-semibold">{recommendation.action_title}</p>
              </div>
              <p className="text-sm text-muted-foreground">{recommendation.description}</p>
              {recommendation.arrival_estimate && (
                <p className="text-xs text-muted-foreground mt-1">
                  Arrives in approximately {recommendation.arrival_estimate}
                </p>
              )}
            </div>

            {/* Right: Score Metrics */}
            <div className="flex items-center gap-6">
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Score</p>
                <Badge variant={getScoreBadgeVariant(recommendation.score)} className="font-bold min-w-12">
                  {recommendation.score}
                </Badge>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Risk Resolved</p>
                <p className="text-sm font-bold text-green-600">{recommendation.risk_resolved_pct}%</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Emissions</p>
                <p className="text-sm">{recommendation.emissions_kg}kg</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">Shipping Cost</p>
                <p className="text-sm">${recommendation.shipping_cost.toLocaleString()}</p>
              </div>
              <Button
                onClick={() => onAccept(recommendation)}
                disabled={isSelected}
                className="min-w-20"
              >
                {isSelected ? 'Selected' : 'Select'}
              </Button>
            </div>
          </div>

          {/* Expandable Details */}
          <div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowDetails(!showDetails)}
              className="gap-1"
            >
              {showDetails ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {showDetails ? 'Hide' : 'View'} Before/After Comparison
            </Button>

            {showDetails && (
              <div className="mt-4">
                <BeforeAfterComparison
                  beforeState={recommendation.before_state}
                  afterState={recommendation.after_state}
                />
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

/**
 * Before/After Comparison Table
 */
const BeforeAfterComparison = ({ beforeState, afterState }) => {
  const maxInventory = Math.max(
    ...beforeState.sites.map(s => s.available),
    ...afterState.sites.map(s => s.available)
  );

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <Button variant="outline" size="sm">Before Rebalance</Button>
        <Button size="sm">After Rebalance</Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Site</TableHead>
              <TableHead className="text-right">Available</TableHead>
              <TableHead className="text-right">Min Qty</TableHead>
              <TableHead className="text-right">Days of Cover</TableHead>
              <TableHead className="min-w-[200px]">Projected Inventory</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {afterState.sites.map((site, idx) => {
              const before = beforeState.sites[idx];
              const change = site.available - before.available;

              return (
                <TableRow key={site.name}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span>{site.name}</span>
                      {change !== 0 && (
                        <Badge
                          variant={change > 0 ? 'success' : 'destructive'}
                          className="text-xs h-5"
                        >
                          {change > 0 ? `+${change}` : change}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className={`text-right font-bold ${site.available <= site.min_qty ? 'text-red-500' : ''}`}>
                    {site.available.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">{site.min_qty.toLocaleString()}</TableCell>
                  <TableCell className="text-right">{site.days_of_cover}</TableCell>
                  <TableCell>
                    <InventoryTimelineBar
                      projections={site.projected}
                      target={site.target}
                      min={site.min_qty}
                      maxValue={maxInventory}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
};

/**
 * Main Dashboard Component
 */
const RecommendedActionsDashboard = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [agentMode, setAgentMode] = useState('copilot');
  const [inventoryRisks, setInventoryRisks] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [selectedRecommendation, setSelectedRecommendation] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch recommendations from API
  const fetchRecommendations = useCallback(async () => {
    try {
      setRefreshing(true);

      const response = await api.get('/recommendations/dashboard');
      setInventoryRisks(response.data.inventory_risks);
      setRecommendations(response.data.recommendations);
      setAgentMode(response.data.agent_mode);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch recommendations:', err);
      setError('Unable to load recommendations. Please try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  const handleAcceptRecommendation = async (recommendation) => {
    try {
      const response = await api.post(`/recommendations/${recommendation.id}/accept`, {});
      if (response.data.success) {
        setSelectedRecommendation(recommendation.id);
      }
    } catch (err) {
      console.error('Failed to accept recommendation:', err);
      setError('Failed to accept recommendation. Please try again.');
    }
  };

  // If manual mode, show empty state
  if (!loading && agentMode === 'manual') {
    return (
      <div className="container mx-auto py-8 px-4 max-w-7xl">
        <Card>
          <CardContent className="text-center py-16">
            <Settings className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-2xl font-semibold mb-2">Manual Mode Active</h2>
            <p className="text-muted-foreground max-w-md mx-auto">
              Recommended actions are not available in manual mode.
              All decisions are made directly by the user without AI assistance.
            </p>
            <p className="text-sm text-muted-foreground mt-4">
              Switch to Copilot or Autonomous mode to receive AI-powered recommendations.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold">Recommended Actions</h1>
            <p className="text-muted-foreground">
              AI-powered recommendations to resolve inventory risks and optimize your supply chain
            </p>
          </div>
          <div className="flex items-center gap-4">
            <Badge variant="outline" className="gap-1">
              <Brain className="h-3 w-3" />
              {agentMode.charAt(0).toUpperCase() + agentMode.slice(1)} Mode
            </Badge>
            <Button
              variant="outline"
              size="icon"
              onClick={fetchRecommendations}
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Main Content */}
        {!loading && !error && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Overview */}
            <div className="lg:col-span-1">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Overview
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Inventory risks requiring attention
                  </p>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {/* Summary Stats */}
                    <div className="flex gap-2">
                      <div className="flex-1 text-center p-2 bg-red-100 rounded">
                        <p className="text-2xl font-bold text-red-700">
                          {inventoryRisks.filter(r => r.status === 'critical').length}
                        </p>
                        <p className="text-xs text-red-700">Critical</p>
                      </div>
                      <div className="flex-1 text-center p-2 bg-amber-100 rounded">
                        <p className="text-2xl font-bold text-amber-700">
                          {inventoryRisks.filter(r => r.status === 'warning').length}
                        </p>
                        <p className="text-xs text-amber-700">Warning</p>
                      </div>
                      <div className="flex-1 text-center p-2 bg-green-100 rounded">
                        <p className="text-2xl font-bold text-green-700">
                          {inventoryRisks.filter(r => r.status === 'healthy').length}
                        </p>
                        <p className="text-xs text-green-700">Healthy</p>
                      </div>
                    </div>

                    <hr />

                    {/* Risk Cards */}
                    {inventoryRisks.length === 0 ? (
                      <Alert>
                        <CheckCircle className="h-4 w-4" />
                        <AlertTitle>All Clear</AlertTitle>
                        <AlertDescription>
                          No inventory risks detected at this time.
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <div className="space-y-4">
                        {inventoryRisks.map((risk) => (
                          <InventoryRiskSummaryCard key={risk.id} risk={risk} />
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Column: Recommendations */}
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <Truck className="h-5 w-5" />
                        {recommendations.length > 0 && (
                          <span className="absolute -top-2 -right-2 h-4 w-4 text-xs bg-primary text-primary-foreground rounded-full flex items-center justify-center">
                            {recommendations.length}
                          </span>
                        )}
                      </div>
                      <CardTitle>Resolution Recommendations</CardTitle>
                    </div>
                    <Badge variant="outline">{recommendations.length} options</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Select an action to resolve the inventory risk
                  </p>
                </CardHeader>
                <CardContent>
                  {recommendations.length === 0 ? (
                    <Alert>
                      <Info className="h-4 w-4" />
                      <AlertTitle>No Recommendations</AlertTitle>
                      <AlertDescription>
                        There are no recommended actions at this time. Check back later or review your inventory levels.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <div>
                      {/* Column Headers */}
                      <div className="flex justify-end gap-6 px-4 py-2 bg-muted rounded mb-4">
                        <span className="text-xs text-muted-foreground w-14 text-center">Score</span>
                        <span className="text-xs text-muted-foreground w-20 text-center">Risk Resolved</span>
                        <span className="text-xs text-muted-foreground w-16 text-center">Emissions</span>
                        <span className="text-xs text-muted-foreground w-24 text-center">Shipping Cost</span>
                        <span className="w-20" />
                      </div>

                      {/* Recommendation Cards */}
                      {recommendations.map((rec) => (
                        <RecommendationCard
                          key={rec.id}
                          recommendation={rec}
                          onAccept={handleAcceptRecommendation}
                          isSelected={selectedRecommendation === rec.id}
                        />
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecommendedActionsDashboard;
