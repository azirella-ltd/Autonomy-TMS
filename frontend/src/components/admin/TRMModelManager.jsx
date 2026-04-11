/**
 * TRM Model Manager Component
 *
 * Manages TRM model loading, unloading, and checkpoint management.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHeader,
  TableHead,
  TableRow,
  Badge,
  Alert,
  Spinner,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
} from '../common';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  CloudUpload,
  CloudDownload,
  Trash2,
  Info,
  CheckCircle,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { loadModel, getModelInfo, listCheckpoints, unloadModel } from '../../services/trmApi';

// Parse checkpoint name to extract site/type metadata
// Naming conventions:
//   trm_{type}_site{site_id}_v{N}.pt   (per-site)
//   trm_{type}_base_{master_type}.pt   (base model)
//   trm_{type}_{config_id}.pt          (legacy)
const parseCheckpointName = (name) => {
  const siteMatch = name.match(/^trm_(\w+)_site(\d+)_v(\d+)/);
  if (siteMatch) {
    return { trmType: siteMatch[1], siteId: parseInt(siteMatch[2]), version: parseInt(siteMatch[3]), group: `Site ${siteMatch[2]}` };
  }
  const baseMatch = name.match(/^trm_(\w+)_base_(\w+)/);
  if (baseMatch) {
    return { trmType: baseMatch[1], masterType: baseMatch[2], group: 'Base Models' };
  }
  return { group: 'Legacy / Global' };
};

// Group checkpoints by site/category
const groupCheckpoints = (checkpoints) => {
  const groups = {};
  for (const cp of checkpoints) {
    const meta = parseCheckpointName(cp.name);
    const key = meta.group;
    if (!groups[key]) groups[key] = [];
    groups[key].push({ ...cp, _meta: meta });
  }
  // Sort: Site groups first (numerically), then Base Models, then Legacy
  const sortedKeys = Object.keys(groups).sort((a, b) => {
    const siteA = a.match(/^Site (\d+)$/);
    const siteB = b.match(/^Site (\d+)$/);
    if (siteA && siteB) return parseInt(siteA[1]) - parseInt(siteB[1]);
    if (siteA) return -1;
    if (siteB) return 1;
    if (a === 'Base Models') return -1;
    if (b === 'Base Models') return 1;
    return a.localeCompare(b);
  });
  return sortedKeys.map(key => ({ label: key, checkpoints: groups[key] }));
};

const TRMModelManager = () => {
  const [modelInfo, setModelInfo] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [loadDialogOpen, setLoadDialogOpen] = useState(false);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState('cpu');

  useEffect(() => {
    loadModelInfo();
    loadCheckpointList();
  }, []);

  const loadModelInfo = async () => {
    try {
      const info = await getModelInfo();
      setModelInfo(info);
    } catch (err) {
      console.error('Failed to load model info:', err);
    }
  };

  const loadCheckpointList = async () => {
    setLoading(true);
    try {
      const response = await listCheckpoints();
      setCheckpoints(response.checkpoints || []);
    } catch (err) {
      setError('Failed to load checkpoints');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadModel = async () => {
    if (!selectedCheckpoint) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const info = await loadModel(selectedCheckpoint.path, selectedDevice);
      setModelInfo(info);
      setSuccess(`Model loaded successfully: ${selectedCheckpoint.name}`);
      setLoadDialogOpen(false);
    } catch (err) {
      setError(`Failed to load model: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUnloadModel = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await unloadModel();
      setModelInfo(null);
      setSuccess('Model unloaded successfully');
      loadModelInfo();
    } catch (err) {
      setError(`Failed to unload model: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  const formatNumber = (num) => {
    return num ? num.toLocaleString() : 'N/A';
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <Typography variant="h4">
          AI Agent Manager
        </Typography>
        <Button
          variant="outline"
          leftIcon={<RefreshCw className="h-4 w-4" />}
          onClick={() => {
            loadModelInfo();
            loadCheckpointList();
          }}
        >
          Refresh
        </Button>
      </div>

      {/* Error/Success Alerts */}
      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" onClose={() => setSuccess(null)} className="mb-4">
          {success}
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Current Model Info */}
        <Card>
          <CardContent className="p-6">
            <Typography variant="h6" gutterBottom>
              Current Model
            </Typography>

            {modelInfo ? (
              <>
                <div className="flex items-center mb-4">
                  {modelInfo.model_loaded ? (
                    <CheckCircle className="h-5 w-5 text-emerald-500 mr-2" />
                  ) : (
                    <XCircle className="h-5 w-5 text-destructive mr-2" />
                  )}
                  <Badge
                    variant={modelInfo.model_loaded ? 'success' : 'secondary'}
                  >
                    {modelInfo.model_loaded ? 'Loaded' : 'Not Loaded'}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="ml-2"
                  >
                    {modelInfo.device.toUpperCase()}
                  </Badge>
                </div>

                {modelInfo.model_loaded && modelInfo.parameters && (
                  <div className="mb-4 space-y-1">
                    <Typography variant="body2">
                      <strong>Total Parameters:</strong> {formatNumber(modelInfo.parameters.total)}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Encoder:</strong> {formatNumber(modelInfo.parameters.encoder)}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Refinement:</strong> {formatNumber(modelInfo.parameters.refinement)}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Decision Head:</strong> {formatNumber(modelInfo.parameters.decision_head)}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Value Head:</strong> {formatNumber(modelInfo.parameters.value_head)}
                    </Typography>
                  </div>
                )}

                <Typography variant="body2" gutterBottom>
                  <strong>Window Size:</strong> {modelInfo.window_size}
                </Typography>

                <Typography variant="body2" gutterBottom>
                  <strong>Fallback Enabled:</strong> {modelInfo.use_fallback ? 'Yes' : 'No'}
                </Typography>

                {modelInfo.model_loaded && (
                  <Button
                    variant="destructive"
                    fullWidth
                    onClick={handleUnloadModel}
                    disabled={loading}
                    className="mt-4"
                  >
                    Unload Model
                  </Button>
                )}
              </>
            ) : (
              <Alert variant="info">
                No model information available. Load a model to get started.
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardContent className="p-6">
            <Typography variant="h6" gutterBottom>
              Quick Actions
            </Typography>

            <div className="flex flex-col gap-4">
              <Button
                variant="default"
                leftIcon={<CloudUpload className="h-4 w-4" />}
                onClick={() => setLoadDialogOpen(true)}
                disabled={loading}
                fullWidth
              >
                Load Model
              </Button>

              <Button
                variant="outline"
                leftIcon={<Info className="h-4 w-4" />}
                onClick={loadModelInfo}
                disabled={loading}
                fullWidth
              >
                Refresh Model Info
              </Button>
            </div>

            <div className="mt-6">
              <Typography variant="body2" color="textSecondary">
                <strong>Note:</strong> Loading a model will replace any currently loaded model.
                GPU (CUDA) inference is 3-5x faster than CPU but requires a CUDA-capable device.
              </Typography>
            </div>
          </CardContent>
        </Card>

        {/* Available Checkpoints (grouped by site) */}
        <div className="col-span-1 md:col-span-2">
          <Card>
            <CardContent className="p-6">
              <Typography variant="h6" gutterBottom>
                Available Checkpoints
              </Typography>

              {loading ? (
                <div className="flex justify-center p-6">
                  <Spinner size="lg" />
                </div>
              ) : checkpoints.length > 0 ? (
                <div className="mt-4 space-y-6">
                  {groupCheckpoints(checkpoints).map(group => (
                    <div key={group.label}>
                      <div className="flex items-center gap-2 mb-2">
                        <Typography variant="subtitle2">{group.label}</Typography>
                        <Badge variant="secondary" className="text-xs">
                          {group.checkpoints.length}
                        </Badge>
                      </div>
                      <TableContainer>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Name</TableHead>
                              <TableHead>Size</TableHead>
                              <TableHead>Modified</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {group.checkpoints.map((checkpoint, index) => (
                              <TableRow key={index}>
                                <TableCell>
                                  <Typography variant="body2" className="font-mono">
                                    {checkpoint.name}
                                  </Typography>
                                </TableCell>
                                <TableCell>
                                  {checkpoint.size_mb} MB
                                </TableCell>
                                <TableCell>
                                  {formatDate(checkpoint.modified)}
                                </TableCell>
                                <TableCell className="text-right">
                                  <IconButton
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedCheckpoint(checkpoint);
                                      setLoadDialogOpen(true);
                                    }}
                                    title="Load Model"
                                  >
                                    <CloudDownload className="h-4 w-4 text-primary" />
                                  </IconButton>
                                  <IconButton
                                    variant="ghost"
                                    size="sm"
                                    title="Model Info"
                                  >
                                    <Info className="h-4 w-4" />
                                  </IconButton>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </div>
                  ))}
                </div>
              ) : (
                <Alert variant="info">
                  No checkpoints found. Train a model first to generate checkpoints.
                </Alert>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Load Model Dialog */}
      <Modal isOpen={loadDialogOpen} onClose={() => setLoadDialogOpen(false)} size="md">
        <ModalHeader>
          <ModalTitle>Load AI Agent</ModalTitle>
        </ModalHeader>
        <ModalBody>
          {selectedCheckpoint && (
            <div className="mb-4 space-y-1">
              <Typography variant="body2">
                <strong>Model:</strong> {selectedCheckpoint.name}
              </Typography>
              <Typography variant="body2">
                <strong>Size:</strong> {selectedCheckpoint.size_mb} MB
              </Typography>
              <Typography variant="body2">
                <strong>Path:</strong> <code className="bg-muted px-1 rounded text-sm">{selectedCheckpoint.path}</code>
              </Typography>
            </div>
          )}

          <Typography variant="body2" gutterBottom className="mt-4">
            Select device for inference:
          </Typography>

          <div className="flex gap-2">
            <Badge
              variant={selectedDevice === 'cpu' ? 'default' : 'secondary'}
              onClick={() => setSelectedDevice('cpu')}
              className="cursor-pointer"
            >
              CPU
            </Badge>
            <Badge
              variant={selectedDevice === 'cuda' ? 'default' : 'secondary'}
              onClick={() => setSelectedDevice('cuda')}
              className="cursor-pointer"
            >
              CUDA (GPU)
            </Badge>
          </div>

          <Alert variant="info" className="mt-4">
            <Typography variant="body2">
              <strong>CPU:</strong> Slower but works everywhere (~5-10ms per decision)
              <br />
              <strong>CUDA:</strong> Faster but requires GPU (~2-3ms per decision)
            </Typography>
          </Alert>
        </ModalBody>
        <ModalFooter className="gap-2">
          <Button variant="outline" onClick={() => setLoadDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleLoadModel}
            disabled={loading}
          >
            Load Model
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
};

export default TRMModelManager;
