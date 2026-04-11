/**
 * ScenarioContextBar — Always-visible scenario indicator + tree popover
 *
 * Inspired by Kinaxis "Git for data" pattern:
 * - Current scenario always visible (like a git branch badge)
 * - Popover shows scenario tree with branch/switch/compare actions
 * - Quick "Create What-If" to branch from current scenario
 * - Commit/promote triggers AAP approval when cross-authority changes detected
 * - Scorecard comparison between parent and current scenario
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Modal,
  Popover,
  PopoverTrigger,
  PopoverContent,
  Spinner,
  Textarea,
  Alert,
  AlertDescription,
} from '../common';
import {
  GitBranch,
  GitCommit,
  Plus,
  ChevronDown,
  Check,
  Undo2,
  BarChart3,
  ArrowRight,
  Shield,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '@azirella-ltd/autonomy-frontend';


const SCENARIO_TYPE_STYLES = {
  BASELINE: { variant: 'default', label: 'Baseline', bg: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' },
  WORKING: { variant: 'warning', label: 'Working', bg: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' },
  SIMULATION: { variant: 'info', label: 'Simulation', bg: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' },
  ARCHIVED: { variant: 'secondary', label: 'Archived', bg: 'bg-gray-100 dark:bg-gray-800/30 text-gray-500 dark:text-gray-400' },
};

const STATUS_STYLES = {
  DRAFT: 'bg-gray-100 text-gray-600',
  EVALUATING: 'bg-yellow-100 text-yellow-700 animate-pulse',
  EVALUATED: 'bg-blue-100 text-blue-700',
  SHARED: 'bg-purple-100 text-purple-700',
  APPROVED: 'bg-green-100 text-green-700',
  PROMOTED: 'bg-emerald-100 text-emerald-700',
  PRUNED: 'bg-red-100 text-red-600 line-through',
  REJECTED: 'bg-red-100 text-red-700',
};

const SCORECARD_LABELS = {
  financial: { label: 'Financial', color: 'text-green-600' },
  customer: { label: 'Customer', color: 'text-blue-600' },
  operational: { label: 'Operational', color: 'text-amber-600' },
  strategic: { label: 'Strategic', color: 'text-purple-600' },
};

const fmtPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '-';
const fmtBenefit = (v) => v != null ? (v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2)) : '-';


// ─── Scorecard Mini Card ───────────────────────────────────────────────────
const ScorecardMini = ({ scorecard, label }) => {
  if (!scorecard) return null;
  return (
    <div className="space-y-1">
      {label && <p className="text-xs font-medium text-muted-foreground">{label}</p>}
      <div className="grid grid-cols-2 gap-1">
        {Object.entries(SCORECARD_LABELS).map(([key, cfg]) => (
          <div key={key} className="flex items-center justify-between text-xs px-2 py-1 rounded bg-muted/50">
            <span className={cfg.color}>{cfg.label}</span>
            <span className="font-mono">{fmtPct(scorecard[key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
};


// ─── Scenario Tree Node ────────────────────────────────────────────────────
const TreeNode = ({ scenario, isActive, depth, onSelect, onEvaluate, onCommit, onRollback }) => {
  const typeStyle = SCENARIO_TYPE_STYLES[scenario.scenario_type] || SCENARIO_TYPE_STYLES.BASELINE;
  const statusStyle = STATUS_STYLES[scenario.status] || STATUS_STYLES.DRAFT;

  return (
    <div
      className={cn(
        'flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer transition-colors text-sm',
        isActive ? 'bg-primary/10 border border-primary/30' : 'hover:bg-muted/50',
      )}
      style={{ marginLeft: depth * 16 }}
      onClick={() => onSelect(scenario)}
    >
      {depth > 0 && (
        <GitBranch className="h-3 w-3 text-muted-foreground flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className={cn('truncate font-medium', isActive && 'text-primary')}>
            {scenario.name}
          </span>
          <span className={cn('text-[10px] px-1.5 py-0 rounded-full', typeStyle.bg)}>
            {typeStyle.label}
          </span>
        </div>
        {scenario.status && scenario.status !== 'DRAFT' && (
          <span className={cn('text-[10px] px-1.5 py-0 rounded-full mt-0.5 inline-block', statusStyle)}>
            {scenario.status}
          </span>
        )}
      </div>
      {scenario.net_benefit != null && (
        <span className={cn(
          'text-xs font-mono flex-shrink-0',
          scenario.net_benefit >= 0 ? 'text-green-600' : 'text-red-600',
        )}>
          {fmtBenefit(scenario.net_benefit)}
        </span>
      )}
      {isActive && scenario.scenario_type === 'WORKING' && !scenario.committed_at && (
        <div className="flex items-center gap-0.5 flex-shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onCommit(scenario); }}
            className="p-1 hover:bg-primary/20 rounded"
            title="Commit to parent"
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onRollback(scenario); }}
            className="p-1 hover:bg-destructive/20 rounded text-destructive"
            title="Rollback changes"
          >
            <Undo2 className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
};


// ─── Main Component ────────────────────────────────────────────────────────
const ScenarioContextBar = () => {
  const {
    activeConfig,
    effectiveConfigId,
    workingBranch,
    branches,
    setWorkingBranch,
    clearWorkingBranch,
    createBranch,
    refresh,
  } = useActiveConfig();

  const configId = activeConfig?.id;
  const configName = activeConfig?.name;

  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);

  // Branch creation dialog
  const [branchDialogOpen, setBranchDialogOpen] = useState(false);
  const [branchName, setBranchName] = useState('');
  const [branchDescription, setBranchDescription] = useState('');
  const [branchType, setBranchType] = useState('WORKING');
  const [actionLoading, setActionLoading] = useState(false);

  // Scorecard comparison
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareData, setCompareData] = useState(null);

  // Commit approval state
  const [commitPending, setCommitPending] = useState(null);

  // Derive active scenario from context
  const activeScenario = workingBranch
    ? {
        id: workingBranch.id,
        name: workingBranch.name,
        scenario_type: workingBranch.scenario_type || 'WORKING',
        status: workingBranch.status || 'DRAFT',
        net_benefit: workingBranch.net_benefit,
        parent_scenario_id: configId,
      }
    : {
        id: configId,
        name: configName || 'Baseline',
        scenario_type: 'BASELINE',
        status: null,
        net_benefit: null,
      };

  // Load scenario tree for current config
  const loadTree = useCallback(async () => {
    if (!configId) return;
    setLoading(true);
    try {
      const res = await api.get(`/supply-chain-config/${configId}/tree`);
      setTreeData(res.data);
    } catch (err) {
      console.debug('Scenario tree not available:', err.response?.status);
      setTreeData(null);
    } finally {
      setLoading(false);
    }
  }, [configId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  // ─── Actions ──────────────────────────────────────────────────────────

  const handleSelectScenario = useCallback((scenario) => {
    setPopoverOpen(false);
    if (scenario.scenario_type === 'BASELINE' || scenario.id === configId) {
      clearWorkingBranch();
    } else {
      setWorkingBranch(scenario);
    }
  }, [configId, setWorkingBranch, clearWorkingBranch]);

  const handleCreateBranch = useCallback(async () => {
    if (!branchName.trim() || !configId) return;
    setActionLoading(true);
    try {
      // Use context's createBranch which handles API + state update
      await createBranch(branchName.trim(), branchDescription.trim() || '');
      setBranchDialogOpen(false);
      setBranchName('');
      setBranchDescription('');
      setBranchType('WORKING');
      await loadTree();
    } catch (err) {
      console.error('Failed to create branch:', err);
    } finally {
      setActionLoading(false);
    }
  }, [configId, branchName, branchDescription, createBranch, loadTree]);

  const handleEvaluate = useCallback(async (scenario) => {
    if (!scenario?.id) return;
    setActionLoading(true);
    try {
      // Use planning scenarios evaluate endpoint
      await api.post(`/scenarios/${scenario.id}/evaluate`, {
        num_periods: 12,
        site_key: 'default',
      });
      await loadTree();
    } catch (err) {
      console.error('Failed to evaluate scenario:', err);
    } finally {
      setActionLoading(false);
    }
  }, [loadTree]);

  const handleCommit = useCallback(async (scenario) => {
    if (!scenario?.id) return;
    setActionLoading(true);
    try {
      await api.post(`/supply-chain-config/${scenario.id}/commit`);
      setCommitPending(null);
      clearWorkingBranch();
      await refresh();
      await loadTree();
    } catch (err) {
      if (err.response?.status === 409) {
        // AAP: requires authorization — store thread ID for tracking
        const threadId = err.response?.data?.thread_id;
        setCommitPending({ scenario, authThreadId: threadId });
      } else {
        console.error('Failed to commit:', err);
      }
    } finally {
      setActionLoading(false);
    }
  }, [clearWorkingBranch, refresh, loadTree]);

  const handleRollback = useCallback(async (scenario) => {
    if (!scenario?.id) return;
    if (!window.confirm('Discard all changes in this scenario? This cannot be undone.')) return;
    setActionLoading(true);
    try {
      await api.post(`/supply-chain-config/${scenario.id}/rollback`);
      clearWorkingBranch();
      await refresh();
      await loadTree();
    } catch (err) {
      console.error('Failed to rollback:', err);
    } finally {
      setActionLoading(false);
    }
  }, [clearWorkingBranch, refresh, loadTree]);

  const handleCompare = useCallback(async () => {
    if (!treeData?.children?.length) return;
    setCompareOpen(true);
    try {
      const ids = [treeData.config.id, ...treeData.children.map(c => c.id)].join(',');
      const res = await api.get('/scenarios/compare', { params: { ids } });
      setCompareData(res.data?.comparison);
    } catch (err) {
      console.debug('Compare not available:', err);
      setCompareData(null);
    }
  }, [treeData]);

  // ─── Build flat node list from tree ────────────────────────────────────
  const flatNodes = [];
  if (treeData) {
    // Root config
    flatNodes.push({
      ...treeData.config,
      _depth: 0,
      scenario_type: treeData.config?.scenario_type || 'BASELINE',
    });
    // Ancestors shown as breadcrumb, not in tree
    // Children
    if (treeData.children) {
      for (const child of treeData.children) {
        flatNodes.push({ ...child, _depth: 1 });
      }
    }
  }

  const activeTypeStyle = SCENARIO_TYPE_STYLES[activeScenario?.scenario_type] || SCENARIO_TYPE_STYLES.BASELINE;
  const hasChildren = treeData?.children?.length > 0;
  const isOnBranch = activeScenario?.scenario_type !== 'BASELINE';

  return (
    <>
      {/* Always-visible scenario indicator */}
      <Card className="mb-0">
        <CardContent className="py-2 px-4">
          <div className="flex items-center gap-3">
            {/* Branch icon + current scenario name */}
            <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
              <PopoverTrigger asChild>
                <button className="flex items-center gap-2 hover:bg-muted/50 rounded-md px-2 py-1 transition-colors">
                  <GitBranch className={cn('h-4 w-4', isOnBranch ? 'text-amber-500' : 'text-emerald-500')} />
                  <span className="font-medium text-sm">
                    {activeScenario?.name || configName || 'Baseline'}
                  </span>
                  <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full', activeTypeStyle.bg)}>
                    {activeTypeStyle.label}
                  </span>
                  <ChevronDown className="h-3 w-3 text-muted-foreground" />
                </button>
              </PopoverTrigger>

              <PopoverContent className="w-80 p-0" align="start">
                <div className="p-3 border-b">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold">Scenario Tree</span>
                    <div className="flex items-center gap-1">
                      {hasChildren && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={handleCompare}
                        >
                          <BarChart3 className="h-3 w-3 mr-1" />
                          Compare
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => { setPopoverOpen(false); setBranchDialogOpen(true); }}
                      >
                        <Plus className="h-3 w-3 mr-1" />
                        Branch
                      </Button>
                    </div>
                  </div>

                  {/* Ancestor breadcrumb */}
                  {treeData?.ancestors?.length > 0 && (
                    <div className="flex items-center gap-1 mb-2 text-xs text-muted-foreground">
                      {treeData.ancestors.map((a, i) => (
                        <React.Fragment key={a.id}>
                          {i > 0 && <ArrowRight className="h-3 w-3" />}
                          <button
                            className="hover:text-primary hover:underline"
                            onClick={() => handleSelectScenario({
                              id: a.id,
                              name: a.name,
                              scenario_type: a.scenario_type || 'BASELINE',
                            })}
                          >
                            {a.name}
                          </button>
                        </React.Fragment>
                      ))}
                      <ArrowRight className="h-3 w-3" />
                    </div>
                  )}
                </div>

                {/* Tree nodes */}
                <div className="p-2 max-h-64 overflow-y-auto">
                  {loading ? (
                    <div className="flex items-center justify-center py-4">
                      <Spinner className="h-4 w-4" />
                    </div>
                  ) : flatNodes.length > 0 ? (
                    flatNodes.map((node) => (
                      <TreeNode
                        key={node.id}
                        scenario={node}
                        isActive={activeScenario?.id === node.id}
                        depth={node._depth}
                        onSelect={handleSelectScenario}
                        onEvaluate={handleEvaluate}
                        onCommit={handleCommit}
                        onRollback={handleRollback}
                      />
                    ))
                  ) : (
                    <p className="text-xs text-muted-foreground py-2 text-center">
                      No scenario tree. Create a branch to start.
                    </p>
                  )}
                </div>

                {/* Quick actions footer */}
                <div className="p-2 border-t bg-muted/30">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs h-7"
                    onClick={() => { setPopoverOpen(false); setBranchDialogOpen(true); }}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    Create What-If Scenario
                  </Button>
                </div>
              </PopoverContent>
            </Popover>

            {/* Scenario status indicators */}
            <div className="flex items-center gap-2 flex-1 justify-end">
              {/* Net benefit badge */}
              {activeScenario?.net_benefit != null && (
                <Badge
                  variant={activeScenario.net_benefit >= 0 ? 'default' : 'destructive'}
                  className="text-xs"
                >
                  Net Benefit: {fmtBenefit(activeScenario.net_benefit)}
                </Badge>
              )}

              {/* Pending authorization indicator */}
              {commitPending && (
                <Badge variant="warning" className="text-xs flex items-center gap-1">
                  <Shield className="h-3 w-3" />
                  Awaiting Authorization
                </Badge>
              )}

              {/* Working scenario quick actions */}
              {isOnBranch && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleEvaluate(activeScenario)}
                    disabled={actionLoading}
                    title="Evaluate scenario (run what-if)"
                  >
                    <BarChart3 className="h-3.5 w-3.5 mr-1" />
                    Evaluate
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleCommit(activeScenario)}
                    disabled={actionLoading}
                    title="Commit changes to parent (requires approval for cross-authority changes)"
                  >
                    <GitCommit className="h-3.5 w-3.5 mr-1" />
                    Commit
                  </Button>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ─── Create Branch Dialog ─────────────────────────────────────────── */}
      <Modal
        isOpen={branchDialogOpen}
        onClose={() => !actionLoading && setBranchDialogOpen(false)}
        title="Create What-If Scenario"
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setBranchDialogOpen(false)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateBranch}
              disabled={actionLoading || !branchName.trim()}
            >
              {actionLoading ? <Spinner className="h-4 w-4 mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
              Create Scenario
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Alert variant="info">
            <AlertDescription className="text-sm">
              Create a branch from <strong>{activeScenario?.name || 'Baseline'}</strong>.
              Changes are stored as deltas (copy-on-write). To commit changes back,
              you will need approval from responsible agents/users for any parameters
              outside your authority.
            </AlertDescription>
          </Alert>

          <div>
            <Label htmlFor="branch-name">Scenario Name</Label>
            <Input
              id="branch-name"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              placeholder="e.g., Q2 Demand Spike, Safety Stock +20%"
              disabled={actionLoading}
            />
          </div>

          <div>
            <Label htmlFor="branch-desc">Description (what are you testing?)</Label>
            <Textarea
              id="branch-desc"
              value={branchDescription}
              onChange={(e) => setBranchDescription(e.target.value)}
              rows={3}
              placeholder="Describe the hypothesis you want to test..."
              disabled={actionLoading}
            />
          </div>

          <div>
            <Label htmlFor="branch-type">Scenario Type</Label>
            <select
              id="branch-type"
              value={branchType}
              onChange={(e) => setBranchType(e.target.value)}
              disabled={actionLoading}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="WORKING">Working -- active changes to commit back</option>
              <option value="SIMULATION">Simulation -- exploratory what-if analysis</option>
            </select>
          </div>
        </div>
      </Modal>

      {/* ─── Scorecard Comparison Modal ───────────────────────────────────── */}
      <Modal
        isOpen={compareOpen}
        onClose={() => setCompareOpen(false)}
        title="Scenario Comparison"
        size="lg"
        footer={
          <Button variant="outline" onClick={() => setCompareOpen(false)}>
            Close
          </Button>
        }
      >
        {compareData ? (
          <div className="space-y-4">
            {compareData.map((item) => (
              <Card key={item.scenario_id || item.name}>
                <CardContent className="py-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      {item.net_benefit != null && (
                        <Badge variant={item.net_benefit >= 0 ? 'default' : 'destructive'} className="text-xs">
                          {fmtBenefit(item.net_benefit)}
                        </Badge>
                      )}
                    </div>
                    <span className={cn('text-xs px-2 py-0.5 rounded-full',
                      STATUS_STYLES[item.status] || STATUS_STYLES.DRAFT)}>
                      {item.status || 'DRAFT'}
                    </span>
                  </div>
                  <ScorecardMini scorecard={item.balanced_scorecard} />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center py-8">
            <Spinner className="h-6 w-6 mr-2" />
            <span className="text-muted-foreground">Loading comparison...</span>
          </div>
        )}
      </Modal>
    </>
  );
};

export default ScenarioContextBar;
