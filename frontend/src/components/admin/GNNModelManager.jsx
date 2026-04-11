import React, { useState, useEffect } from 'react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  Button,
  IconButton,
  Alert,
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHead,
  TableRow,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Select,
  SelectOption,
  H4,
  Text,
} from '../common';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../ui/tooltip';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  CloudUpload,
  CloudDownload,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import {
  getGNNModelInfo,
  loadGNNModel,
  unloadGNNModel,
  listGNNCheckpoints,
  deleteGNNCheckpoint,
} from '../../services/gnnApi';

const GNNModelManager = ({ selectedConfig }) => {
  const [modelInfo, setModelInfo] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [filteredCheckpoints, setFilteredCheckpoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Load dialog
  const [loadDialogOpen, setLoadDialogOpen] = useState(false);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState('cuda');

  // Fetch model info and checkpoints on mount
  useEffect(() => {
    fetchModelInfo();
    fetchCheckpoints();
  }, []);

  // Filter checkpoints when selectedConfig changes
  useEffect(() => {
    if (!selectedConfig) {
      setFilteredCheckpoints(checkpoints);
    } else {
      // Filter checkpoints by config name (normalize for comparison)
      const normalizedSelected = selectedConfig.toLowerCase().replace(/[\s_-]+/g, '_');
      const filtered = checkpoints.filter((cp) => {
        if (!cp.config_name) return false;
        const cpConfig = cp.config_name.toLowerCase().replace(/[\s_-]+/g, '_');
        return cpConfig === normalizedSelected;
      });
      setFilteredCheckpoints(filtered);
    }
  }, [selectedConfig, checkpoints]);

  const fetchModelInfo = async () => {
    try {
      const info = await getGNNModelInfo();
      setModelInfo(info);
    } catch (err) {
      console.error('Failed to fetch model info:', err);
      // Model may not be loaded, which is fine
      setModelInfo(null);
    }
  };

  const fetchCheckpoints = async () => {
    setLoading(true);
    try {
      const data = await listGNNCheckpoints();
      setCheckpoints(data.checkpoints || []);
    } catch (err) {
      setError('Failed to fetch checkpoints');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadModel = async () => {
    if (!selectedCheckpoint) {
      setError('Please select a checkpoint');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const info = await loadGNNModel(selectedCheckpoint.path, selectedDevice);
      setModelInfo(info);
      setSuccess(`Model loaded successfully: ${selectedCheckpoint.name}`);
      setLoadDialogOpen(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load model');
    } finally {
      setLoading(false);
    }
  };

  const handleUnloadModel = async () => {
    setLoading(true);
    setError(null);
    try {
      await unloadGNNModel();
      setModelInfo(null);
      setSuccess('Model unloaded successfully');
    } catch (err) {
      setError('Failed to unload model');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCheckpoint = async (checkpoint) => {
    if (!window.confirm(`Delete checkpoint ${checkpoint.name}?`)) {
      return;
    }

    setLoading(true);
    try {
      await deleteGNNCheckpoint(checkpoint.path);
      setSuccess(`Deleted checkpoint: ${checkpoint.name}`);
      fetchCheckpoints();
    } catch (err) {
      setError('Failed to delete checkpoint');
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes) return 'N/A';
    const mb = bytes / (1024 * 1024);
    return mb.toFixed(2) + ' MB';
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  return (
    <TooltipProvider>
      <div className="p-6">
        <H4 className="mb-1">Network Agent Manager</H4>
        <Text className="text-muted-foreground mb-4">
          Load, manage, and configure network model checkpoints
        </Text>

        {error && (
          <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        {/* Current Model Info */}
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="flex justify-between items-center mb-4">
              <CardTitle as="h5" className="text-lg">Current Model</CardTitle>
              <div className="flex gap-2">
                {modelInfo && (
                  <Button
                    variant="outline"
                    onClick={handleUnloadModel}
                    disabled={loading}
                    leftIcon={<Trash2 className="h-4 w-4" />}
                    className="text-destructive border-destructive hover:bg-destructive/10"
                  >
                    Unload Model
                  </Button>
                )}
                <Button
                  onClick={() => setLoadDialogOpen(true)}
                  disabled={loading}
                  leftIcon={<CloudUpload className="h-4 w-4" />}
                >
                  Load Model
                </Button>
              </div>
            </div>

            {modelInfo ? (
              <>
                {/* Warning if loaded model doesn't match selected config */}
                {selectedConfig && modelInfo.config_name &&
                  modelInfo.config_name.toLowerCase().replace(/[\s_-]+/g, '_') !==
                  selectedConfig.toLowerCase().replace(/[\s_-]+/g, '_') && (
                  <Alert variant="warning" className="mb-4">
                    <strong>Config Mismatch:</strong> The loaded model was trained on "{modelInfo.config_name}"
                    but you have "{selectedConfig}" selected. Results may be inaccurate.
                  </Alert>
                )}
                <Table>
                <TableBody>
                  <TableRow hoverable={false}>
                    <TableCell className="w-[30%] font-semibold">Status</TableCell>
                    <TableCell>
                      <Badge
                        variant="success"
                        size="sm"
                        icon={<CheckCircle className="h-3 w-3" />}
                      >
                        Loaded
                      </Badge>
                    </TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Model Path</TableCell>
                    <TableCell>{modelInfo.model_path || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Device</TableCell>
                    <TableCell>
                      <Badge
                        variant={modelInfo.device === 'cuda' ? 'default' : 'secondary'}
                        size="sm"
                      >
                        {modelInfo.device?.toUpperCase() || 'N/A'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Total Parameters</TableCell>
                    <TableCell>{modelInfo.num_parameters?.toLocaleString() || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Configuration</TableCell>
                    <TableCell>{modelInfo.config_name || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Training Epochs</TableCell>
                    <TableCell>{modelInfo.epochs || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Final Train Loss</TableCell>
                    <TableCell>{modelInfo.final_train_loss?.toFixed(4) || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Final Val Loss</TableCell>
                    <TableCell>{modelInfo.final_val_loss?.toFixed(4) || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">MAE</TableCell>
                    <TableCell>{modelInfo.mae?.toFixed(4) || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">RMSE</TableCell>
                    <TableCell>{modelInfo.rmse?.toFixed(4) || 'N/A'}</TableCell>
                  </TableRow>
                  <TableRow hoverable={false}>
                    <TableCell className="font-semibold">Loaded At</TableCell>
                    <TableCell>{formatDate(modelInfo.loaded_at)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              </>
            ) : (
              <Alert variant="info">
                No model currently loaded. Click "Load Model" to load a checkpoint.
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Checkpoints List */}
        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-center mb-4">
              <CardTitle as="h5" className="text-lg">Available Checkpoints</CardTitle>
              <Tooltip>
                <TooltipTrigger asChild>
                  <IconButton onClick={fetchCheckpoints} disabled={loading}>
                    <RefreshCw className="h-4 w-4" />
                  </IconButton>
                </TooltipTrigger>
                <TooltipContent>Refresh list</TooltipContent>
              </Tooltip>
            </div>

            {selectedConfig && (
              <Alert variant="info" className="mb-4">
                Showing checkpoints for: <strong>{selectedConfig}</strong>
                {filteredCheckpoints.length === 0 && checkpoints.length > 0 && (
                  <span className="ml-2">({checkpoints.length} total checkpoints exist for other configs)</span>
                )}
              </Alert>
            )}

            {filteredCheckpoints.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Configuration</TableHead>
                    <TableHead>Epochs</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Performance</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredCheckpoints.map((checkpoint) => (
                    <TableRow key={checkpoint.path}>
                      <TableCell>{checkpoint.name}</TableCell>
                      <TableCell>{checkpoint.config_name || 'N/A'}</TableCell>
                      <TableCell>{checkpoint.epochs || 'N/A'}</TableCell>
                      <TableCell>{formatBytes(checkpoint.size)}</TableCell>
                      <TableCell>{formatDate(checkpoint.created_at)}</TableCell>
                      <TableCell>
                        {checkpoint.val_loss ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span>
                                <Badge variant="outline" size="sm">
                                  Loss: {checkpoint.val_loss.toFixed(4)}
                                </Badge>
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              Train: {checkpoint.train_loss?.toFixed(4) || 'N/A'}, Val: {checkpoint.val_loss.toFixed(4)}
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          'N/A'
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <IconButton
                              onClick={() => {
                                setSelectedCheckpoint(checkpoint);
                                setLoadDialogOpen(true);
                              }}
                              disabled={loading}
                              className="mr-1"
                            >
                              <CloudUpload className="h-4 w-4" />
                            </IconButton>
                          </TooltipTrigger>
                          <TooltipContent>Load this checkpoint</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <IconButton
                              onClick={() => handleDeleteCheckpoint(checkpoint)}
                              disabled={loading}
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 className="h-4 w-4" />
                            </IconButton>
                          </TooltipTrigger>
                          <TooltipContent>Delete checkpoint</TooltipContent>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Alert variant="info">
                {selectedConfig
                  ? `No checkpoints found for "${selectedConfig}". Train a model for this configuration to create checkpoints.`
                  : 'No checkpoints found. Train a model to create checkpoints.'}
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Load Model Dialog */}
        <Modal isOpen={loadDialogOpen} onClose={() => setLoadDialogOpen(false)} size="md">
          <ModalHeader>
            <ModalTitle>Load Network Agent</ModalTitle>
          </ModalHeader>
          <ModalBody>
            {selectedCheckpoint && (
              <div className="mb-4 space-y-1">
                <Text className="text-sm">
                  <span className="font-semibold">Checkpoint:</span> {selectedCheckpoint.name}
                </Text>
                <Text className="text-sm">
                  <span className="font-semibold">Configuration:</span> {selectedCheckpoint.config_name || 'N/A'}
                </Text>
                <Text className="text-sm">
                  <span className="font-semibold">Epochs:</span> {selectedCheckpoint.epochs || 'N/A'}
                </Text>
                <Text className="text-sm">
                  <span className="font-semibold">Size:</span> {formatBytes(selectedCheckpoint.size)}
                </Text>
              </div>
            )}

            <div className="mt-4">
              <label className="block text-sm font-medium mb-2">Device</label>
              <Select
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
              >
                <SelectOption value="cuda">GPU (CUDA)</SelectOption>
                <SelectOption value="cpu">CPU</SelectOption>
              </Select>
            </div>

            <Alert variant="warning" className="mt-4">
              Loading a new model will unload the current model if any.
            </Alert>
          </ModalBody>
          <ModalFooter className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setLoadDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleLoadModel}
              disabled={loading || !selectedCheckpoint}
            >
              Load Model
            </Button>
          </ModalFooter>
        </Modal>
      </div>
    </TooltipProvider>
  );
};

export default GNNModelManager;
