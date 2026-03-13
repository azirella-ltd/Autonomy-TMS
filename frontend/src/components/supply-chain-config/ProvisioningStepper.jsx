/**
 * ProvisioningStepper — Agent provisioning dialog.
 *
 * Shows a hierarchical provisioning pipeline organized by agent tier,
 * from data foundation through strategic, tactical, operational, and
 * execution-level agents. Steps have dependency tracking and can be
 * run individually or all at once.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
  ChevronRight,
  Play,
  RotateCcw,
  Zap,
  Lock,
  Database,
  Globe,
  Network,
  Building2,
  Users,
  BarChart3,
  FileText,
} from 'lucide-react';
import { Badge, Button, Modal, Spinner } from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

// Human-readable descriptions for each step (no technology names)
const STEP_DESCRIPTIONS = {
  warm_start: 'Generate 52 weeks of historical demand data to initialize planning agents',
  sop_graphsage: 'Train the strategic network planning agent for S&OP policy parameters',
  cfa_optimization: 'Optimize cost function policy parameters using historical scenarios',
  lgbm_forecast: 'Generate P10/P50/P90 baseline demand forecasts using gradient boosting models',
  demand_tgnn: 'Initialize the demand planning agent with network-aware demand sensing',
  supply_tgnn: 'Initialize supply and RCCP agents for MPS/MRP, sourcing, and capacity feasibility',
  inventory_tgnn: 'Initialize the inventory optimization agent for buffer and rebalancing decisions',
  trm_training: 'Train all execution role agents across 11 decision types from historical expert patterns',
  supply_plan: 'Generate initial supply plan (purchase orders, transfer orders, manufacturing orders)',
  decision_seed: 'Seed the decision stream with initial decisions from execution role agents',
  site_tgnn: 'Train operational site coordination agents for cross-role trade-off learning',
  conformal: 'Calibrate uncertainty bounds from historical data for reliable confidence estimates',
  briefing: 'Generate executive strategy briefing from provisioned network and agent data',
};

// Tier groupings define the hierarchical stack displayed in the UI
const TIERS = [
  {
    key: 'foundation',
    label: 'Data Foundation',
    description: 'Historical data and statistical forecasts that initialize all planning agents',
    Icon: Database,
    steps: ['warm_start', 'lgbm_forecast'],
    color: 'blue',
  },
  {
    key: 'strategic',
    label: 'Strategic Planning Agent',
    description: 'Network-wide S&OP agent that sets policy parameters across the supply chain',
    Icon: Globe,
    steps: ['sop_graphsage', 'cfa_optimization'],
    color: 'purple',
  },
  {
    key: 'tactical',
    label: 'Network Tactical Agents',
    description: 'Multi-site agents for demand planning, supply planning, RCCP capacity validation, and inventory optimization',
    Icon: Network,
    steps: ['demand_tgnn', 'supply_tgnn', 'inventory_tgnn'],
    color: 'violet',
  },
  {
    key: 'execution',
    label: 'Execution Role Agents',
    description: 'Site-level agents that execute individual decisions: ATP, purchase orders, manufacturing, transfers, and 7 other roles',
    Icon: Users,
    steps: ['trm_training', 'decision_seed'],
    color: 'indigo',
  },
  {
    key: 'plans',
    label: 'Initial Plans',
    description: 'First supply plan generated from the trained agents and planning parameters',
    Icon: FileText,
    steps: ['supply_plan'],
    color: 'cyan',
  },
  {
    key: 'site',
    label: 'Operational Site Agents',
    description: 'Per-site coordination agents that learn cross-role trade-offs within each site in the tenant network',
    Icon: Building2,
    steps: ['site_tgnn'],
    color: 'teal',
  },
  {
    key: 'calibration',
    label: 'Calibration & Reporting',
    description: 'Uncertainty calibration and executive briefing generation',
    Icon: BarChart3,
    steps: ['conformal', 'briefing'],
    color: 'emerald',
  },
];

const TIER_COLORS = {
  blue:   { header: 'text-blue-600 dark:text-blue-400',   bg: 'bg-blue-500/8',   border: 'border-blue-200 dark:border-blue-800' },
  purple: { header: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-500/8', border: 'border-purple-200 dark:border-purple-800' },
  violet: { header: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-500/8', border: 'border-violet-200 dark:border-violet-800' },
  indigo: { header: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-500/8', border: 'border-indigo-200 dark:border-indigo-800' },
  cyan:   { header: 'text-cyan-600 dark:text-cyan-400',   bg: 'bg-cyan-500/8',   border: 'border-cyan-200 dark:border-cyan-800' },
  teal:   { header: 'text-teal-600 dark:text-teal-400',   bg: 'bg-teal-500/8',   border: 'border-teal-200 dark:border-teal-800' },
  emerald:{ header: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500/8', border: 'border-emerald-200 dark:border-emerald-800' },
};

const ProvisioningStepper = ({ configId, configName, isOpen, onClose }) => {
  const [provisioningStatus, setProvisioningStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningStep, setRunningStep] = useState(null);
  const [runningAll, setRunningAll] = useState(false);

  const fetchStatus = useCallback(async () => {
    if (!configId) return;
    try {
      const response = await api.get(`/provisioning/status/${configId}`);
      setProvisioningStatus(response.data);
    } catch (err) {
      console.error('Failed to fetch provisioning status:', err);
    } finally {
      setLoading(false);
    }
  }, [configId]);

  useEffect(() => {
    if (isOpen && configId) {
      setLoading(true);
      fetchStatus();
    }
  }, [isOpen, configId, fetchStatus]);

  // Poll while steps are running
  useEffect(() => {
    if (!isOpen || (!runningStep && !runningAll)) return;
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [isOpen, runningStep, runningAll, fetchStatus]);

  const handleRunStep = async (stepKey) => {
    setRunningStep(stepKey);
    try {
      await api.post(`/provisioning/run/${configId}/${stepKey}`);
      await fetchStatus();
    } catch (err) {
      console.error(`Step ${stepKey} failed:`, err);
    } finally {
      setRunningStep(null);
    }
  };

  const handleRunAll = async () => {
    setRunningAll(true);
    try {
      await api.post(`/provisioning/run-all/${configId}`);
      await fetchStatus();
    } catch (err) {
      console.error('Run all failed:', err);
    } finally {
      setRunningAll(false);
    }
  };

  const handleResetStep = async (stepKey) => {
    try {
      await api.post(`/provisioning/reset/${configId}/${stepKey}`);
      await fetchStatus();
    } catch (err) {
      console.error(`Reset ${stepKey} failed:`, err);
    }
  };

  const steps = provisioningStatus?.steps || [];
  const overallStatus = provisioningStatus?.overall_status || 'not_started';
  const completedCount = steps.filter((s) => s.status === 'completed').length;

  // Build a lookup map from steps array
  const stepMap = Object.fromEntries(steps.map((s) => [s.key, s]));

  const getStepIcon = (step) => {
    if (!step) return <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />;
    if (runningStep === step.key || (runningAll && step.status === 'running')) {
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />;
    }
    if (step.status === 'completed') {
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
    }
    if (step.status === 'failed') {
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
    }
    if (step.status === 'running') {
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />;
    }
    if (!step.dependencies_met) {
      return <Lock className="h-3.5 w-3.5 text-muted-foreground/40" />;
    }
    return <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />;
  };

  // Derive tier status from its constituent steps
  const getTierStatus = (tier) => {
    const tierSteps = tier.steps.map((k) => stepMap[k]).filter(Boolean);
    if (tierSteps.length === 0) return 'not_started';
    if (tierSteps.every((s) => s.status === 'completed')) return 'completed';
    if (tierSteps.some((s) => s.status === 'failed')) return 'failed';
    if (tierSteps.some((s) => s.status === 'running')) return 'running';
    if (tierSteps.some((s) => s.status === 'completed')) return 'partial';
    return 'not_started';
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-violet-500" />
          <span>Provision: {configName}</span>
        </div>
      }
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="text-sm text-muted-foreground">
            {completedCount}/{steps.length} steps complete
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            <Button
              onClick={handleRunAll}
              disabled={runningAll || runningStep || overallStatus === 'completed'}
              leftIcon={runningAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            >
              {runningAll ? 'Running...' : overallStatus === 'completed' ? 'Complete' : 'Run All'}
            </Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="space-y-3">
          {/* Overall progress bar */}
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Agent Provisioning
              </span>
              <Badge
                variant={
                  overallStatus === 'completed' ? 'success' :
                  overallStatus === 'in_progress' ? 'info' :
                  overallStatus === 'partial' ? 'warning' :
                  'secondary'
                }
              >
                {overallStatus.replace(/_/g, ' ')}
              </Badge>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all duration-500',
                  overallStatus === 'completed' ? 'bg-emerald-500' : 'bg-violet-500',
                )}
                style={{ width: `${steps.length > 0 ? (completedCount / steps.length) * 100 : 0}%` }}
              />
            </div>
          </div>

          {/* Tier stack */}
          {TIERS.map((tier, tierIdx) => {
            const colors = TIER_COLORS[tier.color];
            const tierStatus = getTierStatus(tier);
            const TierIcon = tier.Icon;

            return (
              <div
                key={tier.key}
                className={cn(
                  'rounded-lg border overflow-hidden',
                  colors.border,
                )}
              >
                {/* Tier header */}
                <div className={cn('flex items-start gap-3 px-3 py-2.5', colors.bg)}>
                  <div className={cn('mt-0.5 flex-shrink-0', colors.header)}>
                    <TierIcon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn('text-sm font-semibold', colors.header)}>
                        {tier.label}
                      </span>
                      {tierStatus === 'completed' && (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                      )}
                      {tierStatus === 'failed' && (
                        <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                      )}
                      {(tierStatus === 'running') && (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500 flex-shrink-0" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 leading-snug">
                      {tier.description}
                    </p>
                  </div>
                </div>

                {/* Steps within tier */}
                <div className="divide-y divide-border/50">
                  {tier.steps.map((stepKey) => {
                    const step = stepMap[stepKey];
                    if (!step) return null;
                    const isRunning = runningStep === step.key || (runningAll && step.status === 'running');
                    const canRun = step.dependencies_met && step.status !== 'completed' && !isRunning && !runningAll && !runningStep;

                    return (
                      <div
                        key={step.key}
                        className={cn(
                          'flex items-center gap-3 px-3 py-2 transition-colors',
                          isRunning ? 'bg-violet-500/5' :
                          step.status === 'completed' ? 'bg-emerald-500/5' :
                          step.status === 'failed' ? 'bg-red-500/5' :
                          'hover:bg-accent/30',
                        )}
                      >
                        {/* Status icon */}
                        <div className="flex-shrink-0 w-4">
                          {getStepIcon(step)}
                        </div>

                        {/* Step details */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={cn(
                              'text-xs font-medium',
                              step.status === 'completed' ? 'text-emerald-700 dark:text-emerald-400' :
                              !step.dependencies_met ? 'text-muted-foreground/60' :
                              'text-foreground',
                            )}>
                              {step.label}
                            </span>
                            {step.completed_at && (
                              <span className="text-[10px] text-muted-foreground">
                                {new Date(step.completed_at).toLocaleTimeString()}
                              </span>
                            )}
                          </div>
                          {(step.error || (!step.dependencies_met && step.depends_on?.length > 0)) && (
                            <p className={cn(
                              'text-[10px] mt-0.5',
                              step.error ? 'text-red-500' : 'text-amber-600',
                            )}>
                              {step.error || `Requires: ${step.depends_on.join(', ')}`}
                            </p>
                          )}
                          {!step.error && step.dependencies_met && step.status !== 'completed' && (
                            <p className="text-[10px] text-muted-foreground mt-0.5">
                              {STEP_DESCRIPTIONS[step.key] || ''}
                            </p>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {step.status === 'failed' && (
                            <button
                              onClick={() => handleResetStep(step.key)}
                              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                              title="Reset and retry"
                            >
                              <RotateCcw className="h-3 w-3" />
                            </button>
                          )}
                          {canRun && (
                            <button
                              onClick={() => handleRunStep(step.key)}
                              className="p-1 rounded hover:bg-accent text-violet-500 hover:text-violet-600"
                              title="Run this step"
                            >
                              <ChevronRight className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
};

export default ProvisioningStepper;
