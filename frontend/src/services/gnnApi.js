/**
 * GNN (Graph Neural Network) API Client
 *
 * Provides methods for interacting with the GNN management API.
 */

import { api } from './api';

/**
 * Get GNN model information
 * @returns {Promise} Model info
 */
export const getGNNModelInfo = async () => {
  const response = await api.get('/model/gnn/info');
  return response.data;
};

/**
 * Load a GNN model
 * @param {string} modelPath - Path to model checkpoint
 * @param {string} device - Device (cpu or cuda)
 * @returns {Promise} Model info
 */
export const loadGNNModel = async (modelPath, device = 'cpu') => {
  const response = await api.post('/model/gnn/load', {
    model_path: modelPath,
    device: device
  });
  return response.data;
};

/**
 * Unload current GNN model
 * @returns {Promise} Success message
 */
export const unloadGNNModel = async () => {
  const response = await api.delete('/model/gnn');
  return response.data;
};

/**
 * List available GNN checkpoints
 * @param {string} checkpointDir - Checkpoint directory
 * @returns {Promise} List of checkpoints
 */
export const listGNNCheckpoints = async (checkpointDir = './checkpoints') => {
  const response = await api.get('/model/gnn/checkpoints', {
    params: { checkpoint_dir: checkpointDir }
  });
  return response.data;
};

/**
 * Delete a GNN checkpoint
 * @param {string} checkpointPath - Path to checkpoint
 * @returns {Promise} Success message
 */
export const deleteGNNCheckpoint = async (checkpointPath) => {
  const response = await api.delete('/model/gnn/checkpoint', {
    params: { checkpoint_path: checkpointPath }
  });
  return response.data;
};

/**
 * Test GNN model
 * @param {Object} testData - Test input data
 * @returns {Promise} Test results
 */
export const testGNNModel = async (testData) => {
  const response = await api.post('/model/gnn/test', testData);
  return response.data;
};

/**
 * Start GNN training
 * @param {Object} config - Training configuration
 * @returns {Promise} Training status
 */
export const startGNNTraining = async (config) => {
  const response = await api.post('/model/train', config);
  return response.data;
};

/**
 * Get GNN training status
 * @returns {Promise} Current training status
 */
export const getGNNTrainingStatus = async () => {
  const response = await api.get('/model/training-status');
  return response.data;
};

/**
 * Stop GNN training
 * @returns {Promise} Success message
 */
export const stopGNNTraining = async () => {
  const response = await api.post('/model/stop-training');
  return response.data;
};

export default {
  getGNNModelInfo,
  loadGNNModel,
  unloadGNNModel,
  listGNNCheckpoints,
  deleteGNNCheckpoint,
  testGNNModel,
  startGNNTraining,
  getGNNTrainingStatus,
  stopGNNTraining
};
