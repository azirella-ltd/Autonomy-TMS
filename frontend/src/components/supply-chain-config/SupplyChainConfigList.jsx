import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Modal,
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
} from '../common';
import {
  Plus,
  Pencil,
  Trash2,
  CheckCircle,
  Circle,
  Copy,
  MoreVertical,
  Gamepad2,
  Play,
  Clock,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  Network,
} from 'lucide-react';
import { useSnackbar } from 'notistack';
import { format } from 'date-fns';
import { api } from '../../services/api';
import { getSupplyChainConfigs, trainSupplyChainConfig } from '../../services/supplyChainConfigService';

const SupplyChainConfigList = ({
  title = 'Supply Chain Configurations',
  basePath = '/supply-chain-config',
  restrictToGroupId = null,
  enableTraining = false,
  readOnly = false,  // When true, hides create/edit/delete actions
} = {}) => {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [configToDelete, setConfigToDelete] = useState(null);
  const [activatingConfig, setActivatingConfig] = useState(null);
  const [trainingStatus, setTrainingStatus] = useState({});
  const [validatingConfig, setValidatingConfig] = useState(null);

  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const formatDate = (value) => {
    if (!value) return '—';
    try {
      return format(new Date(value), 'MMM d, yyyy');
    } catch (err) {
      return value;
    }
  };

  const formatTimeBucket = (value) => {
    if (!value) return 'Week';
    const normalized = String(value).trim().toLowerCase();
    if (normalized === 'day') return 'Day';
    if (normalized === 'month') return 'Month';
    return 'Week';
  };

  const normalizedStatus = (config) => String(config?.training_status || '').toLowerCase();

  const isTrainingActive = (config) => {
    if (!config) return false;
    if (trainingStatus[config.id]?.inProgress) return true;
    return normalizedStatus(config) === 'in_progress';
  };

  const canTrainConfig = (config) => {
    if (!enableTraining || !config) return false;
    if (isTrainingActive(config)) return false;
    const status = normalizedStatus(config);
    if (config.needs_training) return true;
    if (status === 'failed' || status === 'error') return true;
    return false;
  };

  const renderTrainingBadge = (config) => {
    const status = normalizedStatus(config);
    let trainedAt = null;
    if (config?.trained_at) {
      try {
        trainedAt = format(new Date(config.trained_at), 'MMM d, yyyy HH:mm');
      } catch (err) {
        trainedAt = null;
      }
    }

    if (trainingStatus[config?.id]?.inProgress || status === 'in_progress') {
      return (
        <Badge variant="info" className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          Training…
        </Badge>
      );
    }

    if (config?.needs_training) {
      return (
        <Badge variant="warning" className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          Needs training
        </Badge>
      );
    }

    if (status === 'failed' || status === 'error') {
      return (
        <Badge variant="destructive" className="flex items-center gap-1">
          <AlertCircle className="h-3 w-3" />
          Training failed
        </Badge>
      );
    }

    if (status === 'trained' || status === 'complete' || !config?.needs_training) {
      return (
        <Badge variant="success" className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" />
          {trainedAt ? `Trained • ${trainedAt}` : 'Trained'}
        </Badge>
      );
    }

    return (
      <Badge variant="secondary" className="flex items-center gap-1">
        <Clock className="h-3 w-3" />
        {status ? status.replace(/_/g, ' ') : 'Status unknown'}
      </Badge>
    );
  };

  const fetchConfigs = useCallback(async () => {
    try {
      setLoading(true);
      // Backend already filters by user's group - no additional frontend filtering needed
      const configs = await getSupplyChainConfigs();
      setConfigs(configs || []);
      setError(null);
    } catch (err) {
      console.warn('Supply chain configs endpoint unavailable; showing empty list.', err?.response?.status);
      setConfigs([]);
      setError('Unable to load supply chain configurations right now.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const handleCreateNew = () => {
    navigate(`${basePath}/new`);
  };

  const handleEdit = (id) => {
    navigate(`${basePath}/edit/${id}`);
  };

  const handleDeleteClick = (config) => {
    setConfigToDelete(config);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!configToDelete) return;

    try {
      await api.delete(`/supply-chain-config/${configToDelete.id}/`);
      enqueueSnackbar('Configuration deleted successfully', { variant: 'success' });
      await fetchConfigs();
    } catch (err) {
      console.error('Error deleting configuration:', err);
      enqueueSnackbar('Failed to delete configuration', { variant: 'error' });
    } finally {
      setDeleteDialogOpen(false);
      setConfigToDelete(null);
    }
  };

  const handleCreateGame = (config) => {
    navigate(`/scenarios/new-from-config/${config.id}`);
  };

  const handleViewScenarios = (config) => {
    navigate(`${basePath}/${config.id}/scenarios`);
  };

  const handleActivateConfig = async (configId) => {
    if (!configId || activatingConfig === configId) return;

    try {
      setActivatingConfig(configId);
      await api.put(`/supply-chain-config/${configId}/`, { is_active: true });
      enqueueSnackbar('Configuration activated successfully', { variant: 'success' });
      await fetchConfigs();
    } catch (err) {
      console.error('Error activating configuration:', err);
      enqueueSnackbar('Failed to activate configuration', { variant: 'error' });
    } finally {
      setActivatingConfig(null);
    }
  };

  const handleDuplicate = async (config) => {
    if (!config) return;

    try {
      const { id, created_at, updated_at, is_active, ...configData } = config;
      await api.post('/supply-chain-config', {
        ...configData,
        tenant_id: config.tenant_id ?? configData.tenant_id ?? null,
        name: `${config.name} (Copy)`,
        is_active: false,
      });
      enqueueSnackbar('Configuration duplicated successfully', { variant: 'success' });
      await fetchConfigs();
    } catch (err) {
      console.error('Error duplicating configuration:', err);
      enqueueSnackbar('Failed to duplicate configuration', { variant: 'error' });
    }
  };

  const handleTrainConfig = async (config) => {
    if (!config || !enableTraining) return;
    const configId = config.id;
    setTrainingStatus((prev) => ({ ...prev, [configId]: { inProgress: true } }));

    try {
      const response = await trainSupplyChainConfig(configId, {});
      const message = response?.message || 'Training completed successfully';
      enqueueSnackbar(message, { variant: 'success' });
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Failed to train configuration';
      enqueueSnackbar(detail, { variant: 'error' });
    } finally {
      setTrainingStatus((prev) => ({ ...prev, [configId]: { inProgress: false } }));
      await fetchConfigs();
    }
  };

  const handleValidateConfig = async (configId) => {
    if (!configId || validatingConfig === configId) return;

    try {
      setValidatingConfig(configId);
      const response = await api.post(`/supply-chain-config/${configId}/validate`);

      if (response.data.is_valid) {
        enqueueSnackbar('Configuration is valid', { variant: 'success' });
      } else {
        const errorList = response.data.errors?.join(', ') || 'Validation failed';
        enqueueSnackbar(`Validation errors: ${errorList}`, { variant: 'error', autoHideDuration: 10000 });
      }

      await fetchConfigs();
    } catch (err) {
      console.error('Error validating configuration:', err);
      const detail = err?.response?.data?.detail || 'Failed to validate configuration';
      enqueueSnackbar(detail, { variant: 'error' });
    } finally {
      setValidatingConfig(null);
    }
  };

  const renderTableBody = () => {
    if (configs.length === 0) {
      return (
        <TableRow>
          <TableCell colSpan={5} className="text-center py-8">
            {loading ? (
              <Spinner size="md" />
            ) : (
              <p className={error ? 'text-destructive' : 'text-muted-foreground'}>
                {error || 'No supply chain configurations found. Create your first configuration to get started.'}
              </p>
            )}
          </TableCell>
        </TableRow>
      );
    }

    return configs.map((config) => {
      const needsTraining =
        enableTraining &&
        (config.needs_training ||
          normalizedStatus(config) === 'failed' ||
          normalizedStatus(config) === 'error' ||
          !config.trained_at);

      const isFullyActive = config.is_active && !needsTraining;

      return (
        <TableRow key={config.id}>
          <TableCell>
            <span className="font-semibold">{config.name}</span>
          </TableCell>
          <TableCell>
            <span className="text-sm text-muted-foreground" title={config.description || 'No description provided'}>
              {config.description || 'No description provided'}
            </span>
          </TableCell>
          <TableCell>
            <span className="text-sm">{formatTimeBucket(config.time_bucket)}</span>
          </TableCell>
          <TableCell>
            {isFullyActive ? (
              <Badge variant="success" className="flex items-center gap-1 w-fit">
                <CheckCircle className="h-3 w-3" />
                Active
              </Badge>
            ) : config.is_active && needsTraining ? (
              <Badge variant="warning" className="flex items-center gap-1 w-fit">
                <Clock className="h-3 w-3" />
                Needs Training
              </Badge>
            ) : (
              <Badge variant="secondary" className="flex items-center gap-1 w-fit">
                <Circle className="h-3 w-3" />
                Inactive
              </Badge>
            )}
          </TableCell>
          <TableCell className="text-right">
            <div className="flex items-center justify-end gap-1">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleValidateConfig(config.id)}
                      disabled={validatingConfig === config.id}
                      className={
                        config.validation_status === 'valid'
                          ? 'text-success'
                          : config.validation_status === 'invalid'
                          ? 'text-destructive'
                          : ''
                      }
                    >
                      {validatingConfig === config.id ? (
                        <Spinner size="sm" />
                      ) : config.validation_status === 'valid' ? (
                        <ShieldCheck className="h-4 w-4" />
                      ) : config.validation_status === 'invalid' ? (
                        <AlertTriangle className="h-4 w-4" />
                      ) : (
                        <HelpCircle className="h-4 w-4" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {config.validation_status === 'valid'
                      ? 'Configuration is valid'
                      : config.validation_status === 'invalid'
                      ? `Validation errors: ${config.validation_errors?.join(', ') || 'Unknown errors'}`
                      : 'Click to validate configuration'}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              {!readOnly && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="sm" onClick={() => handleEdit(config.id)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Edit</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {!readOnly && (
                    <DropdownMenuItem onClick={() => handleEdit(config.id)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={() => handleViewScenarios(config)}>
                    <Network className="h-4 w-4 mr-2" />
                    Scenarios
                  </DropdownMenuItem>
                  {enableTraining && !readOnly && (
                    <DropdownMenuItem
                      onClick={() => handleTrainConfig(config)}
                      disabled={!canTrainConfig(config)}
                    >
                      {isTrainingActive(config) || trainingStatus[config?.id]?.inProgress ? (
                        <Spinner size="sm" className="mr-2" />
                      ) : (
                        <Play className="h-4 w-4 mr-2" />
                      )}
                      Train
                    </DropdownMenuItem>
                  )}
                  {!readOnly && (
                    <>
                      <DropdownMenuItem onClick={() => handleCreateGame(config)}>
                        <Gamepad2 className="h-4 w-4 mr-2" />
                        Create Game
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => handleDuplicate(config)}>
                        <Copy className="h-4 w-4 mr-2" />
                        Duplicate
                      </DropdownMenuItem>
                      {!config.is_active && (
                        <DropdownMenuItem
                          onClick={() => handleActivateConfig(config.id)}
                          disabled={activatingConfig === config.id}
                        >
                          {activatingConfig === config.id ? (
                            <Spinner size="sm" className="mr-2" />
                          ) : (
                            <Circle className="h-4 w-4 mr-2" />
                          )}
                          Activate
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem
                        onClick={() => handleDeleteClick(config)}
                        disabled={config.is_active}
                        className="text-destructive"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>

              {!readOnly && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => handleDeleteClick(config)}
                        disabled={config.is_active}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {config.is_active ? 'Deactivate before deleting' : 'Delete'}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
          </TableCell>
        </TableRow>
      );
    });
  };

  return (
    <>
      <Card className="p-6">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <div>
            <h2 className="text-lg font-bold">{title}</h2>
            <p className="text-sm text-muted-foreground">
              Manage the supply chain setups available for your organization&apos;s scenarios.
            </p>
          </div>
          {!readOnly && (
            <Button onClick={handleCreateNew} leftIcon={<Plus className="h-4 w-4" />}>
              New Configuration
            </Button>
          )}
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[20%]">Name</TableHead>
              <TableHead className="w-[40%]">Description</TableHead>
              <TableHead className="w-[12%]">Time Bucket</TableHead>
              <TableHead className="w-[13%]">Status</TableHead>
              <TableHead className="w-[15%] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {renderTableBody()}
            {loading && configs.length > 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center">
                  <Spinner size="sm" />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Modal
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        title="Delete Configuration"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm}>
              Delete
            </Button>
          </div>
        }
      >
        <p className="text-muted-foreground">
          Are you sure you want to delete the configuration &quot;{configToDelete?.name}&quot;? This action cannot be undone.
        </p>
      </Modal>
    </>
  );
};

export default SupplyChainConfigList;
