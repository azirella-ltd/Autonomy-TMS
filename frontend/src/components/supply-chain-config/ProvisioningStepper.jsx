/**
 * ProvisioningStepper — Rich visual provisioning dialog.
 *
 * Shows a hierarchical provisioning pipeline organized by agent tier,
 * with animated progress tracking, elapsed times, dependency flow,
 * and detailed status feedback for each of the 13 warm-start steps.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
  ChevronRight,
  ChevronDown,
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
  Clock,
  ArrowDown,
  Info,
} from 'lucide-react';
import { Badge, Button, Modal, Spinner } from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

// ─── Step metadata ───────────────────────────────────────────────────────────

const STEP_META = {
  warm_start: {
    label: 'Historical Demand Simulation',
    desc: 'Generate 52 weeks of historical demand data to initialize planning agents',
    detail: 'Creates belief states, demand distributions, and baseline metrics from simulated history',
    estimate: '10–30s',
  },
  sop_graphsage: {
    label: 'Strategic Network Planning Agent',
    desc: 'Train the S&OP GraphSAGE model for network-wide policy parameters',
    detail: 'Graph neural network learns supply chain topology: criticality, concentration risk, bottlenecks',
    estimate: '15–45s',
  },
  cfa_optimization: {
    label: 'Policy Parameter Optimization',
    desc: 'Optimize cost function policy parameters using differential evolution',
    detail: 'Searches for optimal (service_level, days_of_coverage) via Monte Carlo cost simulation',
    estimate: '20–60s',
  },
  lgbm_forecast: {
    label: 'Demand Forecasting',
    desc: 'Generate P10/P50/P90 baseline demand forecasts',
    detail: 'LightGBM quantile models with event tagging and censored demand handling',
    estimate: '15–45s',
  },
  demand_tgnn: {
    label: 'Demand Planning Agent',
    desc: 'Initialize the demand planning agent with network-aware demand sensing',
    detail: 'Temporal GNN processes demand signals across multi-echelon network',
    estimate: '10–30s',
  },
  supply_tgnn: {
    label: 'Supply Planning Agent',
    desc: 'Initialize supply planning agents for MPS/MRP material requirements',
    detail: 'Multi-site supply planning with BOM explosion and sourcing rules',
    estimate: '10–30s',
  },
  inventory_tgnn: {
    label: 'Inventory Optimization Agent',
    desc: 'Initialize the inventory optimization agent for buffer and rebalancing',
    detail: 'Learns optimal safety stock, reorder points, and cross-site rebalancing',
    estimate: '10–30s',
  },
  trm_training: {
    label: 'Execution Role Agent Training',
    desc: 'Train all 11 execution role agents from historical expert patterns',
    detail: 'Phase 1 behavioral cloning: ATP, PO, MO, TO, rebalancing, quality, maintenance, forecast adj, buffer, subcontracting, order tracking',
    estimate: '30–90s',
  },
  supply_plan: {
    label: 'Supply Plan Generation',
    desc: 'Generate initial supply plan from trained agents and planning parameters',
    detail: 'Creates purchase orders, transfer orders, and manufacturing orders with Monte Carlo evaluation',
    estimate: '15–60s',
  },
  rccp_validation: {
    label: 'Rough-Cut Capacity Validation',
    desc: 'Validate supply plan feasibility against available resource capacity',
    detail: 'RCCP checks each site for overloaded resources, recommends MPS levelling or overtime if needed',
    estimate: '10–30s',
  },
  decision_seed: {
    label: 'Decision Stream Seeding',
    desc: 'Seed the decision stream with initial decisions from execution role agents',
    detail: 'Runs one TRM decision cycle per site, populating the powell_*_decisions tables',
    estimate: '10–30s',
  },
  site_tgnn: {
    label: 'Operational Site Agent Training',
    desc: 'Train per-site coordination agents for cross-role trade-off learning',
    detail: 'GATv2+GRU site-level model learns dependencies between 11 TRM types',
    estimate: '15–45s',
  },
  conformal: {
    label: 'Uncertainty Calibration',
    desc: 'Calibrate conformal prediction bounds from historical data',
    detail: 'Distribution-free coverage guarantees for demand, lead time, and service level forecasts',
    estimate: '5–15s',
  },
  briefing: {
    label: 'Executive Briefing',
    desc: 'Generate executive strategy briefing from provisioned network',
    detail: 'LLM-synthesized briefing with KPI scorecards and agent readiness assessment',
    estimate: '10–30s',
  },
};

// ─── Tier groupings ──────────────────────────────────────────────────────────

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
    label: 'Strategic Planning',
    description: 'Network-wide S&OP agent that sets policy parameters across the supply chain',
    Icon: Globe,
    steps: ['sop_graphsage', 'cfa_optimization'],
    color: 'purple',
  },
  {
    key: 'tactical',
    label: 'Tactical Agents',
    description: 'Multi-site agents for demand, supply, and inventory optimization',
    Icon: Network,
    steps: ['demand_tgnn', 'supply_tgnn', 'inventory_tgnn'],
    color: 'violet',
  },
  {
    key: 'execution',
    label: 'Execution Agents',
    description: '11 site-level role agents: ATP, PO, MO, TO, quality, maintenance, and more',
    Icon: Users,
    steps: ['trm_training', 'decision_seed'],
    color: 'indigo',
  },
  {
    key: 'plans',
    label: 'Initial Plans',
    description: 'First supply plan from the trained agents and optimized parameters, then RCCP capacity validation',
    Icon: FileText,
    steps: ['supply_plan', 'rccp_validation'],
    color: 'cyan',
  },
  {
    key: 'site',
    label: 'Site Coordination',
    description: 'Per-site agents that learn cross-role trade-offs within each network site',
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
  blue:    { header: 'text-blue-600 dark:text-blue-400',     bg: 'bg-blue-500/8',     border: 'border-blue-200 dark:border-blue-800',     ring: 'ring-blue-500',     bar: 'bg-blue-500' },
  purple:  { header: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-500/8',   border: 'border-purple-200 dark:border-purple-800', ring: 'ring-purple-500', bar: 'bg-purple-500' },
  violet:  { header: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-500/8',   border: 'border-violet-200 dark:border-violet-800', ring: 'ring-violet-500', bar: 'bg-violet-500' },
  indigo:  { header: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-500/8',   border: 'border-indigo-200 dark:border-indigo-800', ring: 'ring-indigo-500', bar: 'bg-indigo-500' },
  cyan:    { header: 'text-cyan-600 dark:text-cyan-400',     bg: 'bg-cyan-500/8',     border: 'border-cyan-200 dark:border-cyan-800',     ring: 'ring-cyan-500',   bar: 'bg-cyan-500' },
  teal:    { header: 'text-teal-600 dark:text-teal-400',     bg: 'bg-teal-500/8',     border: 'border-teal-200 dark:border-teal-800',     ring: 'ring-teal-500',   bar: 'bg-teal-500' },
  emerald: { header: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500/8', border: 'border-emerald-200 dark:border-emerald-800', ring: 'ring-emerald-500', bar: 'bg-emerald-500' },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatElapsed(startISO, endISO) {
  if (!startISO) return null;
  const start = new Date(startISO);
  const end = endISO ? new Date(endISO) : new Date();
  const sec = Math.round((end - start) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  return `${min}m ${sec % 60}s`;
}

function formatTime(isoStr) {
  if (!isoStr) return null;
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ─── Circular progress ring ─────────────────────────────────────────────────

const ProgressRing = ({ completed, total, running }) => {
  const pct = total > 0 ? (completed / total) * 100 : 0;
  const r = 44;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;

  return (
    <div className="relative w-28 h-28 mx-auto">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
        {/* Background track */}
        <circle cx="50" cy="50" r={r} fill="none" stroke="currentColor"
          className="text-muted-foreground/10" strokeWidth="6" />
        {/* Progress arc */}
        <circle cx="50" cy="50" r={r} fill="none"
          className={completed === total ? 'text-emerald-500' : 'text-violet-500'}
          stroke="currentColor" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
        {/* Running pulse arc (subtle) */}
        {running > 0 && (
          <circle cx="50" cy="50" r={r} fill="none"
            className="text-violet-400 animate-pulse" stroke="currentColor"
            strokeWidth="2" strokeDasharray={`${circ * 0.08} ${circ * 0.92}`}
            strokeDashoffset={offset - circ * 0.04} strokeLinecap="round" opacity="0.5" />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn(
          'text-2xl font-bold tabular-nums',
          completed === total ? 'text-emerald-600 dark:text-emerald-400' : 'text-foreground',
        )}>
          {completed}
        </span>
        <span className="text-[10px] text-muted-foreground -mt-0.5">
          of {total} steps
        </span>
      </div>
    </div>
  );
};

