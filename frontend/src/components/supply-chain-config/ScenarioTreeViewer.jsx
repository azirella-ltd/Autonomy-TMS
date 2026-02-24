/**
 * Scenario Tree Viewer
 *
 * Displays git-like tree of supply chain configuration scenarios with:
 * - Parent-child relationships
 * - Branch/commit/rollback actions
 * - Delta visualization
 * - Scenario type badges (BASELINE, WORKING, SIMULATION)
 */

import React, { useState, useEffect } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Modal,
  Spinner,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import {
  GitBranch,
  Plus,
  Check,
  Undo2,
  ArrowLeftRight,
  Play,
  Eye,
} from 'lucide-react';
import { useSnackbar } from 'notistack';
import { api } from '../../services/api';

const ScenarioTreeViewer = ({ configId, onConfigChange }) => {
  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [branchDialogOpen, setBranchDialogOpen] = useState(false);
  const [branchName, setBranchName] = useState('');
  const [branchDescription, setBranchDescription] = useState('');
  const [branchType, setBranchType] = useState('WORKING');
  const [actionLoading, setActionLoading] = useState(false);

  const { enqueueSnackbar } = useSnackbar();

  useEffect(() => {
    if (configId) {
      loadScenarioTree();
    }
  }, [configId]);

  const loadScenarioTree = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/supply-chain-config/${configId}/tree`);
      setTreeData(response.data);
    } catch (error) {
      console.error('Failed to load scenario tree:', error);
      enqueueSnackbar('Failed to load scenario tree', { variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBranch = async () => {
    if (!branchName.trim()) {
      enqueueSnackbar('Branch name is required', { variant: 'error' });
      return;
    }

    try {
      setActionLoading(true);
      const response = await api.post(`/supply-chain-config/${configId}/branch`, {
        name: branchName.trim(),
        description: branchDescription.trim(),
        scenario_type: branchType,
      });

      enqueueSnackbar(response.data.message || 'Branch created successfully', {
        variant: 'success',
      });

      // Close dialog and reload tree
      setBranchDialogOpen(false);
      setBranchName('');
      setBranchDescription('');
      setBranchType('WORKING');
      loadScenarioTree();

      // Notify parent if callback provided
      if (onConfigChange) {
        onConfigChange(response.data);
      }
    } catch (error) {
      console.error('Failed to create branch:', error);
      enqueueSnackbar(
        error.response?.data?.detail || 'Failed to create branch',
        { variant: 'error' }
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleCommit = async (childConfigId) => {
    try {
      setActionLoading(true);
      const response = await api.post(`/supply-chain-config/${childConfigId}/commit`);

      enqueueSnackbar(response.data.message || 'Scenario committed successfully', {
        variant: 'success',
      });

      loadScenarioTree();
    } catch (error) {
      console.error('Failed to commit scenario:', error);
      enqueueSnackbar(
        error.response?.data?.detail || 'Failed to commit scenario',
        { variant: 'error' }
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleRollback = async (childConfigId) => {
    if (!window.confirm('Are you sure? This will discard all uncommitted changes.')) {
      return;
    }

    try {
      setActionLoading(true);
      const response = await api.post(`/supply-chain-config/${childConfigId}/rollback`);

      enqueueSnackbar(response.data.message || 'Scenario rolled back successfully', {
        variant: 'success',
      });

      loadScenarioTree();
    } catch (error) {
      console.error('Failed to rollback scenario:', error);
      enqueueSnackbar(
        error.response?.data?.detail || 'Failed to rollback scenario',
        { variant: 'error' }
      );
    } finally {
      setActionLoading(false);
    }
  };

  const [effectiveConfig, setEffectiveConfig] = useState(null);
  const [effectiveDialogOpen, setEffectiveDialogOpen] = useState(false);

  const handleViewEffective = async (childConfigId) => {
    try {
      const response = await api.get(`/supply-chain-config/${childConfigId}/effective`);
      setEffectiveConfig(response.data);
      setEffectiveDialogOpen(true);
    } catch (error) {
      console.error('Failed to load effective config:', error);
      enqueueSnackbar(
        error.response?.data?.detail || 'Failed to load effective configuration',
        { variant: 'error' }
      );
    }
  };

  const getScenarioTypeVariant = (scenarioType) => {
    switch (scenarioType) {
      case 'BASELINE':
        return 'default';
      case 'WORKING':
        return 'warning';
      case 'SIMULATION':
        return 'info';
      default:
        return 'secondary';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return dateString;
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!treeData) {
    return (
      <Alert variant="info">
        No scenario tree data available. This configuration may not support branching.
      </Alert>
    );
  }

  const { config, ancestors, children } = treeData;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <GitBranch className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">Scenario Tree</h3>
        <div className="flex-1" />
        <Button
          onClick={() => setBranchDialogOpen(true)}
          disabled={actionLoading}
          leftIcon={<Plus className="h-4 w-4" />}
        >
          Create Branch
        </Button>
      </div>

      {/* Ancestors (if any) */}
      {ancestors && ancestors.length > 0 && (
        <Card className="mb-4 bg-muted/50">
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground mb-2">Ancestors</p>
            <div className="flex items-center gap-2 flex-wrap">
              {ancestors.map((ancestor, index) => (
                <React.Fragment key={ancestor.id}>
                  {index > 0 && <span className="text-sm">→</span>}
                  <Badge variant={getScenarioTypeVariant(ancestor.scenario_type)}>
                    {ancestor.name}
                  </Badge>
                </React.Fragment>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Current Configuration */}
      <Card className="mb-4 border-2 border-primary">
        <CardContent className="pt-4">
          <div className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <h4 className="text-lg font-semibold">{config.name}</h4>
              <Badge variant={getScenarioTypeVariant(config.scenario_type)}>
                {config.scenario_type}
              </Badge>
              {config.committed_at && (
                <Badge variant="outline">
                  Committed {formatDate(config.committed_at)}
                </Badge>
              )}
            </div>

            {config.description && (
              <p className="text-sm text-muted-foreground">{config.description}</p>
            )}

            <div className="flex items-center gap-2 flex-wrap">
              {config.scenario_type === 'WORKING' && !config.committed_at && (
                <>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleCommit(config.id)}
                          disabled={actionLoading || !config.parent_config_id}
                          leftIcon={<Check className="h-4 w-4" />}
                        >
                          Commit
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Commit changes to parent baseline</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRollback(config.id)}
                          disabled={actionLoading}
                          className="text-destructive"
                          leftIcon={<Undo2 className="h-4 w-4" />}
                        >
                          Rollback
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Discard all uncommitted changes</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </>
              )}
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleViewEffective(config.id)}
                      leftIcon={<Eye className="h-4 w-4" />}
                    >
                      View Effective
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>View effective configuration (merged with ancestors)</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>

            {config.branched_at && (
              <p className="text-xs text-muted-foreground">
                Branched: {formatDate(config.branched_at)}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Children (branches from this config) */}
      {children && children.length > 0 && (
        <div>
          <p className="text-sm text-muted-foreground mb-2 ml-4">
            Branches ({children.length})
          </p>
          <div className="pl-8 border-l-2 border-border space-y-2">
            {children.map((child) => (
              <Card key={child.id} variant="outline">
                <CardContent className="py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{child.name}</span>
                        <Badge variant={getScenarioTypeVariant(child.scenario_type)} className="text-xs">
                          {child.scenario_type}
                        </Badge>
                      </div>
                      {child.branched_at && (
                        <p className="text-xs text-muted-foreground">
                          Branched: {formatDate(child.branched_at)}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                if (onConfigChange) {
                                  onConfigChange({ id: child.id });
                                }
                              }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>View this branch</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      {child.scenario_type === 'WORKING' && (
                        <>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleCommit(child.id)}
                                  disabled={actionLoading}
                                >
                                  <Check className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Commit to parent</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRollback(child.id)}
                                  disabled={actionLoading}
                                  className="text-destructive"
                                >
                                  <Undo2 className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Rollback changes</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {children && children.length === 0 && (
        <Alert variant="info" className="mt-4">
          No branches created yet. Click "Create Branch" to start experimenting with variants.
        </Alert>
      )}

      {/* Create Branch Dialog */}
      <Modal
        isOpen={branchDialogOpen}
        onClose={() => !actionLoading && setBranchDialogOpen(false)}
        title="Create Scenario Branch"
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setBranchDialogOpen(false)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateBranch}
              disabled={actionLoading || !branchName.trim()}
              leftIcon={actionLoading ? <Spinner size="sm" /> : <Plus className="h-4 w-4" />}
            >
              Create Branch
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="branch-name">Branch Name</Label>
            <Input
              id="branch-name"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              placeholder="e.g., Case Config, Six-Pack Config"
              disabled={actionLoading}
            />
          </div>
          <div>
            <Label htmlFor="branch-description">Description</Label>
            <Textarea
              id="branch-description"
              value={branchDescription}
              onChange={(e) => setBranchDescription(e.target.value)}
              rows={3}
              placeholder="Describe the purpose of this branch..."
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
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="WORKING">WORKING - For active development</option>
              <option value="SIMULATION">SIMULATION - For what-if analysis</option>
            </select>
          </div>
          <Alert variant="info">
            <p className="text-sm">
              <strong>Copy-on-Write:</strong> The new branch will inherit all entities from "{config.name}".
              Only your changes will be stored as deltas (~90% storage savings).
            </p>
          </Alert>
        </div>
      </Modal>

      {/* Effective Configuration Dialog */}
      <Modal
        isOpen={effectiveDialogOpen}
        onClose={() => setEffectiveDialogOpen(false)}
        title="Effective Configuration"
        size="lg"
        footer={
          <Button variant="outline" onClick={() => setEffectiveDialogOpen(false)}>
            Close
          </Button>
        }
      >
        {effectiveConfig && (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            <div>
              <span className="font-medium">Name:</span> {effectiveConfig.name}
            </div>
            {effectiveConfig.description && (
              <div>
                <span className="font-medium">Description:</span> {effectiveConfig.description}
              </div>
            )}
            <div>
              <span className="font-medium">Sites:</span> {effectiveConfig.sites?.length || 0}
            </div>
            <div>
              <span className="font-medium">Lanes:</span> {effectiveConfig.transportation_lanes?.length || effectiveConfig.lanes?.length || 0}
            </div>
            <div>
              <span className="font-medium">Products:</span> {effectiveConfig.products?.length || effectiveConfig.items?.length || 0}
            </div>
            <pre className="bg-muted p-3 rounded text-xs overflow-auto max-h-60">
              {JSON.stringify(effectiveConfig, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ScenarioTreeViewer;
