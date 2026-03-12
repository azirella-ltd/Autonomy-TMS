/**
 * ProvisioningStepper — Powell Cascade provisioning dialog.
 *
 * Shows a 13-step provisioning checklist with dependency tracking,
 * real-time status updates, and the ability to run individual steps
 * or the full pipeline.
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
} from 'lucide-react';
import { Badge, Button, Modal, Spinner } from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const STEP_ICONS = {
  warm_start: '1',
  sop_graphsage: '2',
  cfa_optimization: '3',
  lgbm_forecast: '4',
  demand_tgnn: '5',
  supply_tgnn: '6',
  inventory_tgnn: '7',
  trm_training: '8',
  supply_plan: '9',
  decision_seed: '10',
  site_tgnn: '11',
  conformal: '12',
  briefing: '13',
};

const STEP_DESCRIPTIONS = {
  warm_start: 'Generate 52 weeks of historical demand data from forecast distributions',
  sop_graphsage: 'Train network-wide S&OP planning model for policy parameters',
  cfa_optimization: 'Optimize CFA policy parameters via Differential Evolution',
  lgbm_forecast: 'Train LightGBM quantile models and generate P10/P50/P90 baseline demand forecasts',
  demand_tgnn: 'Initialize Demand Planning Agent with network-aware demand sensing',
  supply_tgnn: 'Initialize Supply Planning Agent for MPS/MRP/sourcing decisions',
  inventory_tgnn: 'Initialize Inventory Optimization Agent for buffer and rebalancing decisions',
  trm_training: 'Phase 1 Behavioral Cloning for all 11 AI agents',
  supply_plan: 'Generate initial supply plan (PO/TO/MO requests)',
  decision_seed: 'Seed decision stream with synthetic AI decisions',
  site_tgnn: 'Train Site Agent (Layer 1.5) for cross-site coordination',
  conformal: 'Calibrate conformal prediction intervals from historical data',
  briefing: 'Generate executive strategy briefing from provisioned data',
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

  const getStepIcon = (step) => {
    if (runningStep === step.key || (runningAll && step.status === 'running')) {
      return <Loader2 className="h-4 w-4 animate-spin text-violet-500" />;
    }
    if (step.status === 'completed') {
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    }
    if (step.status === 'failed') {
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
    if (step.status === 'running') {
      return <Loader2 className="h-4 w-4 animate-spin text-violet-500" />;
    }
    if (!step.dependencies_met) {
      return <Lock className="h-4 w-4 text-muted-foreground/50" />;
    }
    return <Circle className="h-4 w-4 text-muted-foreground/40" />;
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
        <div className="space-y-1">
          {/* Overall status bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Powell Cascade Provisioning
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

          {/* Step list */}
          {steps.map((step, idx) => {
            const isRunning = runningStep === step.key || (runningAll && step.status === 'running');
            const canRun = step.dependencies_met && step.status !== 'completed' && !isRunning && !runningAll;

            return (
              <div
                key={step.key}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors',
                  isRunning ? 'bg-violet-500/5 border border-violet-500/20' :
                  step.status === 'completed' ? 'bg-emerald-500/5' :
                  step.status === 'failed' ? 'bg-red-500/5 border border-red-500/20' :
                  'hover:bg-accent/50',
                )}
              >
                {/* Step number + icon */}
                <div className="flex items-center gap-2 flex-shrink-0 w-6">
                  {getStepIcon(step)}
                </div>

                {/* Step details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'text-sm font-medium',
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
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {step.error || STEP_DESCRIPTIONS[step.key] || ''}
                  </p>
                  {!step.dependencies_met && step.depends_on?.length > 0 && (
                    <p className="text-[10px] text-amber-600 mt-0.5">
                      Requires: {step.depends_on.join(', ')}
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
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {canRun && !runningStep && (
                    <button
                      onClick={() => handleRunStep(step.key)}
                      className="p-1 rounded hover:bg-accent text-violet-500 hover:text-violet-600"
                      title="Run this step"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  )}
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