// ─── Status summary badges ──────────────────────────────────────────────────

const StatusSummary = ({ steps }) => {
  const counts = useMemo(() => {
    const c = { completed: 0, running: 0, pending: 0, failed: 0 };
    steps.forEach(s => {
      if (s.status === 'completed') c.completed++;
      else if (s.status === 'running') c.running++;
      else if (s.status === 'failed') c.failed++;
      else c.pending++;
    });
    return c;
  }, [steps]);

  return (
    <div className="flex items-center justify-center gap-3 text-xs">
      {counts.completed > 0 && (
        <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" /> {counts.completed} done
        </span>
      )}
      {counts.running > 0 && (
        <span className="flex items-center gap-1 text-violet-600 dark:text-violet-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {counts.running} running
        </span>
      )}
      {counts.pending > 0 && (
        <span className="flex items-center gap-1 text-muted-foreground">
          <Clock className="h-3.5 w-3.5" /> {counts.pending} queued
        </span>
      )}
      {counts.failed > 0 && (
        <span className="flex items-center gap-1 text-red-500">
          <AlertCircle className="h-3.5 w-3.5" /> {counts.failed} failed
        </span>
      )}
    </div>
  );
};

// ─── Individual step row ─────────────────────────────────────────────────────

const StepRow = ({ step, stepKey, runningStep, runningAll, onRun, onReset, tierColor, configId }) => {
  const [expanded, setExpanded] = useState(false);
  const meta = STEP_META[stepKey] || {};
  const isRunning = runningStep === stepKey || (runningAll && step.status === 'running');
  const canRun = step.dependencies_met && step.status !== 'completed' && !isRunning && !runningAll && !runningStep;
  const colors = TIER_COLORS[tierColor];

  const statusIcon = (() => {
    if (isRunning || step.status === 'running') {
      return <Loader2 className="h-4 w-4 animate-spin text-violet-500" />;
    }
    if (step.status === 'completed') {
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    }
    if (step.status === 'failed') {
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
    if (!step.dependencies_met) {
      return <Lock className="h-4 w-4 text-muted-foreground/30" />;
    }
    return <Circle className="h-4 w-4 text-muted-foreground/30" />;
  })();

  const elapsedStr = step.completed_at ? formatTime(step.completed_at) : null;

  return (
    <div className={cn(
      'transition-colors',
      isRunning ? 'bg-violet-500/5' :
      step.status === 'completed' ? 'bg-emerald-500/3' :
      step.status === 'failed' ? 'bg-red-500/5' : '',
    )}>
      {/* Main row */}
      <div className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-accent/20"
        onClick={() => setExpanded(!expanded)}>
        {/* Status icon */}
        <div className="flex-shrink-0 w-5">{statusIcon}</div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn(
              'text-sm font-medium',
              step.status === 'completed' ? 'text-emerald-700 dark:text-emerald-400' :
              step.status === 'failed' ? 'text-red-600 dark:text-red-400' :
              !step.dependencies_met ? 'text-muted-foreground/50' :
              'text-foreground',
            )}>
              {meta.label || step.label}
            </span>
          </div>
          <p className={cn(
            'text-[11px] mt-0.5 leading-snug',
            step.status === 'completed' ? 'text-emerald-600/60 dark:text-emerald-400/60' :
            'text-muted-foreground',
          )}>
            {meta.desc}
          </p>
        </div>

        {/* Right side: time + actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Elapsed / completion time */}
          {elapsedStr && (
            <span className="text-[10px] text-muted-foreground tabular-nums whitespace-nowrap">
              {elapsedStr}
            </span>
          )}
          {isRunning && (
            <span className="text-[10px] text-violet-500 tabular-nums whitespace-nowrap animate-pulse">
              running...
            </span>
          )}
          {!isRunning && step.status === 'pending' && step.dependencies_met && (
            <span className="text-[10px] text-muted-foreground/50 whitespace-nowrap">
              ~{meta.estimate}
            </span>
          )}

          {/* Action buttons */}
          {step.status === 'failed' && (
            <button onClick={(e) => { e.stopPropagation(); onReset(stepKey); }}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
              title="Reset and retry">
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
          {canRun && (
            <button onClick={(e) => { e.stopPropagation(); onRun(stepKey); }}
              className="p-1.5 rounded-md bg-violet-500/10 hover:bg-violet-500/20 text-violet-600 dark:text-violet-400"
              title="Run this step">
              <Play className="h-3.5 w-3.5" />
            </button>
          )}

          {/* Expand chevron */}
          <ChevronDown className={cn(
            'h-3.5 w-3.5 text-muted-foreground/40 transition-transform',
            expanded && 'rotate-180',
          )} />
        </div>
      </div>

      {/* Expanded detail panel */}
      {expanded && (
        <div className="px-3 pb-3 pl-11">
          <div className="rounded-md bg-muted/30 border border-border/50 p-2.5 space-y-1.5">
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              {meta.detail}
            </p>
            {step.error && (
              <div className="flex items-start gap-1.5 text-[11px] text-red-500 bg-red-500/5 rounded px-2 py-1.5">
                <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                <span className="break-all">{step.error}</span>
              </div>
            )}
            {!step.dependencies_met && step.depends_on?.length > 0 && (
              <div className="flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400">
                <Lock className="h-3 w-3 flex-shrink-0" />
                <span>Blocked by: {step.depends_on.map(d => STEP_META[d]?.label || d).join(', ')}</span>
              </div>
            )}
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
              <span>Step: <code className="bg-muted px-1 rounded text-[10px]">{stepKey}</code></span>
              {step.completed_at && <span>Completed: {new Date(step.completed_at).toLocaleString()}</span>}
              {!step.completed_at && meta.estimate && <span>Estimated: {meta.estimate}</span>}
            </div>
            {stepKey === 'conformal' && step.status === 'completed' && configId && (
              <CDTReadinessPanel configId={configId} />
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Tier section ────────────────────────────────────────────────────────────

const TierSection = ({ tier, stepMap, runningStep, runningAll, onRun, onReset, configId }) => {
  const colors = TIER_COLORS[tier.color];
  const TierIcon = tier.Icon;
  const tierSteps = tier.steps.map(k => stepMap[k]).filter(Boolean);
  const completedCount = tierSteps.filter(s => s.status === 'completed').length;
  const totalCount = tierSteps.length;
  const hasRunning = tierSteps.some(s => s.status === 'running');
  const hasFailed = tierSteps.some(s => s.status === 'failed');
  const allDone = completedCount === totalCount;

  return (
    <div className={cn('rounded-lg border overflow-hidden transition-all', colors.border)}>
      {/* Tier header with progress bar */}
      <div className={cn('relative', colors.bg)}>
        {/* Inline progress bar at bottom of header */}
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-muted-foreground/5">
          <div className={cn('h-full transition-all duration-500', colors.bar)}
            style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%`, opacity: allDone ? 0.6 : 0.8 }} />
        </div>

        <div className="flex items-center gap-3 px-3 py-2.5">
          <div className={cn('flex-shrink-0 p-1.5 rounded-md', allDone ? 'bg-emerald-500/10' : 'bg-white/30 dark:bg-white/5')}>
            <TierIcon className={cn('h-4 w-4', allDone ? 'text-emerald-500' : colors.header)} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={cn('text-sm font-semibold', allDone ? 'text-emerald-700 dark:text-emerald-400' : colors.header)}>
                {tier.label}
              </span>
              <span className="text-[10px] text-muted-foreground tabular-nums">
                {completedCount}/{totalCount}
              </span>
              {allDone && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />}
              {hasFailed && <AlertCircle className="h-3.5 w-3.5 text-red-500" />}
              {hasRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{tier.description}</p>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="divide-y divide-border/30">
        {tier.steps.map(stepKey => {
          const step = stepMap[stepKey];
          if (!step) return null;
          return (
            <StepRow key={stepKey} step={step} stepKey={stepKey}
              runningStep={runningStep} runningAll={runningAll}
              onRun={onRun} onReset={onReset} tierColor={tier.color}
              configId={configId} />
          );
        })}
      </div>
    </div>
  );
};

// ─── CDT readiness indicator (conformal decision theory) ─────────────────────

const CDTReadinessPanel = ({ configId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!configId) return;
    setLoading(true);
    api.get('/conformal-prediction/cdt/readiness')
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [configId]);

  if (loading) return <div className="text-[10px] text-muted-foreground">Loading CDT status...</div>;
  if (!data) return null;

  const { summary, message } = data;
  const allCalibrated = summary.calibrated === summary.total;
  const hasPartial = summary.partial > 0;

  return (
    <div className={cn(
      'rounded-md border p-2.5 space-y-2 text-[11px]',
      allCalibrated
        ? 'bg-emerald-500/5 border-emerald-500/20'
        : 'bg-amber-500/5 border-amber-500/20',
    )}>
      <div className="flex items-center gap-2">
        {allCalibrated ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
        ) : (
          <Info className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
        )}
        <span className={allCalibrated ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-amber-700 dark:text-amber-400 font-medium'}>
          CDT Coverage: {summary.calibrated}/{summary.total} TRM agents
        </span>
      </div>
      <p className="text-muted-foreground leading-relaxed pl-5">{message}</p>
      {!allCalibrated && (
        <div className="flex flex-wrap gap-1.5 pl-5">
          {data.trm_types?.filter(t => t.status !== 'calibrated').map(t => (
            <span key={t.trm_type} className={cn(
              'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]',
              t.status === 'partial'
                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
                : 'bg-muted text-muted-foreground',
            )}>
              {t.label}: {t.calibration_pairs}/{t.min_required}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Flow connector between tiers ────────────────────────────────────────────

const TierConnector = ({ fromDone, toDone }) => (
  <div className="flex justify-center py-0.5">
    <div className={cn(
      'w-0.5 h-3 rounded-full transition-colors duration-300',
      fromDone && toDone ? 'bg-emerald-400/40' :
      fromDone ? 'bg-violet-400/40' :
      'bg-muted-foreground/10',
    )} />
  </div>
);

// ─── Main component ──────────────────────────────────────────────────────────

const ProvisioningStepper = ({ configId, configName, isOpen, onClose }) => {
  const [provisioningStatus, setProvisioningStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningStep, setRunningStep] = useState(null);
  const [runningAll, setRunningAll] = useState(false);
  const [startedAt, setStartedAt] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef(null);

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

  // Poll while any steps are running
  const hasRunningSteps = useMemo(() => {
    if (!provisioningStatus?.steps) return false;
    return provisioningStatus.steps.some(s => s.status === 'running');
  }, [provisioningStatus]);

  useEffect(() => {
    if (!isOpen) return;
    // Poll if user triggered run OR if backend has running steps
    if (!runningStep && !runningAll && !hasRunningSteps) return;
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [isOpen, runningStep, runningAll, hasRunningSteps, fetchStatus]);

  // Elapsed timer when running
  useEffect(() => {
    if (runningAll || hasRunningSteps) {
      if (!startedAt) setStartedAt(Date.now());
      timerRef.current = setInterval(() => setElapsed(Date.now()), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      if (!runningAll && !hasRunningSteps) setStartedAt(null);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [runningAll, hasRunningSteps]);

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
    setStartedAt(Date.now());
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
  const completedCount = steps.filter(s => s.status === 'completed').length;
  const runningCount = steps.filter(s => s.status === 'running').length;
  const failedCount = steps.filter(s => s.status === 'failed').length;
  const stepMap = Object.fromEntries(steps.map(s => [s.key, s]));
  const isActive = runningAll || runningStep || hasRunningSteps;

  const elapsedDisplay = startedAt ? formatElapsed(new Date(startedAt).toISOString()) : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <div className={cn(
            'p-1 rounded-md',
            overallStatus === 'completed' ? 'bg-emerald-500/10' : 'bg-violet-500/10',
          )}>
            <Zap className={cn('h-5 w-5', overallStatus === 'completed' ? 'text-emerald-500' : 'text-violet-500')} />
          </div>
          <div>
            <span className="text-base">Provision: {configName}</span>
            {isActive && elapsedDisplay && (
              <span className="text-xs text-muted-foreground ml-2 tabular-nums">{elapsedDisplay} elapsed</span>
            )}
          </div>
        </div>
      }
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <StatusSummary steps={steps} />
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            <Button
              onClick={handleRunAll}
              disabled={isActive || overallStatus === 'completed'}
              leftIcon={
                runningAll
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : overallStatus === 'completed'
                    ? <CheckCircle2 className="h-4 w-4" />
                    : <Play className="h-4 w-4" />
              }
              className={overallStatus === 'completed' ? 'bg-emerald-600 hover:bg-emerald-700' : ''}
            >
              {runningAll ? 'Provisioning...' : overallStatus === 'completed' ? 'Complete' : 'Run All Steps'}
            </Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Spinner size="lg" />
          <span className="text-sm text-muted-foreground">Loading provisioning status...</span>
        </div>
      ) : (
        <div className="space-y-1">
          {/* Progress ring + summary header */}
          <div className="flex items-center gap-6 py-3">
            <ProgressRing completed={completedCount} total={steps.length} running={runningCount} />
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    overallStatus === 'completed' ? 'success' :
                    overallStatus === 'in_progress' ? 'info' :
                    overallStatus === 'partial' ? 'warning' :
                    'secondary'
                  }
                  className="text-xs"
                >
                  {overallStatus === 'not_started' ? 'Ready to start' :
                   overallStatus === 'in_progress' ? 'In progress' :
                   overallStatus === 'completed' ? 'All agents provisioned' :
                   overallStatus.replace(/_/g, ' ')}
                </Badge>
              </div>
              {/* Phase summary */}
              <div className="grid grid-cols-7 gap-1">
                {TIERS.map(tier => {
                  const tierSteps = tier.steps.map(k => stepMap[k]).filter(Boolean);
                  const done = tierSteps.filter(s => s.status === 'completed').length;
                  const total = tierSteps.length;
                  const allDone = done === total;
                  const hasRun = tierSteps.some(s => s.status === 'running');
                  const hasFail = tierSteps.some(s => s.status === 'failed');
                  const colors = TIER_COLORS[tier.color];
                  return (
                    <div key={tier.key} className="flex flex-col items-center gap-1">
                      <div className={cn(
                        'w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold',
                        allDone ? 'bg-emerald-500 text-white' :
                        hasFail ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400' :
                        hasRun ? 'bg-violet-100 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400 animate-pulse' :
                        done > 0 ? 'bg-muted text-muted-foreground' :
                        'bg-muted/50 text-muted-foreground/40',
                      )}>
                        {allDone ? <CheckCircle2 className="h-3.5 w-3.5" /> :
                         hasRun ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                         `${done}/${total}`}
                      </div>
                      <span className={cn(
                        'text-[9px] text-center leading-tight max-w-[60px]',
                        allDone ? 'text-emerald-600 dark:text-emerald-400 font-medium' :
                        'text-muted-foreground',
                      )}>
                        {tier.label.split(' ')[0]}
                      </span>
                    </div>
                  );
                })}
              </div>
              {/* Overall progress bar */}
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div className={cn(
                  'h-full rounded-full transition-all duration-700 ease-out',
                  overallStatus === 'completed' ? 'bg-emerald-500' :
                  failedCount > 0 ? 'bg-gradient-to-r from-violet-500 to-red-400' :
                  'bg-gradient-to-r from-violet-500 to-violet-400',
                )}
                  style={{ width: `${steps.length > 0 ? (completedCount / steps.length) * 100 : 0}%` }} />
              </div>
            </div>
          </div>

          {/* Tier stack with connectors */}
          <div>
            {TIERS.map((tier, idx) => {
              const prevTier = idx > 0 ? TIERS[idx - 1] : null;
              const prevDone = prevTier
                ? prevTier.steps.map(k => stepMap[k]).filter(Boolean).every(s => s.status === 'completed')
                : true;
              const thisDone = tier.steps.map(k => stepMap[k]).filter(Boolean).every(s => s.status === 'completed');

              return (
                <div key={tier.key}>
                  {idx > 0 && <TierConnector fromDone={prevDone} toDone={thisDone} />}
                  <TierSection tier={tier} stepMap={stepMap}
                    runningStep={runningStep} runningAll={runningAll}
                    onRun={handleRunStep} onReset={handleResetStep}
                    configId={configId} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
};

export default ProvisioningStepper;
